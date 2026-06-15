"""Step 3.4 acceptance criterion 5 — run ambiguity_detector end-to-end on a benchmark sample.

NOT a pipeline module: a Kaya verification harness. Builds the AD's two inputs faithfully —
a real CandidateMapping from the SchemaLinker (3.1, sl_adapter) and a real EntityLookupResult
from live Neo4j (3.2) — then calls ambiguity_detector with the base model as the AD BaseLLM
(few-shot prompted, no adapter) and prints the classifications for eyeballing.

Run inside a GPU job that also has Neo4j up on bolt://localhost:7687 (see kaya/45_ad_probe.slurm).
"""
from __future__ import annotations

import argparse
import os

import yaml

from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.schema import build_pole_schema_repr
from pipeline.types import CandidateMapping, EntityLookupResult


def _sample(items_path: str) -> list:
    """A few questions per ambiguity type (+ null) so all four AD paths are exercised."""
    by_type = items_by_type(load_benchmark(items_path))
    picks: list = []
    for key, n in (("schema", 2), ("entity", 2), ("temporal", 2), ("intent", 1), (None, 2)):
        picks.extend(by_type.get(key, [])[:n])
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-updated.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    args = ap.parse_args()

    import torch  # local import: only needed for the GPU run

    from pipeline.entity_lookup import EntityCache, entity_lookup
    from pipeline.llm import HuggingFaceLLM
    from pipeline.schema_linker.linker import SchemaLinker, SchemaLinkerError

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        diversity_penalty = yaml.safe_load(fh)["diversity_penalty"]

    base = registry["base"]
    dtype = registry.get("dtype", "float16")
    load_in_4bit = registry.get("load_in_4bit", True)

    schema = build_pole_schema_repr()
    items = _sample(args.benchmark)
    print(f"Sampled {len(items)} questions; base={base} dp={diversity_penalty}")

    # ── 1. Real CandidateMapping per question (SchemaLinker + sl_adapter) ──────────
    sl_llm = HuggingFaceLLM(
        model_name_or_path=base,
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter",
        load_in_4bit=load_in_4bit, torch_dtype=dtype,
    )
    linker = SchemaLinker(sl_llm, beam_k=5, diversity_penalty=diversity_penalty)
    mappings: dict[str, CandidateMapping] = {}
    for it in items:
        try:
            mappings[it.question_id] = linker.link(it.question, schema)
        except SchemaLinkerError as exc:
            print(f"  [{it.question_id}] SL produced no valid beams ({exc}); empty mapping")
            mappings[it.question_id] = CandidateMapping(question=it.question, mentions={})
    del sl_llm, linker
    torch.cuda.empty_cache()

    # ── 2. Real EntityLookupResult per question (live Neo4j) ──────────────────────
    import neo4j

    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    cache = EntityCache.load(driver)
    lookups: dict[str, EntityLookupResult] = {}
    for it in items:
        lookups[it.question_id] = entity_lookup(it.question, mappings[it.question_id], cache)
    driver.close()

    # ── 3. AD with the base model as the BaseLLM (no adapter) ──────────────────────
    ad_llm = HuggingFaceLLM(
        model_name_or_path=base, load_in_4bit=load_in_4bit, torch_dtype=dtype,
    )

    print("\n==================== AD CLASSIFICATIONS ====================")
    for it in items:
        res = ambiguity_detector(it.question, mappings[it.question_id], lookups[it.question_id], ad_llm)
        gold = it.ambiguity_type if it.is_ambiguous else "null"
        print(f"\n[{it.question_id}] {it.question}")
        print(f"  gold: is_ambiguous={it.is_ambiguous} type={gold}")
        print(f"  AD  : is_ambiguous={res.is_ambiguous} detected={res.detected_types}")
        print(f"  entropy: schema={res.schema_entropy:.2f} entity={res.entity_entropy:.2f}")
        print(f"  rationale: {res.llm_rationale[:200]}")


if __name__ == "__main__":
    main()
