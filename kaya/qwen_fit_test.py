"""Step 10.5 — Qwen2.5-32B precision fit-test (GO/NO-GO probe) on a Kaya v100-32gb node.

NOT a pipeline module: a Kaya measurement harness. It answers the one question 10.6/10.7 need
answered before spending days of GPU time — **at what precision, and on how many 32GB cards,
does Qwen2.5-32B load, train one QLoRA step, and run one diverse-beam SL generate?**

Phases are separate processes on purpose (a 4-bit and an 8-bit copy of a 32B base will not
coexist on one node), each writing a JSON fragment; `--phase summary` aggregates them and
prints the recommendation:

    python kaya/qwen_fit_test.py --phase load     --precision 4bit
    python kaya/qwen_fit_test.py --phase load     --precision 8bit
    python kaya/qwen_fit_test.py --phase generate --precision 4bit
    python kaya/qwen_fit_test.py --phase train    --precision 4bit
    python kaya/qwen_fit_test.py --phase summary

`load`/`generate` go through `build_llm` (0.2) with **no loader change** — acceptance
criterion 1. `train` mirrors `run_sft`'s (2.1) model/PEFT construction and calls
`build_model_inputs` on real `data/pole_ext_sl_train.jsonl` rows, so the measured peak is the
peak 10.6 will see.

**Step 11.2 reuses this harness unchanged in substance** for Qwen2.5-72B on an H100
(`kaya/111_qwen72b_fit_test.slurm`). Everything 11.2 needed was additive, and every default is
10.5's, so the 10.5 invocations above still behave byte-identically:

  --model_key       which config/models.yaml entry to measure (default qwen2.5-32b)
  --results_dir     where the fragments land (default results/qwen_fit_test) — a second model
                    must not overwrite the first model's fragments
  --tag             fragment-name suffix, so a second train leg at a different batch size
                    (11.2's batch-2 headroom probe) sits beside the primary one
  --budget_profile  which training recipe the summary extrapolates (default `mixed` = 10.5/10.6's
                    Ozsoy-replay mix; `phase11` = 11.3's two-stage generic + POLE-only continues)

11.2 also drops the 8-bit leg (10.5 settled precision) and adds two summary sections the 32B
run did not need: the batch-2 headroom evidence and the three-co-located-load arithmetic that
sizes 11.4's `--gres` against `experiments/build_condition3.py::_device_maps()`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# Run from repo root so the experiments/ package (not pip-installed, unlike pipeline) imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import yaml

from experiments.probe_utils import generate_beams
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.schema import build_pole_external_schema_repr
from pipeline.sft import build_model_inputs

MIB = 1024 * 1024
RESULTS_DIR = Path("results/qwen_fit_test")   # default; --results_dir overrides it in main()

# Job-time cap the budget lines flag against: 72 h on the v100 `gpu` partition and 3 days on
# the H100 `rrifcs` partition are the same number.
JOB_HOUR_CAP = 72

# Training recipes the summary extrapolates the measured step time over. A stage is
# (label, rows file, epochs, how many adapters share that shape) — micro-steps are derived from
# the real row count on disk, so a stale hand-written count cannot creep into a budget table.
BUDGET_PROFILES: dict[str, list[tuple[str, str, int, int]]] = {
    # 10.5's original assumption: from-scratch LoRA over the Ozsoy-replay *mixed* files,
    # 3 epochs, one adapter each for sl/qg x v3/pole_external.
    "mixed": [
        ("v3", "data/pole_sl_train_mixed.jsonl", 3, 2),
        ("pole_external", "data/pole_ext_sl_train_mixed.jsonl", 3, 2),
    ],
    # What 10.6 actually ran and 11.3 will repeat: Stage 1 from-scratch on the 4k Ozsoy sample
    # (3 epochs), then four POLE-only continue-SFTs (2 epochs) — NOT the _mixed files.
    "phase11": [
        ("generic (Ozsoy 4k)", "data/ozsoy_sl_train_4k.jsonl", 3, 2),
        ("_v3 continue", "data/pole_sl_train.jsonl", 2, 2),
        ("_pole_external continue", "data/pole_ext_sl_train.jsonl", 2, 2),
    ],
}


# ── measurement helpers ────────────────────────────────────────────────────────
def gpu_snapshot() -> list[dict]:
    """Per-GPU memory, both as the driver sees it and as torch accounts for it.

    `resident_mib` (total - free, from the driver) is the honest "does it fit" number — it
    includes the CUDA context and any bitsandbytes/cuBLAS workspace that torch's allocator
    does not track. `peak_alloc_mib` is torch's high-water mark since the last reset.
    """
    snap = []
    for i in range(torch.cuda.device_count()):
        free, total = torch.cuda.mem_get_info(i)
        snap.append({
            "device": i,
            "name": torch.cuda.get_device_name(i),
            "total_mib": round(total / MIB, 1),
            "resident_mib": round((total - free) / MIB, 1),
            "alloc_mib": round(torch.cuda.memory_allocated(i) / MIB, 1),
            "reserved_mib": round(torch.cuda.memory_reserved(i) / MIB, 1),
            "peak_alloc_mib": round(torch.cuda.max_memory_allocated(i) / MIB, 1),
        })
    return snap


def print_snapshot(label: str, snap: list[dict]) -> None:
    total = sum(d["resident_mib"] for d in snap)
    print(f"\n--- VRAM: {label} ---")
    for d in snap:
        print(f"  gpu{d['device']} ({d['name']}): resident {d['resident_mib']:>9.1f} MiB "
              f"/ {d['total_mib']:.0f} MiB   torch alloc {d['alloc_mib']:>9.1f}  "
              f"reserved {d['reserved_mib']:>9.1f}  peak {d['peak_alloc_mib']:>9.1f}")
    print(f"  TOTAL resident: {total:.1f} MiB ({total / 1024:.2f} GiB) across "
          f"{len(snap)} GPU(s)")


def fragment_name(args: argparse.Namespace, stem: str) -> str:
    """`load_4bit` / `train_4bit_batch2` — `--tag` keeps a second leg from clobbering the first."""
    return f"{stem}_{args.tag}" if args.tag else stem


def write_fragment(name: str, payload: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {path}")
    return path


def load_registry(models_config: str, model_key: str) -> dict:
    registry = yaml.safe_load(Path(models_config).read_text(encoding="utf-8"))
    if model_key not in registry:
        raise SystemExit(f"Unknown model_key {model_key!r}; known: {sorted(registry)}")
    return registry[model_key]


def quant_flags(precision: str) -> dict:
    """`{load_in_4bit, load_in_8bit}` for the requested precision (fp16 = neither)."""
    return {
        "load_in_4bit": precision == "4bit",
        "load_in_8bit": precision == "8bit",
    }


# ── phase: load (VRAM at a given precision, via build_llm — no loader change) ───
def phase_load(args: argparse.Namespace, entry: dict) -> dict:
    from pipeline.llm import build_llm

    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)
    before = gpu_snapshot()
    print_snapshot("before load", before)

    spec = {
        "backend": "huggingface",
        "model_name_or_path": entry["base"],
        "torch_dtype": entry["dtype"],
        **quant_flags(args.precision),
    }
    print(f"\nbuild_llm({spec}) …")
    t0 = time.perf_counter()
    llm = build_llm(spec)
    load_s = time.perf_counter() - t0

    after = gpu_snapshot()
    print_snapshot(f"after load ({args.precision})", after)
    print(f"  load wall-clock: {load_s:.1f}s")

    device_map = getattr(llm.model, "hf_device_map", None)
    gpus_used = sorted({v for v in (device_map or {}).values() if isinstance(v, int)})
    print(f"  hf_device_map spans device(s): {gpus_used or 'n/a'} "
          f"(entries: {len(device_map or {})})")
    offloaded = sorted({str(v) for v in (device_map or {}).values()
                        if not isinstance(v, int)})
    if offloaded:
        print(f"  ⚠ NON-GPU placements present (cpu/disk offload): {offloaded}")

    payload = {
        "phase": "load",
        "precision": args.precision,
        "base": entry["base"],
        "dtype": entry["dtype"],
        "load_seconds": round(load_s, 1),
        "gpu_count": torch.cuda.device_count(),
        "gpus_used_by_device_map": gpus_used,
        "non_gpu_placements": offloaded,
        "before": before,
        "after": after,
        "total_resident_mib": round(sum(d["resident_mib"] for d in after), 1),
        "max_single_gpu_resident_mib": round(max(d["resident_mib"] for d in after), 1),
    }
    if args.phase == "load":
        write_fragment(fragment_name(args, f"load_{args.precision}"), payload)
        return payload
    # phase == "generate": hand the loaded model on to the generate leg.
    payload["_llm"] = llm
    return payload


# ── phase: generate (one k=5 diverse-beam SL decode, the live 3.1 decoding) ─────
def phase_generate(args: argparse.Namespace, entry: dict) -> dict:
    load_payload = phase_load(args, entry)      # args.phase == "generate" -> hands the model back
    llm = load_payload.pop("_llm")

    schema_block = build_pole_external_schema_repr().to_prompt_string(include_properties=True)
    items = load_benchmark(args.benchmark)
    question = items[args.item_index].question
    decoding = {"strategy": "beam", "diversity_penalty": args.diversity_penalty, "k": args.k}
    print(f"\nDiverse-beam SL generate: k={args.k}, dp={args.diversity_penalty}, "
          f"item={items[args.item_index].question_id}\n  Q: {question}")

    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)
    t0 = time.perf_counter()
    beams = generate_beams(llm, question, schema_block, decoding)
    gen_s = time.perf_counter() - t0

    for rank, beam in enumerate(beams, start=1):
        print(f"  beam {rank}: {beam}")
    after = gpu_snapshot()
    print_snapshot("after generate", after)
    print(f"  generate wall-clock: {gen_s:.1f}s for k={args.k} beams "
          f"({gen_s / max(args.k, 1):.1f}s/beam)")

    payload = {
        **load_payload,
        "phase": "generate",
        "question_id": items[args.item_index].question_id,
        "question": question,
        "k": args.k,
        "diversity_penalty": args.diversity_penalty,
        "beams": beams,
        "distinct_beams": len(set(beams)),
        "generate_seconds": round(gen_s, 2),
        "after_generate": after,
        "generate_peak_total_mib": round(sum(d["peak_alloc_mib"] for d in after), 1),
    }
    write_fragment(fragment_name(args, f"generate_{args.precision}"), payload)
    return payload


# ── phase: train (one real QLoRA forward+backward+step at the locked precision) ─
def _run_steps(model, batch: dict, optimiser, scaler, n_steps: int) -> tuple[list[float], list[float]]:
    """Time `n_steps` forward+backward+optimiser steps; return (seconds, losses)."""
    step_seconds: list[float] = []
    losses: list[float] = []
    for step in range(n_steps):
        torch.cuda.synchronize()
        t_step = time.perf_counter()
        optimiser.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=batch["_autocast_dtype"]):
            out = model(**{k: v for k, v in batch.items() if not k.startswith("_")})
        scaler.scale(out.loss).backward()
        scaler.step(optimiser)
        scaler.update()
        torch.cuda.synchronize()
        step_seconds.append(time.perf_counter() - t_step)
        losses.append(float(out.loss.detach().item()))
        print(f"  step {step + 1}/{n_steps}: loss {losses[-1]:.4f}  {step_seconds[-1]:.2f}s")
    return step_seconds, losses


def _steady(step_seconds: list[float]) -> float:
    """Mean step time excluding step 1, which pays one-off allocator warm-up."""
    steady = step_seconds[1:] or step_seconds
    return sum(steady) / len(steady)


def phase_train(args: argparse.Namespace, entry: dict) -> dict:
    """Mirrors run_sft's (2.1) model + PEFT construction, then times N micro-steps.

    Deliberately does NOT call run_sft — that runs a whole Trainer loop over the full split.
    The construction here (BitsAndBytesConfig -> prepare_model_for_kbit_training -> LoraConfig
    with the registry `target_modules`) is step-for-step the same, and the batch is built with
    the same `build_model_inputs` on real rows, so the peak is representative.

    Two legs off ONE load, because they answer different questions:
      - `checkpointed`: what 10.5's spec asks for (gradient checkpointing on).
      - `plain`: what `run_sft` ACTUALLY does today — its `TrainingArguments` never sets
        `gradient_checkpointing`. If this leg OOMs, 10.6 cannot just point run_sft at the
        Qwen YAMLs; the OOM is recorded rather than raised (`--no_plain_leg` skips it).
    """
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    hp = yaml.safe_load(Path(args.train_config).read_text(encoding="utf-8"))
    max_seq_length = args.max_seq_length or hp["training"]["max_seq_length"]
    batch_size = args.batch_size or hp["training"]["per_device_train_batch_size"]
    dtype = getattr(torch, entry["dtype"])
    flags = quant_flags(args.precision)

    quant = None
    if flags["load_in_4bit"]:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=dtype,
                                   bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    elif flags["load_in_8bit"]:
        quant = BitsAndBytesConfig(load_in_8bit=True)

    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)
    print(f"\nLoading {entry['base']} for training at {args.precision} "
          f"(max_seq_length={max_seq_length}, per_device_train_batch_size={batch_size}) …")
    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(entry["base"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        entry["base"], device_map="auto", torch_dtype=dtype, quantization_config=quant
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    lora = LoraConfig(
        r=hp["peft"]["r"], lora_alpha=hp["peft"]["lora_alpha"],
        lora_dropout=hp["peft"]["lora_dropout"], bias=hp["peft"]["bias"],
        task_type=hp["peft"]["task_type"], target_modules=entry["target_modules"],
    )
    model = get_peft_model(model, lora)
    model.train()
    load_s = time.perf_counter() - t0
    model.print_trainable_parameters()
    after_load = gpu_snapshot()
    print_snapshot(f"after train-load ({args.precision}, +LoRA)", after_load)
    print(f"  train-load wall-clock: {load_s:.1f}s")

    rows = [json.loads(line) for line in
            Path(args.train_rows).read_text(encoding="utf-8").splitlines() if line.strip()]
    batch_rows = rows[:batch_size]
    built = [build_model_inputs(r["prompt"], r["completion"], tokenizer, max_seq_length)
             for r in batch_rows]
    device = model.device
    batch = {key: torch.stack([b[key] for b in built]).to(device) for key in built[0]}
    real_tokens = int(batch["attention_mask"].sum().item())
    print(f"  batch: {batch['input_ids'].shape} from {args.train_rows} "
          f"({real_tokens} real tokens, rest padding)")
    batch["_autocast_dtype"] = dtype

    optimiser = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=hp["training"]["learning_rate"]
    )
    # fp16 (Volta, no bf16) — mirror Trainer's fp16 path: autocast forward + loss scaling.
    scaler = torch.amp.GradScaler("cuda", enabled=bool(hp["training"].get("fp16", True)))

    print(f"\nLeg 1/2 — gradient checkpointing ON ({args.train_steps} steps):")
    step_seconds, losses = _run_steps(model, batch, optimiser, scaler, args.train_steps)
    after_step = gpu_snapshot()
    print_snapshot("after checkpointed step(s) — PEAK", after_step)
    steady_s = _steady(step_seconds)
    print(f"  steady-state step time: {steady_s:.2f}s "
          f"(first step {step_seconds[0]:.2f}s, {len(step_seconds) - 1 or 1} steady sample(s))")

    # Leg 2 — no gradient checkpointing: what run_sft's TrainingArguments actually does today.
    plain: dict = {"measured": False}
    if not args.no_plain_leg:
        print(f"\nLeg 2/2 — gradient checkpointing OFF (run_sft as written), "
              f"{args.train_steps} steps:")
        model.gradient_checkpointing_disable()
        for i in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(i)
        try:
            plain_seconds, plain_losses = _run_steps(model, batch, optimiser, scaler,
                                                     args.train_steps)
            plain_snap = gpu_snapshot()
            print_snapshot("after plain step(s) — PEAK", plain_snap)
            plain = {
                "measured": True, "oom": False,
                "step_seconds": [round(s, 3) for s in plain_seconds],
                "steady_step_seconds": round(_steady(plain_seconds), 3),
                "losses": [round(v, 4) for v in plain_losses],
                "after_step": plain_snap,
                "peak_resident_total_mib": round(sum(d["resident_mib"] for d in plain_snap), 1),
                "max_single_gpu_resident_mib": round(
                    max(d["resident_mib"] for d in plain_snap), 1),
            }
        except torch.cuda.OutOfMemoryError as exc:
            print(f"  ⚠ OOM without gradient checkpointing: {exc}")
            print("    -> 10.6 must enable gradient checkpointing (run_sft change) at this "
                  "seq-len/batch, or lower per_device_train_batch_size.")
            plain = {"measured": True, "oom": True, "error": str(exc)[:400]}
        finally:
            model.gradient_checkpointing_enable()

    payload = {
        "phase": "train",
        "precision": args.precision,
        "base": entry["base"],
        "dtype": entry["dtype"],
        "target_modules": entry["target_modules"],
        "train_config": args.train_config,
        "train_rows_file": args.train_rows,
        "max_seq_length": max_seq_length,
        "per_device_train_batch_size": batch_size,
        "gradient_checkpointing": True,
        "real_tokens_in_batch": real_tokens,
        "load_seconds": round(load_s, 1),
        "step_seconds": [round(s, 3) for s in step_seconds],
        "steady_step_seconds": round(steady_s, 3),
        "losses": [round(v, 4) for v in losses],
        "gpu_count": torch.cuda.device_count(),
        "gpus_used_by_device_map": sorted({v for v in (getattr(model, "hf_device_map", None)
                                                       or {}).values() if isinstance(v, int)}),
        "after_load": after_load,
        "after_step": after_step,
        "peak_total_mib": round(sum(d["peak_alloc_mib"] for d in after_step), 1),
        "peak_resident_total_mib": round(sum(d["resident_mib"] for d in after_step), 1),
        "max_single_gpu_resident_mib": round(max(d["resident_mib"] for d in after_step), 1),
        "no_gradient_checkpointing": plain,
    }
    write_fragment(fragment_name(args, f"train_{args.precision}"), payload)
    return payload


# ── phase: summary (aggregate the fragments; print the recommendation) ──────────
def _count_rows(path: str) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


def _fits_one_card(snap: list[dict], headroom_mib: float = 1024.0) -> bool:
    """True when the TOTAL footprint would fit on a single card with `headroom_mib` to spare.

    Footprint-vs-capacity, NOT "how many cards did the run touch": with 2 GPUs visible,
    `device_map="auto"` spreads a model that would comfortably fit one card across both, so
    counting occupied cards understates single-card feasibility. Sum resident across GPUs and
    compare to one card's capacity — the honest "does 20 GB fit in a 32 GB card" question.
    """
    total_footprint = sum(d["resident_mib"] for d in snap)
    single_card_capacity = max(d["total_mib"] for d in snap)
    return total_footprint + headroom_mib <= single_card_capacity


def _card_name(fragments: dict) -> str:
    """The GPU this fit-test ran on, taken from any fragment's snapshot."""
    for frag in fragments.values():
        for key in ("after", "after_step", "after_load", "before"):
            snap = frag.get(key)
            if snap:
                return f"{snap[0]['name']} ({snap[0]['total_mib'] / 1024:.1f} GiB)"
    return "unknown GPU"


