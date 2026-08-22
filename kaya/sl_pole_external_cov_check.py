"""Step 10.3 acceptance criterion 3 — quick intrinsic check of `sl_adapter_pole_external`.

NOT a pipeline module: a Kaya verification harness (the external-POLE sibling of
kaya/sl_v3_cov_check.py, 7.4). Loads the refreshed adapter
(checkpoints/{model_key}/sl_adapter_pole_external) on its base, regenerates diverse-beam
completions for a ~25-item stratified sample of the external-POLE benchmark, and reports the
sample Cov@5 (gold pattern present in the top-5 beams) — the fast sanity read before the full
10.4 G1 gate runs the same measure over all 100 items with a live-Neo4j-backed E2E run. GPU
only, no Neo4j needed (schema linking alone). Reuses experiments/probe_utils.py's
generate_beams/covered/gold_patterns (2.2/2.3) so the measure is identical to the one 10.4
gates on. Differs from the v3 sibling only in the schema (build_pole_external_schema_repr),
adapter path (sl_adapter_pole_external) and default benchmark (data/benchmark-pole-external.json).
"""
from __future__ import annotations

import argparse
import os
import sys

# Run from repo root so the experiments/ package (not pip-installed, unlike pipeline) imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from experiments.probe_utils import covered, generate_beams, gold_patterns
from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.schema import build_pole_external_schema_repr


def _sample(items_path: str, n: int = 25) -> list:
    """A stratified spread across ambiguity types, capped at n items."""
    by_type = items_by_type(load_benchmark(items_path))
    picks: list = []
    per_type = max(1, n // 5)
    for key in ("schema", "entity", "intent", "temporal", None):
        picks.extend(by_type.get(key, [])[:per_type])
    return picks[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-pole-external.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--sample_size", type=int, default=25)
    args = ap.parse_args()

    from pipeline.llm import HuggingFaceLLM

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        decoding_cfg = yaml.safe_load(fh)
    decoding = decoding_cfg.get("decoding", {}).get(
        args.model_key, {"strategy": "beam", "diversity_penalty": decoding_cfg["diversity_penalty"], "k": 5}
    )

    schema = build_pole_external_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    items = _sample(args.benchmark, args.sample_size)
    print(f"Sampled {len(items)}/{args.sample_size} external-POLE items; decoding={decoding}")

    llm = HuggingFaceLLM(
        model_name_or_path=registry["base"],
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter_pole_external",
        load_in_4bit=registry.get("load_in_4bit", True),
        torch_dtype=registry.get("dtype", "float16"),
    )

    hits = 0
    for item in items:
        beams = generate_beams(llm, item.question, schema_block, decoding)
        golds = gold_patterns(item)
        ok = covered(beams, golds)
        hits += ok
        print(f"[{item.question_id}] ({item.ambiguity_type or 'null'}) covered={ok}")
        print(f"    Q: {item.question}")
        print(f"    gold:  {golds}")
        for i, beam in enumerate(beams, 1):
            print(f"    beam{i}: {beam!r}")

    cov_at_5 = hits / len(items) if items else 0.0
    print(f"\nSample Cov@5 (sl_adapter_pole_external, n={len(items)}): {cov_at_5:.3f}")


if __name__ == "__main__":
    main()
