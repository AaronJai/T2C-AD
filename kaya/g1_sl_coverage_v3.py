"""7.5 Gate G1 — SL intrinsic coverage over ALL 120 v3 questions (the linchpin gate).

NOT a pipeline module: a Kaya verification harness. Resolves its Schema Linker from the
config/models.yaml entry for --model_key (8.2): a LOCAL model loads the v3 SL adapter
(checkpoints/{model_key}/sl_adapter_v3) on its base and decodes k=5 diverse beams; an
`kind: api` model uses `build_llm` on the API spec (no adapter, no GPU, no Neo4j) and decodes
k=5 temperature samples with the instruct SL prompt. For every one of the 120 v3 benchmark
items it reports Cov@5 (gold pattern present in the top-5 completions) and EM@1 (top-1
completion matches a gold pattern) — exactly the intrinsic measure 3.1 reported, computed with
the same structural `covered()`/`_canonical_pattern` the live SL postprocessing accepts
(direction- and dangling-`--`-invariant; decisions-log 2026-07-10).

Gate rule (7.5): PROCEED if Cov@5 >= 0.60; below 0.60 STOP and iterate 7.4. Target >= 0.85.

Side effect: caches the beams to results/beams_{model_key}_v3.jsonl in the SAME record shape
the 2.3 entropy probe uses, so G2's probe reuses them GPU-free (the spec's named artefact).

No Neo4j (schema linking alone). GPU only for the local path; the API path is GPU-free. Reuses
experiments/probe_utils.py verbatim so the measure is byte-identical to the one G2's sweep gates on.
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
    ap.add_argument("--decoding", default=None,
                    help="JSON decoding override, e.g. "
                         "'{\"strategy\":\"sample\",\"temperature\":0.7,\"k\":5}'. "
                         "API models default to sampling temperature 0.7 (pre-sweep, mirrors "
                         "7.5's pre-sweep dp=0.2); local models read the currently-locked block.")
    ap.add_argument("--adapter_suffix", default="_v3",
                    help="Which SL adapter to load for a local model: default '_v3' "
                         "(sl_adapter_v3, the 7.4 in-domain-SFT adapter this gate normally "
                         "measures). Pass '' to load the pre-7.4 generic-Ozsoy-only sl_adapter "
                         "instead, for the schema-redesign-vs-in-domain-SFT ablation (see "
                         "decisions-log). No effect on an API model (no adapter).")
    ap.add_argument("--no_adapter", action="store_true",
                    help="Load the raw base model with NO PEFT adapter at all (not even the "
                         "generic-Ozsoy one) — the third point of the no-FT / generic-FT / "
                         "in-domain-FT ablation. Overrides --adapter_suffix. No effect on an "
                         "API model (already adapter-free).")
    args = ap.parse_args()

    from pipeline.llm import build_llm

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        decoding_cfg = yaml.safe_load(fh)
    kind = registry.get("kind", "local")

    # Decoding: an explicit --decoding override wins. Else an API model defaults to pre-sweep
    # temperature sampling (0.7, k=5); a local model uses the currently-locked block (G1 runs
    # BEFORE G2 re-locks the penalty).
    if args.decoding:
        decoding = json.loads(args.decoding)
    elif kind == "api":
        decoding = {"strategy": "sample", "temperature": 0.7, "k": 5}
    else:
        decoding = decoding_cfg.get("decoding", {}).get(
            args.model_key,
            {"strategy": "beam", "diversity_penalty": decoding_cfg["diversity_penalty"], "k": 5},
        )
    # Instruct SL prompt for an API model (8.1/8.2); completion prompt for the local fine-tuned SL.
    prompt_style = "instruct" if kind == "api" else "completion"

    schema = build_pole_v3_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    items = load_benchmark(args.benchmark)
    print(f"Loaded {len(items)} v3 items; kind={kind} decoding={decoding} "
          f"prompt_style={prompt_style}")

    if kind == "api":
        # API path: build_llm on the API spec (no adapter, no GPU, no Neo4j).
        llm = build_llm({"backend": registry["backend"], "model": registry["model"]})
        adapter = None
    else:
        from pipeline.llm import HuggingFaceLLM
        adapter = None if args.no_adapter else f"checkpoints/{args.model_key}/sl_adapter{args.adapter_suffix}"
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
        beams = generate_beams(llm, item.question, schema_block, decoding,
                               prompt_style=prompt_style)
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
        "kind": kind,
        "adapter": adapter,
        "decoding": decoding,
        "prompt_style": prompt_style,
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
