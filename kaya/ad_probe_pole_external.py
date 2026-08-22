"""10.4 Gate G3 — external-POLE ambiguity-detector stratified probe (end-to-end, real backend).

NOT a pipeline module: a Kaya verification harness — the external-POLE sibling of
kaya/ad_probe_v3.py (7.5), re-grounded on the external substrate: the external-POLE schema repr,
the external benchmark, the external entity registry, the sl_adapter_pole_external SchemaLinker
(10.3), and the external AD system prompt (AD_SYSTEM_PROMPT_POLE_EXTERNAL, 9.3). Builds the AD's
two real inputs — a CandidateMapping from the SchemaLinker (3.1) and an EntityLookupResult from
live external Neo4j (3.2) — then calls ambiguity_detector over a stratified sample and prints
gold-vs-predicted so base-Mistral detection counts on this graph can be recorded.

AD backend is selectable so base-model AD vs an instruct/API AD can be compared:
  --ad_backend base                 (default) the active model's base as the AD BaseLLM
  --ad_backend api --ad_model KEY   an `kind: api` registry entry (needs its API key exported)

Run inside a GPU job that also has the external-POLE Neo4j up on bolt://localhost:7687
(kaya/99_ad_probe_pole_external.slurm).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT_POLE_EXTERNAL
from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.entity_lookup.registry import registry_for_version
from pipeline.schema import build_pole_external_schema_repr
from pipeline.types import CandidateMapping, EntityLookupResult


def _sample(items_path: str) -> list:
    """A stratified spread (2 per ambiguity type + 2 null) so all four AD paths are exercised."""
    by_type = items_by_type(load_benchmark(items_path))
    picks: list = []
    for key, n in (("schema", 2), ("entity", 2), ("temporal", 2), ("intent", 2), (None, 2)):
        picks.extend(by_type.get(key, [])[:n])
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-pole-external.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--ad_backend", choices=["base", "api"], default="base",
                    help="AD LLM: the local base (default) or an `kind: api` registry entry.")
    ap.add_argument("--ad_model", default=None,
                    help="registry key for --ad_backend api (e.g. claude-sonnet).")
    args = ap.parse_args()

    import torch

    from pipeline.entity_lookup import EntityCache, entity_lookup
    from pipeline.llm import HuggingFaceLLM, build_llm
    from pipeline.schema_linker.linker import SchemaLinker, SchemaLinkerError

    with open(args.models_config) as fh:
        all_registry = yaml.safe_load(fh)
    registry = all_registry[args.model_key]
    with open(args.sl_inference_config) as fh:
        sli = yaml.safe_load(fh)
    # SL leg reads the locked beam block (flat-dp fallback) — the same dp=1.0 run_evaluation uses.
    decoding = sli.get("decoding", {}).get(
        args.model_key,
        {"strategy": "beam", "diversity_penalty": sli["diversity_penalty"], "k": 5},
    )
    diversity_penalty = decoding.get("diversity_penalty", 1.0)

    base = registry["base"]
    dtype = registry.get("dtype", "float16")
    load_in_4bit = registry.get("load_in_4bit", True)

    schema = build_pole_external_schema_repr()
    ext_registry = registry_for_version("pole_external")
    items = _sample(args.benchmark)
    print(f"Sampled {len(items)} external-POLE questions; base={base} "
          f"sl_adapter=sl_adapter_pole_external decoding={decoding} ad_backend={args.ad_backend}")

    # ── 1. Real CandidateMapping per question (SchemaLinker + sl_adapter_pole_external) ────
    sl_llm = HuggingFaceLLM(
        model_name_or_path=base,
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter_pole_external",
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

    # ── 2. Real EntityLookupResult per question (live external Neo4j + external registry) ──
    import neo4j

    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    cache = EntityCache.load(driver, registry=ext_registry)
    lookups: dict[str, EntityLookupResult] = {}
    for it in items:
        lookups[it.question_id] = entity_lookup(it.question, mappings[it.question_id], cache)
    driver.close()

    # ── 3. AD with the selected backend and the external AD system prompt ─────────────────
    if args.ad_backend == "api":
        if not args.ad_model or args.ad_model not in all_registry:
            raise SystemExit(f"--ad_backend api needs a valid --ad_model. Known: {list(all_registry)}")
        entry = all_registry[args.ad_model]
        ad_llm = build_llm({"backend": entry["backend"], "model": entry["model"]})
        ad_desc = f"api:{args.ad_model}"
    else:
        ad_llm = HuggingFaceLLM(model_name_or_path=base, load_in_4bit=load_in_4bit, torch_dtype=dtype)
        ad_desc = f"base:{base}"

    print(f"\n============ AD CLASSIFICATIONS (pole_external, ad={ad_desc}) ============")
    n_correct = 0
    tp = fp = fn = tn = 0
    for it in items:
        res = ambiguity_detector(
            it.question, mappings[it.question_id], lookups[it.question_id], ad_llm,
            system_prompt=AD_SYSTEM_PROMPT_POLE_EXTERNAL,
        )
        gold = it.ambiguity_type if it.is_ambiguous else "null"
        correct = res.is_ambiguous == it.is_ambiguous
        n_correct += correct
        if it.is_ambiguous and res.is_ambiguous:
            tp += 1
        elif it.is_ambiguous and not res.is_ambiguous:
            fn += 1
        elif not it.is_ambiguous and res.is_ambiguous:
            fp += 1
        else:
            tn += 1
        print(f"\n[{it.question_id}] {it.question}")
        print(f"  gold: is_ambiguous={it.is_ambiguous} type={gold}")
        print(f"  AD  : is_ambiguous={res.is_ambiguous} detected={res.detected_types}")
        print(f"  entropy: schema={res.schema_entropy:.2f} entity={res.entity_entropy:.2f}")
        print(f"  rationale: {res.llm_rationale[:200]}")

    print(f"\n============ SUMMARY (pole_external, ad={ad_desc}) ============")
    print(f"  binary detection: correct {n_correct}/{len(items)}")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  (base-Mistral AD detection counts on the external graph; the API-AD swap is the")
    print(f"   documented path to higher recall — mirrors 3.4/7.5's finding.)")


if __name__ == "__main__":
    main()
