# experiments/diversity_penalty_sweep.py  --model_key {mistral7b|claude-sonnet|...}
"""Sweep the Schema Linker's diversity knob; pick the value with best entropy AUC under guardrails.

Backend-aware (the SL distribution mechanism differs by backend):
  - LOCAL (HuggingFace): sweep diverse-beam `diversity_penalty ∈ {0.2, 0.5, 1.0}`.
  - API   (OpenAI/Anthropic): sweep sampling `temperature ∈ {0.3, 0.7, 1.0}` (no beam groups).
Both score the same entropy→ambiguity signal on the POLE benchmark via the shared probe helpers
(probe_utils) decoding exactly as the live SL (3.1).

Outputs:
  - results/diversity_penalty_sweep_{model_key}.json   (per-value table + chosen decoding)
  - config/schema_linker_inference.yaml                 (decoding[<model_key>], read by 3.1/5.4)

A LOCAL sweep needs a GPU + the trained SL adapter (2.1); an API sweep needs an API key (no GPU).
The selection logic itself is pure (`select_penalty`/`_select_row`) and unit-tested offline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from experiments.probe_utils import (
    covered,
    generate_beams,
    gold_patterns,
    hallucinated,
    normalised_entropy,
    roc_auc,
)
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.llm import BaseLLM, HuggingFaceLLM, build_llm
from pipeline.schema import build_schema_repr
from pipeline.types import BenchmarkItem

PENALTIES = [0.2, 0.5, 1.0]        # local: diverse-beam diversity_penalty
TEMPERATURES = [0.3, 0.7, 1.0]     # api: sampling temperature
TOP_P = 0.95                        # api: nucleus cutoff held fixed while temperature is swept
BEAM_K = 5
COV_GUARDRAIL = 0.85       # success-criterion #5: gold pattern present in top-5 beams/samples


def candidate_decodings(kind: str) -> list[dict]:
    """The decoding blocks to sweep for a backend kind (the swept knob differs by backend)."""
    if kind == "api":
        return [{"strategy": "sample", "temperature": t, "top_p": TOP_P, "k": BEAM_K}
                for t in TEMPERATURES]
    return [{"strategy": "beam", "diversity_penalty": p, "k": BEAM_K} for p in PENALTIES]


def score_decoding(llm: BaseLLM, items: list[BenchmarkItem], schema_block: str,
                   valid_labels: set[str], valid_rels: set[str], decoding: dict) -> dict:
    """Run k=5 generation over all items at one decoding and aggregate the metrics.

    The row carries the full `decoding` block plus a flat `diversity_penalty` mirror (for the
    back-compat `select_penalty` on a local sweep)."""
    entropies: list[float] = []
    labels: list[bool] = []
    cov_flags: list[bool] = []
    hall_rates: list[float] = []
    for item in items:
        beams = generate_beams(llm, item.question, schema_block, decoding)
        entropies.append(normalised_entropy(beams))
        labels.append(item.is_ambiguous)
        cov_flags.append(covered(beams, gold_patterns(item)))
        hall_rates.append(hallucinated(beams, valid_labels, valid_rels))
    return {
        "decoding": decoding,
        "diversity_penalty": decoding.get("diversity_penalty"),
        "temperature": decoding.get("temperature"),
        "entropy_auc": roc_auc(entropies, labels),
        "cov_at_5": sum(cov_flags) / len(cov_flags),
        "hallucination_rate": sum(hall_rates) / len(hall_rates),
    }


def _select_row(rows: list[dict], value_label: str) -> tuple[dict, str]:
    """Core selection rule (2.2 §Selection), parameterised by the swept-value label.

    Among rows clearing the Cov@5 guardrail, choose the highest entropy AUC (the objective),
    breaking ties by lower hallucination. If none clears the guardrail, fall back to the best
    Cov@5/AUC trade-off and flag it so the caller records it in decisions-log.
    """
    qualified = [r for r in rows if r["cov_at_5"] >= COV_GUARDRAIL]
    if qualified:
        best = max(qualified, key=lambda r: (r["entropy_auc"], -r["hallucination_rate"]))
        reason = (
            f"Cov@5={best['cov_at_5']:.3f} ≥ {COV_GUARDRAIL}; highest entropy AUC "
            f"({best['entropy_auc']:.3f}) among {len(qualified)} qualifying {value_label}s."
        )
        return best, reason
    best = max(rows, key=lambda r: (r["cov_at_5"], r["entropy_auc"]))
    reason = (
        f"NO {value_label} cleared Cov@5 ≥ {COV_GUARDRAIL}; picked best Cov@5/AUC trade-off "
        f"(Cov@5={best['cov_at_5']:.3f}, AUC={best['entropy_auc']:.3f}). "
        f"RECORD THIS IN decisions-log.md."
    )
    return best, reason


def select_penalty(rows: list[dict]) -> tuple[float, str]:
    """Back-compat (local beam sweep): pick the diversity_penalty per the selection rule."""
    best, reason = _select_row(rows, "penalty")
    return best["diversity_penalty"], reason


def select_decoding(rows: list[dict], kind: str) -> tuple[dict, str]:
    """Pick the winning decoding block (generalized over backend kind)."""
    best, reason = _select_row(rows, "temperature" if kind == "api" else "penalty")
    return best["decoding"], reason


def write_results(rows: list[dict], chosen: dict, reason: str, path: Path) -> None:
    """Write the per-value table + chosen decoding to the results JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "beam_k": BEAM_K,
        "cov_guardrail": COV_GUARDRAIL,
        "values": rows,
        "chosen_decoding": chosen,
        "selection_reason": reason,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_inference_config(model_key: str, decoding: dict, path: Path) -> None:
    """Merge the locked decoding[model_key] block into config/schema_linker_inference.yaml.

    Preserves other models' entries; refreshes the legacy flat `diversity_penalty` mirror only
    when this model is a local beam sweep (back-compat for readers predating the per-model block).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dmap = dict(existing.get("decoding") or {})
    dmap[model_key] = decoding
    out: dict = {"decoding": dmap}
    if decoding.get("strategy") == "beam" and "diversity_penalty" in decoding:
        out["diversity_penalty"] = decoding["diversity_penalty"]
    elif "diversity_penalty" in existing:
        out["diversity_penalty"] = existing["diversity_penalty"]
    header = (
        "# config/schema_linker_inference.yaml\n"
        "# Locked Schema Linker decoding, selected by the 2.2 sweep, keyed per model_key:\n"
        "#   local → diverse-beam diversity_penalty; api → sampling temperature/top_p.\n"
        "# `k` is the number of completions. Read by 3.1 (via run_evaluation, 5.4) and the 2.3 probe.\n"
    )
    path.write_text(header + yaml.safe_dump(out, sort_keys=False), encoding="utf-8")


def _build_llm(entry: dict, model_key: str) -> tuple[BaseLLM, str]:
    """Construct the SL backend to sweep from a registry entry; return (llm, kind)."""
    kind = entry.get("kind", "local")
    if kind == "api":
        return build_llm({"backend": entry["backend"], "model": entry["model"]}), kind
    llm = HuggingFaceLLM(
        entry["base"],
        peft_adapter_path=f"checkpoints/{model_key}/sl_adapter",
        load_in_4bit=entry.get("load_in_4bit", False),
        torch_dtype=entry["dtype"],
    )
    return llm, kind


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--models", default="config/models.yaml")
    ap.add_argument("--benchmark", default="data/benchmark-updated.json")
    ap.add_argument("--dataset_version", default="v2", choices=["v2", "v3"],
                    help="Which schema repr to render for the SL prompt (v3 → concise schema).")
    ap.add_argument("--results_tag", default="",
                    help="Dataset tag suffixed into the sweep results name (e.g. v3); empty → today's name.")
    ap.add_argument("--results", default=None,
                    help="default results/diversity_penalty_sweep_{model_key}{_tag}.json")
    ap.add_argument("--inference_config", default="config/schema_linker_inference.yaml")
    args = ap.parse_args()

    # 1. Benchmark + the POLE schema block, rendered once.
    items = load_benchmark(args.benchmark)
    schema = build_schema_repr(args.dataset_version)
    schema_block = schema.to_prompt_string(include_properties=True)
    valid_labels = set(schema.node_labels)
    valid_rels = {p["type"] for p in schema.relationship_paths}

    # 2. Build the SL backend (local adapter or API model) from the registry.
    registry = yaml.safe_load(Path(args.models).read_text(encoding="utf-8"))
    if args.model_key not in registry:
        raise SystemExit(f"Unknown model_key '{args.model_key}'. Known: {list(registry)}")
    llm, kind = _build_llm(registry[args.model_key], args.model_key)

    # 3. Score each candidate decoding for this backend kind.
    decodings = candidate_decodings(kind)
    rows = [score_decoding(llm, items, schema_block, valid_labels, valid_rels, d)
            for d in decodings]

    # 4. Select + 5. write outputs.
    chosen, reason = select_decoding(rows, kind)
    tag = f"_{args.results_tag}" if args.results_tag else ""
    results = args.results or f"results/diversity_penalty_sweep_{args.model_key}{tag}.json"
    write_results(rows, chosen, reason, Path(results))
    write_inference_config(args.model_key, chosen, Path(args.inference_config))

    knob = "temperature" if kind == "api" else "penalty"
    print(f"{knob:>8} | {'entropy AUC':>11} | {'Cov@5':>6} | {'halluc.':>7}")
    for r in rows:
        val = r["temperature"] if kind == "api" else r["diversity_penalty"]
        print(f"{val:>8} | {r['entropy_auc']:>11.3f} | "
              f"{r['cov_at_5']:>6.3f} | {r['hallucination_rate']:>7.3f}")
    print(f"\nChosen decoding = {chosen}\n{reason}")


if __name__ == "__main__":
    main()
