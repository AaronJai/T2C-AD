"""Step 3.5 acceptance criterion 6 — run the disambiguator end-to-end on a benchmark sample.

NOT a pipeline module: a Kaya verification harness. Builds the disambiguator's inputs
faithfully — a real CandidateMapping from the SchemaLinker (3.1, sl_adapter) and a real
EntityLookupResult from live Neo4j (3.2) — then calls disambiguator with the base model as the
dis BaseLLM (few-shot prompted, no adapter) on the AMBIGUOUS subset, and confirms it commits a
SchemaMapping. It also exercises the retry path: a second call with the first commitment in
previously_tried must commit a *different* interpretation (or None once candidates are exhausted).

The AmbiguityResult is constructed from the gold annotation (detected_types = [gold type]) — the
unit under test is the disambiguator, not the AD (whose flat-entropy behaviour is documented in
3.4). Run inside a GPU job that also has Neo4j up on bolt://localhost:7687 (see kaya/47_dis_probe.slurm).
"""
from __future__ import annotations

import argparse
import os

import yaml

from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.disambiguator.disambiguator import disambiguator
from pipeline.schema import build_pole_schema_repr
from pipeline.types import AmbiguityResult, CandidateMapping, EntityLookupResult, SchemaMapping


def _sample(items_path: str) -> list:
    """A few ambiguous questions per type so all four disambiguation paths are exercised."""
    by_type = items_by_type(load_benchmark(items_path))
    picks: list = []
    for key, n in (("schema", 2), ("entity", 2), ("temporal", 2), ("intent", 1)):
        picks.extend(by_type.get(key, [])[:n])
    return picks


def _ambiguity_result(item) -> AmbiguityResult:
    """Build an AmbiguityResult carrying the gold ambiguity type (probe drives the disambiguator
    directly; the AD's own classification is evaluated separately in 3.4 / 4.2)."""
    types = [item.ambiguity_type] if item.ambiguity_type else []
    return AmbiguityResult(
        is_ambiguous=True, detected_types=types,
        schema_entropy=0.0, entity_entropy=0.0,
        llm_rationale="(probe: gold type injected)",
    )


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
    print(f"Sampled {len(items)} ambiguous questions; base={base} dp={diversity_penalty}")

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

    # ── 3. Disambiguator with the base model as the BaseLLM (no adapter) ───────────
    dis_llm = HuggingFaceLLM(
        model_name_or_path=base, load_in_4bit=load_in_4bit, torch_dtype=dtype,
    )

    print("\n==================== DISAMBIGUATOR COMMITMENTS ====================")
    committed_count = 0
    for it in items:
        amb = _ambiguity_result(it)
        previously_tried: list[SchemaMapping] = []
        print(f"\n[{it.question_id}] {it.question}")
        print(f"  gold type: {it.ambiguity_type}")
        # First commitment, then one retry with the first in previously_tried.
        for attempt in (1, 2):
            sm = disambiguator(
                it.question, amb, mappings[it.question_id], lookups[it.question_id],
                dis_llm, previously_tried,
            )
            if sm is None:
                print(f"  attempt {attempt}: None (candidates exhausted)")
                break
            print(f"  attempt {attempt}: committed_pattern = {sm.cypher_syntax}")
            if attempt == 1:
                committed_count += 1
            previously_tried.append(sm)

    print(f"\nCommitted a SchemaMapping for {committed_count}/{len(items)} sampled questions.")


if __name__ == "__main__":
    main()