def _base_name(fragments: dict) -> str:
    for frag in fragments.values():
        if frag.get("base"):
            return frag["base"]
    return "unknown base"


def _colocation_block(load_frag: dict | None, gen_frag: dict | None,
                      fallback_headroom_gib: float = 4.0) -> dict:
    """Leg 5 — can C3's three co-located loads share two cards, or does 11.4 need three?

    `build_condition3._device_maps()` pins SL -> cuda:0 and QG **and** AD -> cuda:1 whenever
    >= 2 GPUs are visible, so the binding constraint is **two model copies on card 1**, not the
    three-copy total — and note that a THIRD card does not relieve it by itself: `_device_maps`
    returns `({"":0}, {"":1}, {"":1})` for any device_count >= 2, so `cuda:2` would sit idle.

    Decode headroom is measured, not guessed: the generate leg's peak minus the load leg's
    footprint is what one k=5 group-beam decode actually cost on this card. QG and AD decode
    with k=1, so charging *each* of them the k=5 figure is a deliberate over-estimate — if the
    verdict is FITS under that bound it is not a knife-edge on the KV term.
    """
    if not load_frag or load_frag.get("failed"):
        return {"measured": False}
    per_load_gib = load_frag["total_resident_mib"] / 1024
    card_gib = max(d["total_mib"] for d in load_frag["after"]) / 1024

    decode_gib, decode_source = fallback_headroom_gib, "assumed (no generate fragment)"
    if gen_frag and not gen_frag.get("failed") and gen_frag.get("after_generate"):
        peak_gib = sum(d["resident_mib"] for d in gen_frag["after_generate"]) / 1024
        if peak_gib > per_load_gib:
            decode_gib = peak_gib - per_load_gib
            decode_source = f"measured (k={gen_frag.get('k')} beam decode peak - load)"

    weights_gib = 2 * per_load_gib
    worst_case_gib = weights_gib + 2 * decode_gib          # QG + AD each charged a k=5 decode
    return {
        "measured": True,
        "per_load_gib": round(per_load_gib, 2),
        "card_gib": round(card_gib, 2),
        "two_on_one_card_gib": round(weights_gib, 2),
        "three_loads_gib": round(3 * per_load_gib, 2),
        "decode_headroom_gib": round(decode_gib, 2),
        "decode_headroom_source": decode_source,
        "card1_worst_case_gib": round(worst_case_gib, 2),
        "card1_margin_gib": round(card_gib - worst_case_gib, 2),
        "qg_plus_ad_fit_one_card": worst_case_gib <= card_gib,
        "gpus_needed_for_c3": 2 if worst_case_gib <= card_gib else 3,
    }


