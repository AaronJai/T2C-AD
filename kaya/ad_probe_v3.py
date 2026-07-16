"""7.5 Gate G3 — v3 ambiguity-detector stratified probe (end-to-end, real backend).

NOT a pipeline module: a Kaya verification harness — the v3 analogue of kaya/ad_probe.py
(3.4 criterion 5), re-grounded on the v3 substrate: v3 schema repr, v3 benchmark, v3 entity
registry, the sl_adapter_v3 SchemaLinker, and the v3 AD system prompt (AD_SYSTEM_PROMPT_V3).
Builds the AD's two real inputs — a CandidateMapping from the SchemaLinker (3.1) and an
EntityLookupResult from live Neo4j (3.2) — then calls ambiguity_detector over a stratified
sample and prints gold-vs-predicted so the detector's behaviour on healthy (post-7.4) beam
diversity + non-zero entropy can be eyeballed and counted.

AD backend is selectable so the spec's "base-model AD vs instruct/API AD" pair can be run:
  --ad_backend base                 (default) the active model's base as the AD BaseLLM
  --ad_backend api --ad_model KEY   an `kind: api` registry entry (needs its API key exported)

Run inside a GPU job that also has the v3 Neo4j up on bolt://localhost:7687 (kaya/80_ad_probe_v3.slurm).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT_V3
from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.entity_lookup.registry import registry_for_version
from pipeline.schema import build_pole_v3_schema_repr
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
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--ad_backend", choices=["base", "api"], default="base",
                    help="AD LLM: the local base (default) or an `kind: api` registry entry.")
    ap.add_argument("--ad_model", default=None,
                    help="registry key for --ad_backend api (e.g. claude-sonnet).")
    ap.add_argument("--adapter_suffix", default="_v3",
                    help="Which SL adapter to load for a local SL: default '_v3' (the 7.4 "
                         "in-domain-SFT adapter this gate normally measures). Pass '' for the "
                         "pre-7.4 generic-Ozsoy-only sl_adapter, or a path ending in "
                         "'_v3_noadapter'-style sentinel handled below, for the schema-vs-SFT "
                         "detection ablation (decisions-log). No effect on an API SL.")
    ap.add_argument("--no_sl_adapter", action="store_true",
                    help="Load the raw base model as the SL with NO PEFT adapter at all. "
                         "Overrides --adapter_suffix. No effect on an API SL.")
    args = ap.parse_args()

    import torch

    from pipeline.entity_lookup import EntityCache, entity_lookup
    from pipeline.llm import HuggingFaceLLM, build_llm
    from pipeline.schema_linker.linker import SchemaLinker, SchemaLinkerError

    with open(args.models_config) as fh:
        all_registry = yaml.safe_load(fh)
    registry = all_registry[args.model_key]
    sl_kind = registry.get("kind", "local")
    with open(args.sl_inference_config) as fh:
        sli = yaml.safe_load(fh)
    # Decoding for the SL leg, kind-aware: a local model reads the locked beam block (flat-dp
    # fallback); an `kind: api` model reads its sampling block, defaulting to pre-sweep temp 0.7.
    if sl_kind == "api":
        decoding = sli.get("decoding", {}).get(
            args.model_key, {"strategy": "sample", "temperature": 0.7, "k": 5})
    else:
        decoding = sli.get("decoding", {}).get(
            args.model_key,
            {"strategy": "beam", "diversity_penalty": sli["diversity_penalty"], "k": 5},
        )
    diversity_penalty = decoding.get("diversity_penalty", 0.2)

    base = registry.get("base")
    dtype = registry.get("dtype", "float16")
    load_in_4bit = registry.get("load_in_4bit", True)

    schema = build_pole_v3_schema_repr()
    v3_registry = registry_for_version("v3")
    items = _sample(args.benchmark)
    sl_adapter_desc = "none" if args.no_sl_adapter else f"sl_adapter{args.adapter_suffix}"
    print(f"Sampled {len(items)} v3 questions; sl_kind={sl_kind} base={base} sl_adapter="
          f"{sl_adapter_desc} decoding={decoding} ad_backend={args.ad_backend}")

    # ── 1. Real CandidateMapping per question (SchemaLinker) ──────────────────────────
    # SL leg resolves from the registry (8.2): local → the HF sl_adapter_v3 with beam decoding;
    # `kind: api` → build_llm on the API spec with temperature-sampling decoding + instruct prompt.
    if sl_kind == "api":
        sl_llm = build_llm({"backend": registry["backend"], "model": registry["model"]})
        linker = SchemaLinker(sl_llm, beam_k=decoding.get("k", 5), decoding=decoding,
                              prompt_style="instruct")
    else:
        sl_adapter = None if args.no_sl_adapter else f"checkpoints/{args.model_key}/sl_adapter{args.adapter_suffix}"
        sl_llm = HuggingFaceLLM(
            model_name_or_path=base,
            peft_adapter_path=sl_adapter,
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
    if sl_kind != "api":
        torch.cuda.empty_cache()

    # ── 2. Real EntityLookupResult per question (live v3 Neo4j + v3 registry) ─────────
    import neo4j

    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    cache = EntityCache.load(driver, registry=v3_registry)
    lookups: dict[str, EntityLookupResult] = {}
    for it in items:
        lookups[it.question_id] = entity_lookup(it.question, mappings[it.question_id], cache)
    driver.close()

    # ── 3. AD with the selected backend and the v3 AD system prompt ──────────────────
    if args.ad_backend == "api":
        if not args.ad_model or args.ad_model not in all_registry:
            raise SystemExit(f"--ad_backend api needs a valid --ad_model. Known: {list(all_registry)}")
        entry = all_registry[args.ad_model]
        ad_llm = build_llm({"backend": entry["backend"], "model": entry["model"]})
        ad_desc = f"api:{args.ad_model}"
    else:
        if base is None:
            raise SystemExit(
                f"--ad_backend base needs a local base, but model_key '{args.model_key}' is "
                f"`kind: api` (no `base`). Use --ad_backend api --ad_model <key> for an API AD.")
        ad_llm = HuggingFaceLLM(model_name_or_path=base, load_in_4bit=load_in_4bit, torch_dtype=dtype)
        ad_desc = f"base:{base}"

    print(f"\n============ AD CLASSIFICATIONS (v3, ad={ad_desc}) ============")
    n_correct = 0
    tp = fp = fn = tn = 0
    for it in items:
        res = ambiguity_detector(
            it.question, mappings[it.question_id], lookups[it.question_id], ad_llm,
            system_prompt=AD_SYSTEM_PROMPT_V3,
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

    print(f"\n============ SUMMARY (v3, ad={ad_desc}) ============")
    print(f"  binary detection: correct {n_correct}/{len(items)}")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  non-zero schema_entropy on ambiguous items is the 7.4/7.3 signal G3 checks for.")


if __name__ == "__main__":
    main()
