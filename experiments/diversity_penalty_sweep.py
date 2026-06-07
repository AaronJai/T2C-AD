# experiments/diversity_penalty_sweep.py  --model_key mistral7b
"""Sweep diversity_penalty ∈ {0.2, 0.5, 1.0}; pick the value with best entropy AUC under guardrails.

Standalone, lightweight probe built directly on HuggingFaceLLM.generate (0.2) + the shared
probe helpers (probe_utils). It does NOT use the full 3.1 inference/postprocessing stack
(which doesn't exist yet) — it reproduces just enough diverse-beam handling to measure the
entropy→ambiguity signal on the POLE benchmark.

Outputs:
  - results/diversity_penalty_sweep.json     (per-penalty table + chosen value)
  - config/schema_linker_inference.yaml       (diversity_penalty: <chosen>, read by 3.1)

Running the sweep needs a GPU + the trained SL adapter (2.1). The selection logic itself is
pure (`select_penalty`) and unit-tested offline.
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
from pipeline.llm import HuggingFaceLLM
from pipeline.schema import build_pole_schema_repr
from pipeline.types import BenchmarkItem

PENALTIES = [0.2, 0.5, 1.0]
BEAM_K = 5
COV_GUARDRAIL = 0.85       # success-criterion #5: gold pattern present in top-5 beams


def score_penalty(llm: HuggingFaceLLM, items: list[BenchmarkItem], schema_block: str,
                  valid_labels: set[str], valid_rels: set[str],
                  penalty: float) -> dict:
    """Run k=5 diverse beam search over all items at one penalty and aggregate the metrics."""
    entropies: list[float] = []
    labels: list[bool] = []
    cov_flags: list[bool] = []
    hall_rates: list[float] = []
    for item in items:
        beams = generate_beams(llm, item.question, schema_block, BEAM_K, penalty)
        entropies.append(normalised_entropy(beams))
        labels.append(item.is_ambiguous)
        cov_flags.append(covered(beams, gold_patterns(item)))
        hall_rates.append(hallucinated(beams, valid_labels, valid_rels))
    return {
        "diversity_penalty": penalty,
        "entropy_auc": roc_auc(entropies, labels),
        "cov_at_5": sum(cov_flags) / len(cov_flags),
        "hallucination_rate": sum(hall_rates) / len(hall_rates),
    }


def select_penalty(rows: list[dict]) -> tuple[float, str]:
    """Pick the diversity_penalty per the selection rule (2.2 §Selection).

    Among penalties clearing the Cov@5 guardrail, choose the highest entropy AUC (the
    objective), breaking ties by lower hallucination. If none clears the guardrail, fall back
    to the best Cov@5/AUC trade-off and flag it so the caller records it in decisions-log.
    """
    qualified = [r for r in rows if r["cov_at_5"] >= COV_GUARDRAIL]
    if qualified:
        best = max(qualified, key=lambda r: (r["entropy_auc"], -r["hallucination_rate"]))
        reason = (
            f"Cov@5={best['cov_at_5']:.3f} ≥ {COV_GUARDRAIL}; highest entropy AUC "
            f"({best['entropy_auc']:.3f}) among {len(qualified)} qualifying penalties."
        )
        return best["diversity_penalty"], reason
    # Guardrail breached by all penalties — best trade-off, flagged for decisions-log.
    best = max(rows, key=lambda r: (r["cov_at_5"], r["entropy_auc"]))
    reason = (
        f"NO penalty cleared Cov@5 ≥ {COV_GUARDRAIL}; picked best Cov@5/AUC trade-off "
        f"(Cov@5={best['cov_at_5']:.3f}, AUC={best['entropy_auc']:.3f}). "
        f"RECORD THIS IN decisions-log.md."
    )
    return best["diversity_penalty"], reason


def write_results(rows: list[dict], chosen: float, reason: str, path: Path) -> None:
    """Write the per-penalty table + chosen value to results/diversity_penalty_sweep.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "beam_k": BEAM_K,
        "cov_guardrail": COV_GUARDRAIL,
        "penalties": rows,
        "chosen_diversity_penalty": chosen,
        "selection_reason": reason,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_inference_config(chosen: float, path: Path) -> None:
    """Write the locked diversity_penalty into config/schema_linker_inference.yaml (read by 3.1)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# config/schema_linker_inference.yaml\n"
        "# Locked Schema Linker inference parameters. `diversity_penalty` was selected by the\n"
        "# 2.2 sweep (max entropy AUC under the Cov@5 guardrail) and feeds 3.1's GenerationConfig.\n"
    )
    body = yaml.safe_dump({"diversity_penalty": chosen}, sort_keys=False)
    path.write_text(header + body, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--models", default="config/models.yaml")
    ap.add_argument("--benchmark", default="data/benchmark-updated.json")
    ap.add_argument("--results", default="results/diversity_penalty_sweep.json")
    ap.add_argument("--inference_config", default="config/schema_linker_inference.yaml")
    args = ap.parse_args()

    # 1. Benchmark + the POLE schema block, rendered once.
    items = load_benchmark(args.benchmark)
    schema = build_pole_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    valid_labels = set(schema.node_labels)
    valid_rels = {p["type"] for p in schema.relationship_paths}

    # 2. Load the SL adapter (2.1 namespaces it checkpoints/{model_key}/sl_adapter).
    registry = yaml.safe_load(Path(args.models).read_text(encoding="utf-8"))
    if args.model_key not in registry:
        raise SystemExit(f"Unknown model_key '{args.model_key}'. Known: {list(registry)}")
    m = registry[args.model_key]
    llm = HuggingFaceLLM(
        m["base"],
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter",
        load_in_4bit=m.get("load_in_4bit", False),
        torch_dtype=m["dtype"],
    )

    # 3. Score each penalty.
    rows = [
        score_penalty(llm, items, schema_block, valid_labels, valid_rels, penalty)
        for penalty in PENALTIES
    ]

    # 4. Select + 5. write outputs.
    chosen, reason = select_penalty(rows)
    write_results(rows, chosen, reason, Path(args.results))
    write_inference_config(chosen, Path(args.inference_config))

    print(f"{'penalty':>8} | {'entropy AUC':>11} | {'Cov@5':>6} | {'halluc.':>7}")
    for r in rows:
        print(f"{r['diversity_penalty']:>8} | {r['entropy_auc']:>11.3f} | "
              f"{r['cov_at_5']:>6.3f} | {r['hallucination_rate']:>7.3f}")
    print(f"\nChosen diversity_penalty = {chosen}\n{reason}")


if __name__ == "__main__":
    main()
