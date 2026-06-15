# pipeline/sft.py
"""Reusable LoRA SFT harness for the Schema Linker (2.1) and Query Generator (2.4).

Two public entry points, identical for both adapters:
  - ``build_model_inputs``: tokenise one (prompt, completion) row with completion-only
    loss masking (prompt + padding -> -100).
  - ``run_sft``: run LoRA/QLoRA SFT from a flat config dict and return the adapter path.

``measure_token_lengths`` supports the 2.1 ``max_seq_length`` sub-task (set the cap to cover
~the 99th percentile of prompt + completion lengths on the train split).
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import torch
from transformers import PreTrainedTokenizer


def build_model_inputs(
    prompt: str,
    completion: str,
    tokenizer: PreTrainedTokenizer,
    max_seq_length: int,
) -> dict:
    """Tokenise (prompt + completion + eos); mask prompt tokens in labels with -100.

    labels: -100 for prompt and padding tokens (ignored by CrossEntropyLoss), real token
    ids for the completion. This is the completion-only loss used by both adapters.

    Returns the three tensors (``input_ids``, ``attention_mask``, ``labels``), each of
    shape ``[max_seq_length]``. If ``prompt + completion`` exceeds ``max_seq_length`` the
    completion (the target) is truncated — see the 2.1 ``max_seq_length`` sub-task.
    """
    full_text  = prompt + completion + tokenizer.eos_token
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
    full_ids   = tokenizer.encode(full_text, add_special_tokens=False)[:max_seq_length]
    prompt_len = min(len(prompt_ids), max_seq_length)

    labels = ([-100] * prompt_len + full_ids[prompt_len:])[:max_seq_length]
    pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    pad = max_seq_length - len(full_ids)
    return {
        "input_ids":      torch.tensor(full_ids + [pad_id] * pad, dtype=torch.long),
        "attention_mask": torch.tensor([1] * len(full_ids) + [0] * pad, dtype=torch.long),
        "labels":         torch.tensor(labels + [-100] * pad, dtype=torch.long),
    }


class _JsonlSFTDataset(torch.utils.data.Dataset):
    """Wraps a {"prompt","completion"} jsonl split; each item -> build_model_inputs(...).

    Items are pre-padded with masked labels, so the default collator only needs to stack.
    """

    def __init__(self, path: str | Path, tokenizer: PreTrainedTokenizer, max_seq_length: int):
        text = Path(path).read_text(encoding="utf-8")
        self._rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        self._tokenizer = tokenizer
        self._max_seq_length = max_seq_length

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, idx: int) -> dict:
        row = self._rows[idx]
        return build_model_inputs(
            row["prompt"], row["completion"], self._tokenizer, self._max_seq_length
        )


def run_sft(config: dict) -> str:
    """Run LoRA SFT from a parsed config dict; return the saved adapter path.

    Config-key contract (a flat, already-assembled dict — the entry point merges the
    per-model registry fields in):
      config["model"]    : {"base": str, "dtype": str, "load_in_4bit": bool}
      config["peft"]     : {"r", "lora_alpha", "lora_dropout", "bias", "task_type",
                            "target_modules"}  # target_modules comes from config/models.yaml
      config["training"] : {"output_dir", "num_train_epochs", "per_device_train_batch_size",
                            "gradient_accumulation_steps", "learning_rate", "lr_scheduler_type",
                            "warmup_ratio", "max_seq_length", "weight_decay", "bf16", "fp16",
                            "logging_steps", "save_strategy", "evaluation_strategy",
                            "per_device_eval_batch_size" (optional, default 1)}
      config["data"]     : {"train_path", "eval_path"}  # eval_path optional

    Steps:
      1. Load base + tokenizer; apply dtype and, if load_in_4bit, a 4-bit QLoRA config.
      2. Wrap with PEFT LoraConfig (target_modules from the registry).
      3. Build train/eval datasets via build_model_inputs (completion-only loss).
      4. transformers.Trainer with TrainingArguments from config["training"]; train,
         resuming from the last checkpoint in output_dir if one exists.
      5. Save the adapter to output_dir; return that path.

    Idempotent: if output_dir already holds a saved adapter (``adapter_model.safetensors``
    from a prior completed run), training is skipped entirely and that path is returned —
    this lets a chained sequence of wall-clock-limited jobs re-invoke run_sft as a no-op
    once an earlier link in the chain has already finished. See the 2026-06-08 decisions-log
    entry on chaining 2.1/2.4 runs across the cluster's per-job time cap.
    """
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
        default_data_collator,
    )
    from transformers.trainer_utils import get_last_checkpoint

    model_cfg = config["model"]
    peft_cfg = config["peft"]
    train_cfg = config["training"]
    data_cfg = config["data"]
    output_dir = train_cfg["output_dir"]

    if (Path(output_dir) / "adapter_model.safetensors").exists():
        return output_dir

    # 1. Base model + tokenizer (dtype + optional QLoRA 4-bit).
    dtype = getattr(torch, model_cfg["dtype"])
    quant = None
    if model_cfg.get("load_in_4bit"):
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(model_cfg["base"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_cfg["base"],
        device_map="auto",
        torch_dtype=dtype,
        quantization_config=quant,
    )

    # 2. PEFT LoRA wrap (target_modules supplied by the registry).
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    if quant is not None:
        model = prepare_model_for_kbit_training(model)
    lora = LoraConfig(
        r=peft_cfg["r"],
        lora_alpha=peft_cfg["lora_alpha"],
        lora_dropout=peft_cfg["lora_dropout"],
        bias=peft_cfg["bias"],
        task_type=peft_cfg["task_type"],
        target_modules=peft_cfg["target_modules"],
    )
    model = get_peft_model(model, lora)

    # 3. Datasets (pre-padded, masked labels -> default collator).
    max_seq_length = train_cfg["max_seq_length"]
    train_ds = _JsonlSFTDataset(data_cfg["train_path"], tokenizer, max_seq_length)
    eval_path = data_cfg.get("eval_path")
    eval_ds = _JsonlSFTDataset(eval_path, tokenizer, max_seq_length) if eval_path else None

    # 4. Trainer; resume from the last epoch checkpoint if a prior chained run left one.
    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=train_cfg["num_train_epochs"],
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=train_cfg["learning_rate"],
        lr_scheduler_type=train_cfg["lr_scheduler_type"],
        warmup_ratio=train_cfg["warmup_ratio"],
        weight_decay=train_cfg["weight_decay"],
        bf16=train_cfg.get("bf16", False),
        fp16=train_cfg.get("fp16", False),
        logging_steps=train_cfg["logging_steps"],
        save_strategy=train_cfg["save_strategy"],
        evaluation_strategy=train_cfg["evaluation_strategy"] if eval_ds else "no",
        per_device_eval_batch_size=train_cfg.get("per_device_eval_batch_size", 1),
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=default_data_collator,
    )
    last_checkpoint = get_last_checkpoint(output_dir) if Path(output_dir).is_dir() else None
    # transformers 4.45.2's _load_rng_state() calls torch.load(rng_file) with no kwargs;
    # torch>=2.6 defaults weights_only=True, which can't unpickle the numpy RNG state in
    # our own (trusted, just-saved-by-us) checkpoints. Relax the default for this resume
    # call only — see decisions-log.
    _orig_torch_load = torch.load
    torch.load = functools.partial(torch.load, weights_only=False)
    try:
        trainer.train(resume_from_checkpoint=last_checkpoint)
    finally:
        torch.load = _orig_torch_load

    # 5. Save the adapter; return its path.
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def measure_token_lengths(
    jsonl_path: str | Path,
    tokenizer: PreTrainedTokenizer,
    percentiles: tuple[int, ...] = (50, 90, 95, 99),
) -> dict:
    """Token-length distribution of ``prompt + completion + eos`` over a jsonl split.

    Supports the 2.1 ``max_seq_length`` sub-task: set the cap to cover ~the 99th percentile
    so long schema blocks aren't silently truncated. Returns ``{"count", "max", "mean",
    "p50", "p90", ...}`` (one ``p{n}`` per requested percentile). Cheap, no GPU; only needs
    the base tokenizer and the materialised 1.2 jsonl.
    """
    text = Path(jsonl_path).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    lengths = [
        len(tokenizer.encode(
            row["prompt"] + row["completion"] + tokenizer.eos_token,
            add_special_tokens=False,
        ))
        for row in rows
    ]
    lengths.sort()
    report: dict = {
        "count": len(lengths),
        "max": lengths[-1] if lengths else 0,
        "mean": (sum(lengths) / len(lengths)) if lengths else 0.0,
    }
    for p in percentiles:
        report[f"p{p}"] = _percentile(lengths, p)
    return report


def _percentile(sorted_values: list[int], p: int) -> int:
    """Nearest-rank percentile of a pre-sorted list (0 if empty)."""
    if not sorted_values:
        return 0
    rank = max(1, (p * len(sorted_values) + 99) // 100)   # ceil(p/100 * n), >=1
    return sorted_values[min(rank, len(sorted_values)) - 1]