def phase_summary(args: argparse.Namespace) -> dict:
    fragments = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                 for p in sorted(RESULTS_DIR.glob("*.json")) if p.stem != "summary"}
    if not fragments:
        raise SystemExit(f"No fragments in {RESULTS_DIR} — run the load/train/generate phases first.")

    print("\n" + "=" * 78)
    print(f"FIT-TEST SUMMARY — {_base_name(fragments)} on {_card_name(fragments)}")
    print("=" * 78)

    # Precisions actually measured. 10.5 probed 4bit + 8bit; 11.2 drops the 8-bit leg (10.5
    # settled precision and a ~78 GiB 8-bit 72B is of no interest), so iterate what exists.
    measured_precisions = sorted({
        frag["precision"] for name, frag in fragments.items()
        if name.startswith(("load_", "generate_")) and frag.get("precision")
    })
    print("\n1-2. LOAD VRAM BY PRECISION (inference path, via build_llm)")
    for precision in measured_precisions:
        frag = fragments.get(f"load_{precision}") or fragments.get(f"generate_{precision}")
        if frag.get("failed"):
            print(f"  {precision}: FAILED TO LOAD — {frag['error'].splitlines()[0]}")
            continue
        snap = frag["after"]
        per_gpu = ", ".join(f"gpu{d['device']} {d['resident_mib']:.0f}" for d in snap)
        print(f"  {precision}: total {frag['total_resident_mib']:.0f} MiB "
              f"({frag['total_resident_mib'] / 1024:.1f} GiB) — [{per_gpu}] MiB; "
              f"one card: {'YES' if _fits_one_card(snap) else 'NO (spans/needs 2)'}"
              f"{'; ⚠ offload ' + str(frag['non_gpu_placements']) if frag.get('non_gpu_placements') else ''}")

    def _ok(name: str) -> dict | None:
        frag = fragments.get(name)
        if frag and frag.get("failed"):
            print(f"\n[{name}] FAILED: {frag['error'].splitlines()[0]}")
            return None
        return frag

    train = _ok(f"train_{args.precision}")
    gen = _ok(f"generate_{args.precision}")

    print(f"\n3. ONE QLoRA TRAIN STEP @ {args.precision}")
    if train:
        print(f"  max_seq_length {train['max_seq_length']} × batch "
              f"{train['per_device_train_batch_size']} + gradient checkpointing: NO OOM")
        print(f"  peak resident {train['peak_resident_total_mib']:.0f} MiB total, "
              f"max single GPU {train['max_single_gpu_resident_mib']:.0f} MiB; "
              f"one card: {'YES' if _fits_one_card(train['after_step']) else 'NO (needs 2)'}")
        print(f"  steady-state step: {train['steady_step_seconds']:.2f}s "
              f"(all steps: {train['step_seconds']})")
        plain = train.get("no_gradient_checkpointing", {})
        if plain.get("oom"):
            print("  ⚠ WITHOUT gradient checkpointing: OOM — run_sft as written (2.1 sets no")
            print("    gradient_checkpointing) will NOT fit; 10.6 needs the flag or a smaller batch.")
        elif plain.get("measured"):
            print(f"  without gradient checkpointing (= run_sft as written): fits, peak "
                  f"{plain['peak_resident_total_mib']:.0f} MiB total, step "
                  f"{plain['steady_step_seconds']:.2f}s")
    else:
        print("  NOT MEASURED")

    # 11.2 leg 3 — batch-2 headroom. EVIDENCE ONLY: batch 1 is fixed by the parity clause, and
    # this leg exists so the writeup can say the constraint was a choice, not a hardware limit.
    headroom = fragments.get(f"train_{args.precision}_batch2")
    print(f"\n3b. BATCH-2 HEADROOM PROBE @ {args.precision} (evidence only — NOT adopted)")
    if not headroom:
        print("  NOT MEASURED")
    elif headroom.get("failed"):
        print(f"  DOES NOT FIT — {headroom['error'].splitlines()[0][:180]}")
    else:
        versus = (f" (vs batch 1: {train['steady_step_seconds']:.2f}s)" if train else "")
        print(f"  FITS: peak resident {headroom['peak_resident_total_mib']:.0f} MiB "
              f"({headroom['peak_resident_total_mib'] / 1024:.1f} GiB), step "
              f"{headroom['steady_step_seconds']:.2f}s{versus}")
    print("  Batch 1 is REQUIRED by the Phase-11 parity clause regardless of this result.")

    print(f"\n4. ONE DIVERSE-BEAM SL GENERATE (k=5) @ {args.precision}")
    if gen:
        print(f"  {gen['generate_seconds']:.1f}s for k={gen['k']} "
              f"(dp={gen['diversity_penalty']}), {gen['distinct_beams']} distinct beam(s)")
    else:
        print("  NOT MEASURED")

    # 11.2 leg 5 — the number that sizes 11.4's --gres.
    coloc = _colocation_block(fragments.get(f"load_{args.precision}") or gen, gen)
    print("\n5. THREE CO-LOCATED LOADS (C3 e2e) — build_condition3._device_maps()")
    if not coloc["measured"]:
        print("  NOT MEASURED (needs a successful load fragment)")
    else:
        print(f"  measured single load: {coloc['per_load_gib']:.1f} GiB   card: "
              f"{coloc['card_gib']:.1f} GiB")
        print(f"  _device_maps() pins SL -> cuda:0 and QG + AD -> cuda:1, so card 1 carries "
              f"2 × {coloc['per_load_gib']:.1f} = {coloc['two_on_one_card_gib']:.1f} GiB of "
              f"weights before any KV cache")
        print(f"  3 × load = {coloc['three_loads_gib']:.1f} GiB total across the pipeline")
        print(f"  decode headroom per model: {coloc['decode_headroom_gib']:.2f} GiB "
              f"— {coloc['decode_headroom_source']}")
        verdict = "FITS" if coloc["qg_plus_ad_fit_one_card"] else "DOES NOT FIT"
        print(f"  card 1 worst case = {coloc['two_on_one_card_gib']:.1f} weights + 2 × "
              f"{coloc['decode_headroom_gib']:.2f} decode = "
              f"{coloc['card1_worst_case_gib']:.1f} GiB vs {coloc['card_gib']:.1f} GiB: "
              f"{verdict} (margin {coloc['card1_margin_gib']:+.1f} GiB)")
        print(f"  -> the C3 e2e needs {coloc['gpus_needed_for_c3']} card(s) of this size "
              f"(11.4 sizes its --gres from this)")
        print("  CAVEAT: _device_maps() returns SL->cuda:0, QG+AD->cuda:1 for ANY device_count")
        print("          >= 2, so asking for a third card does NOT relieve card 1 on its own —")
        print("          spreading AD to cuda:2 would need a _device_maps() change (11.4's call).")

    print("\n6. RECOMMENDATION")
    budgets: dict[str, dict] = {}
    if train:
        infer_frag = fragments.get(f"load_{args.precision}")
        if not infer_frag or infer_frag.get("failed"):
            infer_frag = gen
        # Training GPU count = what the successful run's device_map actually spanned (a 4-bit
        # 32B base + training state does not fit one 32 GB card, so device_map="auto" shards it).
        n_train = len(train.get("gpus_used_by_device_map") or []) or (
            1 if _fits_one_card(train["after_step"]) else 2)
        card = _card_name(fragments)
        print(f"  precision      : {args.precision} (locked in config/models.yaml)")
        print(f"  training GPUs  : {n_train} × {card} "
              f"(batch {train['per_device_train_batch_size']}, gradient checkpointing ON)")
        if infer_frag:
            n_infer = 1 if _fits_one_card(infer_frag["after"]) else 2
            print(f"  inference GPUs : {n_infer} × {card}")
        else:
            print("  inference GPUs : NOT MEASURED")
        if coloc["measured"]:
            print(f"  C3 e2e GPUs    : {coloc['gpus_needed_for_c3']} × {card} (leg 5)")
        step_s = train["steady_step_seconds"]
        micro = train["per_device_train_batch_size"]
        print(f"  training budget from the measured {step_s:.2f}s/micro-step, profile "
              f"'{args.budget_profile}':")
        for label, path, epochs, adapters in BUDGET_PROFILES[args.budget_profile]:
            rows = _count_rows(path)
            if not rows:
                print(f"  {label:<24}: rows file {path} MISSING — budget not computed")
                continue
            steps = math.ceil(rows / micro) * epochs
            hours = steps * step_s / 3600
            budgets[label] = {"rows": rows, "epochs": epochs, "adapters": adapters,
                              "micro_steps": steps, "estimated_hours_per_adapter": round(hours, 1)}
            print(f"  {label:<24}: {rows} rows / batch {micro} × {epochs} epochs "
                  f"= {steps} micro-steps × {step_s:.2f}s ≈ {hours:.1f}h per adapter "
                  f"({'exceeds' if hours > JOB_HOUR_CAP else 'within'} the {JOB_HOUR_CAP}h job cap)")
        total_h = sum(b["estimated_hours_per_adapter"] * b["adapters"] for b in budgets.values())
        n_adapters = sum(b["adapters"] for b in budgets.values())
        print(f"  {n_adapters} adapters ≈ {total_h:.1f}h total GPU wall-clock")
        print("  NOTE: extrapolation assumes the measured single-GPU step time holds for every")
        print("        micro-batch (no eval, no checkpoint I/O) — treat it as a floor.")
    else:
        print("  BLOCKED — the train phase has no fragment; rerun --phase train.")

    payload = {
        "phase": "summary",
        "model_key": args.model_key,
        "locked_precision": args.precision,
        "budget_profile": args.budget_profile,
        "fragments": sorted(fragments),
        "training_budget": budgets,
        "colocation": coloc,
        "batch2_headroom": ({"measured": False} if not headroom else
                            {"measured": True, "fits": not headroom.get("failed"),
                             "peak_resident_total_mib": headroom.get("peak_resident_total_mib"),
                             "steady_step_seconds": headroom.get("steady_step_seconds"),
                             "error": headroom.get("error")}),
    }
    write_fragment("summary", payload)
    return payload


