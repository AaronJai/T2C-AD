"""10.4 Gate G1 — SL intrinsic coverage over ALL external-POLE questions (the linchpin gate).

NOT a pipeline module: a Kaya verification harness — the external-POLE sibling of
kaya/g1_sl_coverage_v3.py (7.5). Loads the 10.3 continue-SFT adapter
(checkpoints/{model_key}/sl_adapter_pole_external) on its base and decodes k=5 diverse beams over
the FULL external-POLE benchmark (data/benchmark-pole-external.json, 100 items), reporting Cov@5
(gold pattern present in the top-5 completions) and EM@1 (top-1 completion matches a gold pattern)
— the same intrinsic measure 3.1 reported, computed with the same structural
`covered()`/`_canonical_pattern` the live SL postprocessing accepts (direction- and
dangling-`--`-invariant). This is the full-100 confirmation of 10.3's 25-item sample Cov@5=0.840.

Gate rule (10.4/7.5): PROCEED to G2 if Cov@5 >= 0.60; below 0.60 STOP and iterate 10.2/10.3.
Target >= 0.85.

Side effect: caches the beams to results/beams_{model_key}_pole_external.jsonl in the SAME record
shape the 2.3 entropy probe uses (so a later probe can reuse them GPU-free).

10.7 addition: `--adapter_suffix ''` / `--no_adapter` select the generic Ozsoy-only adapter or no
adapter at all, so this harness can also produce the cheap intrinsic tier of the three-way
adapter attribution (no adapter / +generic / +generic+POLE) on this substrate. Both flags are
additive and default-preserving — the recorded 10.4 invocation is byte-identical.

No Neo4j (schema linking alone). GPU only. Reuses experiments/probe_utils.py verbatim so the
measure is byte-identical to the one the v3 and external cov-checks use. Differs from the v3 G1
harness only in the schema (build_pole_external_schema_repr), adapter suffix (_pole_external),
default benchmark and the output/cache tags.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Run as a bare file → put the repo root on sys.path so experiments/ imports (mirrors
# kaya/g1_sl_coverage_v3.py; see 7.4 handoff note on the ModuleNotFoundError shim).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from experiments.entropy_probe import cache_beams
from experiments.probe_utils import _canonical_pattern, covered, generate_beams, gold_patterns
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.schema import build_pole_external_schema_repr


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
    ap.add_argument("--benchmark", default="data/benchmark-pole-external.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--beam_cache", default=None,
                    help="default results/beams_{model_key}_pole_external.jsonl")
    ap.add_argument("--results", default=None,
                    help="default results/g1_sl_coverage_{model_key}_pole_external.json")
    ap.add_argument("--adapter_suffix", default="_pole_external",
                    help="Which SL adapter to load: default '_pole_external' (the in-domain "
                         "continue-SFT adapter this gate normally measures). Pass '' to load the "
                         "generic Ozsoy-only sl_adapter instead — the middle column of the "
                         "no-adapter / +generic / +generic+POLE attribution (10.7). Mirrors the "
                         "flag kaya/g1_sl_coverage_v3.py has carried since the 2026-07 v3 "
                         "ablation; added here by 10.7, default-preserving.")
    ap.add_argument("--no_adapter", action="store_true",
                    help="Load the raw base model with NO PEFT adapter at all — the first column "
                         "of that three-way attribution. Overrides --adapter_suffix.")
    args = ap.parse_args()

    from pipeline.llm import HuggingFaceLLM

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        decoding_cfg = yaml.safe_load(fh)
    # Reuse the locked decoding[mistral7b] block (beam, diversity_penalty 1.0, k=5) — the same
    # v3-locked penalty run_evaluation reads for this run (10.4 spec: sweep skipped for budget).
    decoding = decoding_cfg.get("decoding", {}).get(
        args.model_key,
        {"strategy": "beam", "diversity_penalty": decoding_cfg["diversity_penalty"], "k": 5},
    )

    schema = build_pole_external_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    items = load_benchmark(args.benchmark)
    print(f"Loaded {len(items)} external-POLE items; decoding={decoding}")

    adapter = (None if args.no_adapter
               else f"checkpoints/{args.model_key}/sl_adapter{args.adapter_suffix}")
    llm = HuggingFaceLLM(
        model_name_or_path=registry["base"],
        peft_adapter_path=adapter,
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

    cache_path = Path(args.beam_cache or f"results/beams_{args.model_key}_pole_external.jsonl")
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
        "dataset_version": "pole_external",
        "adapter": adapter,
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
    results_path = Path(args.results or f"results/g1_sl_coverage_{args.model_key}_pole_external.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n============ G1 SL COVERAGE (pole_external, n=%d) ============" % n)
    print(f"  Cov@5 = {cov_at_5:.3f}   EM@1 = {em_at_1:.3f}")
    print(f"  {'type':>9} | {'n':>3} | {'Cov@5':>6} | {'EM@1':>6}")
    for t, d in per_type.items():
        print(f"  {t:>9} | {d['n']:>3} | {d['cov_at_5']:>6.3f} | {d['em_at_1']:>6.3f}")
    verdict = ("PASS (>= 0.60) → proceed to G2" if cov_at_5 >= 0.60
               else "FAIL (< 0.60) → STOP, iterate 10.2/10.3")
    print(f"\n  GATE G1: {verdict}")
    print(f"  Cached beams → {cache_path}")
    print(f"  Summary → {results_path}")


if __name__ == "__main__":
    main()
