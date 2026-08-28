"""Contract tests for 2.1 — shared SFT harness + Schema Linker training entry point.

Covers the now-set (no-GPU) acceptance criteria: completion-only masking, run_sft
importability + documented config contract, and the entry-point config assembly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
import yaml

from experiments.train_query_generator import build_run_config as build_qg_run_config
from experiments.train_schema_linker import build_run_config
from pipeline.sft import (
    _training_arguments_kwargs,
    build_model_inputs,
    measure_token_lengths,
    run_sft,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS_YAML = _REPO_ROOT / "config" / "models.yaml"
_TRAIN_YAML = _REPO_ROOT / "config" / "schema_linker_train.yaml"
_CONFIG_DIR = _REPO_ROOT / "config"

# Every Mistral SL/QG train YAML (2.1/2.4 from-scratch + the 7.4/10.3 continue-SFT pairs).
_MISTRAL_TRAIN_YAMLS = [
    "schema_linker_train.yaml",
    "query_generator_train.yaml",
    "schema_linker_train_v3.yaml",
    "query_generator_train_v3.yaml",
    "schema_linker_train_pole_external.yaml",
    "query_generator_train_pole_external.yaml",
]
# The six 10.6 Qwen YAMLs (Stage-1 generic + the four Stage-2 continues).
_QWEN_TRAIN_YAMLS = [
    "schema_linker_train_qwen_generic.yaml",
    "query_generator_train_qwen_generic.yaml",
    "schema_linker_train_qwen_v3.yaml",
    "query_generator_train_qwen_v3.yaml",
    "schema_linker_train_qwen_pole_external.yaml",
    "query_generator_train_qwen_pole_external.yaml",
]


class _CharTokenizer:
    """Minimal stand-in: one id per character, single-char eos so prompt is a clean prefix."""

    eos_token = "§"      # '§' — one character, distinct from the PROMPT/COMPL letters
    pad_token_id = 256   # > any ASCII ord used here, and non-zero so it isn't skipped
    eos_token_id = 257

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [ord(c) for c in text]


# ── Acceptance 1: completion-only masking, correct shapes ─────────────────────────
def test_build_model_inputs_masking_and_shapes():
    tok = _CharTokenizer()
    out = build_model_inputs("PROMPT", "COMPL", tok, max_seq_length=32)

    assert set(out) == {"input_ids", "attention_mask", "labels"}
    for tensor in out.values():
        assert tensor.shape == (32,)
        assert tensor.dtype == torch.long

    prompt_len = len("PROMPT")                       # 6 (one id per char)
    completion_ids = [ord(c) for c in "COMPL" + tok.eos_token]
    real_len = prompt_len + len(completion_ids)      # 12

    # Prompt span masked with -100; completion (incl. eos) carries the real ids.
    assert out["labels"][:prompt_len].tolist() == [-100] * prompt_len
    assert out["labels"][prompt_len:real_len].tolist() == completion_ids
    # Padding masked in both labels and attention_mask.
    assert out["labels"][real_len:].tolist() == [-100] * (32 - real_len)
    assert out["attention_mask"].tolist() == [1] * real_len + [0] * (32 - real_len)
    # input_ids: real tokens then pad_id.
    assert out["input_ids"][:real_len].tolist() == [ord(c) for c in "PROMPT"] + completion_ids
    assert out["input_ids"][real_len:].tolist() == [tok.pad_token_id] * (32 - real_len)


def test_build_model_inputs_truncates_to_max_seq_length():
    tok = _CharTokenizer()
    out = build_model_inputs("PROMPT", "COMPLETION", tok, max_seq_length=8)
    for tensor in out.values():
        assert tensor.shape == (8,)
    # No padding when content already fills the window.
    assert out["attention_mask"].tolist() == [1] * 8


# ── Acceptance 2: run_sft importable with a documented config-key contract ────────
def test_run_sft_importable_and_documented():
    assert callable(run_sft)
    doc = run_sft.__doc__ or ""
    for key in ('config["model"]', 'config["peft"]', 'config["training"]', 'config["data"]'):
        assert key in doc


# ── Acceptance 3: entry point assembles a valid run_sft config from the YAMLs ──────
def test_build_run_config_for_known_key():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))

    config = build_run_config("mistral7b", registry, hp)

    assert config["model"]["base"] == registry["mistral7b"]["base"]
    # target_modules comes from the registry (architecture-specific), not the shared YAML.
    assert config["peft"]["target_modules"] == registry["mistral7b"]["target_modules"]
    assert "target_modules" not in hp["peft"]
    assert config["training"]["output_dir"] == "checkpoints/mistral7b/sl_adapter"
    # Shared hyperparameters carried through; max_seq_length is not the rejected 512.
    assert config["peft"]["r"] == hp["peft"]["r"]
    assert config["training"]["max_seq_length"] == hp["training"]["max_seq_length"] != 512
    assert config["data"] == hp["data"]


def test_build_run_config_namespaces_second_base():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    config = build_run_config("llama31-8b", registry, hp)
    assert config["training"]["output_dir"] == "checkpoints/llama31-8b/sl_adapter"


def test_build_run_config_unknown_key_exits_with_known_keys():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit) as exc:
        build_run_config("does-not-exist", registry, hp)
    message = str(exc.value)
    assert "mistral7b" in message and "llama31-8b" in message


# ── max_seq_length sub-task helper (runs offline once the 1.2 jsonl exists) ────────
def test_measure_token_lengths(tmp_path):
    rows = [
        {"prompt": "ab", "completion": "c"},        # 2 + 1 + 1(eos) = 4
        {"prompt": "abcd", "completion": "ef"},      # 4 + 2 + 1     = 7
        {"prompt": "a", "completion": "bcdefg"},     # 1 + 6 + 1     = 8
    ]
    jsonl = tmp_path / "train.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    report = measure_token_lengths(jsonl, _CharTokenizer(), percentiles=(50, 99))
    assert report["count"] == 3
    assert report["max"] == 8
    assert report["p99"] == 8


# ── 10.6 acceptance 1: the gradient-checkpointing flag is guarded ─────────────────
# The flag must be inert unless a YAML asks for it, so the Mistral v2/v3/_pole_external
# adapters would retrain byte-identically to the ones already on disk.
@pytest.mark.parametrize("yaml_name", _MISTRAL_TRAIN_YAMLS)
def test_mistral_training_arguments_unchanged_by_the_new_flag(yaml_name):
    hp = yaml.safe_load((_CONFIG_DIR / yaml_name).read_text(encoding="utf-8"))
    train_cfg = {k: v for k, v in hp["training"].items() if k != "output_name"}
    train_cfg["output_dir"] = "checkpoints/mistral7b/sl_adapter"

    # No Mistral YAML carries the flag at all ...
    assert "gradient_checkpointing" not in hp["training"]
    # ... so the kwargs are exactly the pre-10.6 set, key for key and value for value.
    assert _training_arguments_kwargs(train_cfg, has_eval=True) == {
        "output_dir": "checkpoints/mistral7b/sl_adapter",
        "num_train_epochs": train_cfg["num_train_epochs"],
        "per_device_train_batch_size": train_cfg["per_device_train_batch_size"],
        "gradient_accumulation_steps": train_cfg["gradient_accumulation_steps"],
        "learning_rate": train_cfg["learning_rate"],
        "lr_scheduler_type": train_cfg["lr_scheduler_type"],
        "warmup_ratio": train_cfg["warmup_ratio"],
        "weight_decay": train_cfg["weight_decay"],
        "bf16": False,
        "fp16": True,
        "logging_steps": train_cfg["logging_steps"],
        "save_strategy": train_cfg["save_strategy"],
        "evaluation_strategy": train_cfg["evaluation_strategy"],
        "per_device_eval_batch_size": train_cfg["per_device_eval_batch_size"],
    }


def test_training_arguments_flag_absent_false_and_true():
    base = {
        "output_dir": "checkpoints/x/sl_adapter", "num_train_epochs": 3,
        "per_device_train_batch_size": 1, "gradient_accumulation_steps": 32,
        "learning_rate": 2.0e-4, "lr_scheduler_type": "cosine", "warmup_ratio": 0.03,
        "weight_decay": 0.001, "logging_steps": 50, "save_strategy": "epoch",
        "evaluation_strategy": "epoch",
    }
    absent = _training_arguments_kwargs(base, has_eval=True)
    assert "gradient_checkpointing" not in absent
    assert "gradient_checkpointing_kwargs" not in absent
    # An explicit false is equally inert.
    assert _training_arguments_kwargs({**base, "gradient_checkpointing": False}, True) == absent

    on = _training_arguments_kwargs({**base, "gradient_checkpointing": True}, has_eval=True)
    assert on["gradient_checkpointing"] is True
    # use_reentrant=False is required with PEFT + 4-bit (10.5).
    assert on["gradient_checkpointing_kwargs"] == {"use_reentrant": False}
    assert {k: v for k, v in on.items() if not k.startswith("gradient_checkpointing")} == {
        k: v for k, v in absent.items() if not k.startswith("gradient_checkpointing")
    }


def test_evaluation_strategy_is_no_without_an_eval_split():
    train_cfg = {
        "output_dir": "d", "num_train_epochs": 1, "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 1, "learning_rate": 1e-4, "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.0, "weight_decay": 0.0, "logging_steps": 1, "save_strategy": "epoch",
        "evaluation_strategy": "epoch",
    }
    assert _training_arguments_kwargs(train_cfg, has_eval=False)["evaluation_strategy"] == "no"


# ── 10.6: the six Qwen YAMLs carry the fit-test-mandated training overrides ───────
@pytest.mark.parametrize("yaml_name", _QWEN_TRAIN_YAMLS)
def test_qwen_train_yamls_pin_the_fit_test_settings(yaml_name):
    hp = yaml.safe_load((_CONFIG_DIR / yaml_name).read_text(encoding="utf-8"))
    training = hp["training"]
    # 10.5 (job 1101258): batch 2 OOMs a 32 GB V100, and batch 1 OOMs without checkpointing.
    assert training["per_device_train_batch_size"] == 1
    assert training["gradient_accumulation_steps"] == 32      # effective batch stays 32
    assert training["gradient_checkpointing"] is True
    assert training["fp16"] is True and training["bf16"] is False   # Volta: no bf16
    assert training["max_seq_length"] == 3584


@pytest.mark.parametrize("yaml_name", _QWEN_TRAIN_YAMLS)
def test_qwen_train_yamls_assemble_qwen_run_configs(yaml_name):
    """Each Qwen YAML + the registry produces a run_sft config with the right adapter paths."""
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load((_CONFIG_DIR / yaml_name).read_text(encoding="utf-8"))
    builder = build_run_config if yaml_name.startswith("schema_linker") else build_qg_run_config

    config = builder("qwen2.5-32b", registry, hp)
    role = "sl" if yaml_name.startswith("schema_linker") else "qg"
    suffix = {"generic": "", "v3": "_v3", "pole_external": "_pole_external"}[
        yaml_name.removesuffix(".yaml").split("_qwen_", 1)[1]
    ]
    assert config["training"]["output_dir"] == f"checkpoints/qwen2.5-32b/{role}_adapter{suffix}"
    assert config["model"]["base"] == registry["qwen2.5-32b"]["base"]
    assert config["model"]["load_in_4bit"] is True          # LOCKED by the 10.5 fit-test
    assert config["peft"]["target_modules"] == registry["qwen2.5-32b"]["target_modules"]
    # Stage 1 inits a fresh LoRA; both Stage-2 continues start from that generic adapter (7.4).
    if suffix:
        assert config["model"]["init_adapter_path"] == f"checkpoints/qwen2.5-32b/{role}_adapter"
    else:
        assert "init_adapter_path" not in config["model"]
    # The flag survives config assembly into the kwargs run_sft passes to TrainingArguments.
    assert _training_arguments_kwargs(config["training"], True)["gradient_checkpointing"] is True
