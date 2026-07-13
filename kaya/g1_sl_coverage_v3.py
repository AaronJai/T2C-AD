"""7.5 Gate G1 — SL intrinsic coverage over ALL 120 v3 questions (the linchpin gate).

NOT a pipeline module: a Kaya verification harness. Loads the v3 Schema Linker adapter
(checkpoints/{model_key}/sl_adapter_v3) on its base, regenerates k=5 diverse-beam completions
for every one of the 120 v3 benchmark items, and reports Cov@5 (gold pattern present in the
top-5 beams) and EM@1 (top-1 beam matches a gold pattern) — exactly the intrinsic measure 3.1
reported, computed with the same structural `covered()`/`_canonical_pattern` the live SL
postprocessing accepts (direction- and dangling-`--`-invariant; decisions-log 2026-07-10).

Gate rule (7.5): PROCEED if Cov@5 >= 0.60; below 0.60 STOP and iterate 7.4. Target >= 0.85.

Side effect: caches the beams to results/beams_{model_key}_v3.jsonl in the SAME record shape
the 2.3 entropy probe uses, so G2's probe reuses them GPU-free (the spec's named artefact).

GPU only, no Neo4j (schema linking alone). Reuses experiments/probe_utils.py verbatim so the
measure is byte-identical to the one G2's sweep gates on.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Run as a bare file → put the repo root on sys.path so experiments/ imports (mirrors
# kaya/sl_v3_cov_check.py; see 7.4 handoff note on the ModuleNotFoundError shim).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from experiments.entropy_probe import cache_beams
from experiments.probe_utils import _canonical_pattern, covered, generate_beams, gold_patterns
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.schema import build_pole_v3_schema_repr


def _em_at_1(beams: list[str], golds: list[str]) -> bool:
    """Top-1 beam matches a gold pattern (structural, same signature as covered())."""
    if not beams or not beams[0]:
        return False
    gold_sigs = {_canonical_pattern(g) for g in golds if g}
    try:
        return _canonical_pattern(beams[0]) in gold_sigs
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--beam_cache", default=None,
                    help="default results/beams_{model_key}_v3.jsonl (the spec's G1 artefact)")
    ap.add_argument("--results", default=None,
                    help="default results/g1_sl_coverage_{model_key}_v3.json")
    args = ap.parse_args()

    from pipeline.llm import HuggingFaceLLM

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        decoding_cfg = yaml.safe_load(fh)
    # Pre-sweep decoding: use the currently-locked block (G1 runs BEFORE G2 re-locks the penalty).
    decoding = decoding_cfg.get("decoding", {}).get(
        args.model_key,
        {"strategy": "beam", "diversity_penalty": decoding_cfg["diversity_penalty"], "k": 5},
    )

    schema = build_pole_v3_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    items = load_benchmark(args.benchmark)
    print(f"Loaded {len(items)} v3 items; decoding={decoding}")

    llm = HuggingFaceLLM(
        model_name_or_path=registry["base"],
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter_v3",
        load_in_4bit=registry.get("load_in_4bit", True),
        torch_dtype=registry.get("dtype", "float16"),
    )

    records: list[dict] = []
    cov_hits = 0
    em_hits = 0
    per_type_total: dict = defaultdict(int)
    per_type_cov: dict = defaultdict(int)
    per_type_em: dict = defaultdict(int)

    for item in items:
        beams = generate_beams(llm, item.question, schema_block, decoding)
        golds = gold_patterns(item)
        cov = covered(beams, golds)
        em = _em_at_1(beams, golds)
        cov_hits += cov
        em_hits += em
        t = item.ambiguity_type or "null"
        per_type_total[t] += 1
        per_type_cov[t] += cov
        per_type_em[t] += em
        records.append({
            "question_id": item.question_id,
            "is_ambiguous": item.is_ambiguous,
            "beams": beams,
        })
        print(f"[{item.question_id}] ({t}) cov={int(cov)} em={int(em)}")

    n = len(items)
    cov_at_5 = cov_hits / n if n else 0.0
    em_at_1 = em_hits / n if n else 0.0

    cache_path = Path(args.beam_cache or f"results/beams_{args.model_key}_v3.jsonl")
    cache_beams(records, cache_path)

    per_type = {
        t: {
            "n": per_type_total[t],
            "cov_at_5": per_type_cov[t] / per_type_total[t],
            "em_at_1": per_type_em[t] / per_type_total[t],
        }
        for t in sorted(per_type_total, key=lambda k: (k is None, k))
    }
    payload = {
        "model_key": args.model_key,
        "dataset_version": "v3",
        "adapter": f"checkpoints/{args.model_key}/sl_adapter_v3",
        "decoding": decoding,
        "n_items": n,
        "cov_at_5": cov_at_5,
        "em_at_1": em_at_1,
        "gate_threshold": 0.60,
        "gate_passed": cov_at_5 >= 0.60,
        "target": 0.85,
        "per_type": per_type,
        "beam_cache": str(cache_path),
    }
    results_path = Path(args.results or f"results/g1_sl_coverage_{args.model_key}_v3.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n==================== G1 SL COVERAGE (v3, n=%d) ====================" % n)
    print(f"  Cov@5 = {cov_at_5:.3f}   EM@1 = {em_at_1:.3f}")
    print(f"  {'type':>9} | {'n':>3} | {'Cov@5':>6} | {'EM@1':>6}")
    for t, d in per_type.items():
        print(f"  {t:>9} | {d['n']:>3} | {d['cov_at_5']:>6.3f} | {d['em_at_1']:>6.3f}")
    verdict = "PASS (>= 0.60) → proceed to G2" if cov_at_5 >= 0.60 else "FAIL (< 0.60) → STOP, iterate 7.4"
    print(f"\n  GATE G1: {verdict}")
    print(f"  Cached beams → {cache_path}")
    print(f"  Summary → {results_path}")


if __name__ == "__main__":
    main()