def main() -> None:
    global RESULTS_DIR                                  # noqa: PLW0603 — one CLI-set constant
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", required=True, choices=["load", "generate", "train", "summary"])
    ap.add_argument("--precision", default="4bit", choices=["4bit", "8bit", "fp16"],
                    help="On summary, the LOCKED precision the recommendation is written for.")
    ap.add_argument("--model_key", default="qwen2.5-32b")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--results_dir", default=str(RESULTS_DIR),
                    help="Where the JSON fragments live. Give a second model its own directory "
                         "so it does not overwrite the first model's measurements (11.2).")
    ap.add_argument("--tag", default="",
                    help="Suffix appended to this leg's fragment name, e.g. --tag batch2 for "
                         "11.2's batch-2 headroom probe beside the primary train fragment.")
    ap.add_argument("--budget_profile", default="mixed", choices=sorted(BUDGET_PROFILES),
                    help="Training recipe the summary extrapolates over (default: 10.5's).")
    ap.add_argument("--train_config", default="config/schema_linker_train_pole_external.yaml",
                    help="Supplies the LoRA/training hyperparameters the fit-test mirrors.")
    ap.add_argument("--train_rows", default="data/pole_ext_sl_train.jsonl",
                    help="Real SL rows to build the train batch from (10.2).")
    ap.add_argument("--benchmark", default="data/benchmark-pole-external.json")
    ap.add_argument("--item_index", type=int, default=0)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--diversity_penalty", type=float, default=1.0)
    ap.add_argument("--train_steps", type=int, default=3)
    ap.add_argument("--no_plain_leg", action="store_true",
                    help="Skip the no-gradient-checkpointing leg (run_sft as written).")
    ap.add_argument("--tolerate_failure", action="store_true",
                    help="Record a phase failure as a fragment and exit 0 (used for the 8-bit "
                         "leg, which may be unsupported on Volta) instead of raising.")
    ap.add_argument("--max_seq_length", type=int, default=None,
                    help="Override the train config's cap (default: use it).")
    ap.add_argument("--batch_size", type=int, default=None,
                    help="Override per_device_train_batch_size (default: use the train config).")
    args = ap.parse_args()
    RESULTS_DIR = Path(args.results_dir)

    if args.phase == "summary":
        phase_summary(args)
        return

    if not torch.cuda.is_available():
        raise SystemExit("No CUDA device — this probe must run on a GPU node "
                         "(v100-32gb for 10.5, rrifcs/h100 for 11.2).")
    entry = load_registry(args.models_config, args.model_key)
    print(f"model_key={args.model_key}  base={entry['base']}  dtype={entry['dtype']}  "
          f"target_modules={entry['target_modules']}  precision={args.precision}")
    print(f"GPUs visible: {torch.cuda.device_count()} — "
          f"{[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}")

    runner = {"load": phase_load, "generate": phase_generate, "train": phase_train}[args.phase]
    try:
        runner(args, entry)
    except Exception as exc:                                  # noqa: BLE001 — see below
        if not args.tolerate_failure:
            raise
        # A failure IS a result here: bitsandbytes 8-bit (LLM.int8) wants sm75+ and Kaya's
        # V100s are sm70, so the 8-bit leg may legitimately not run at all. Record it as
        # evidence and exit 0 so the remaining phases in the job still execute.
        print(f"\n⚠ {args.phase}/{args.precision} FAILED: {type(exc).__name__}: {exc}")
        write_fragment(fragment_name(args, f"{args.phase}_{args.precision}"), {
            "phase": args.phase, "precision": args.precision, "base": entry["base"],
            "failed": True, "error": f"{type(exc).__name__}: {exc}",
        })


if __name__ == "__main__":
    main()
