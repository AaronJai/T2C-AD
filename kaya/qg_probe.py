"""Step 3.6 acceptance criterion 4 — run the Query Generator end-to-end on a benchmark sample.

NOT a pipeline module: a Kaya verification harness. Loads the trained QG adapter
(checkpoints/{model_key}/qg_adapter) on its base and runs QueryGenerator.generate over a
stratified benchmark sample in BOTH modes the QG must serve:

  * committed-pattern (Conditions 2 & 3): the committed SchemaMapping comes from a real
    SchemaLinker top-1 mapping (the orchestrator's unambiguous-bypass path), so cypher_syntax
    is a genuine pattern, not a hand-written one.
  * zero-shot (Condition 1): cypher_syntax="" so build_qg_prompt uses the zero-shot format.

The check is mechanical (criterion 4): generate runs over the questions and emits clean
MATCH…RETURN… Cypher. Intrinsic QG quality on the text2cypher split is an OPTIONAL informal
spot-check (per 2.1) — not reported here; the QG's contribution is demonstrated by C2-over-C1
on POLE in Phase 5. No Neo4j needed: the QG consumes a committed pattern + schema, not entity
lookups. The SL adapter is loaded only to source the committed pattern, then freed before the
QG adapter is loaded (the dis_probe two-model pattern), keeping a single 7B resident at a time.
"""
from __future__ import annotations

import argparse
import re

import yaml

from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.schema import build_pole_schema_repr
from pipeline.types import CandidateMapping, SchemaMapping

# No \b around the keywords: _clean_cypher's unescape can place a token (or a newline) flush
# against RETURN, and a word boundary there would spuriously fail (\n glued to RETURN, etc.).
_CLEAN_RE = re.compile(r"MATCH\b.*\bRETURN", re.IGNORECASE | re.DOTALL)


def _sample(items_path: str) -> list:
    """A spread across types so both ambiguous and unambiguous questions are exercised."""
    by_type = items_by_type(load_benchmark(items_path))
    picks: list = []
    for key, n in (("schema", 2), ("entity", 1), ("temporal", 1), ("intent", 1), (None, 3)):
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

    from pipeline.llm import HuggingFaceLLM
    from pipeline.query_generator.generator import QueryGenerator
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

    # ── 1. Real committed pattern per question (SchemaLinker top-1 → SchemaMapping) ──
    sl_llm = HuggingFaceLLM(
        model_name_or_path=base,
        peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter",
        load_in_4bit=load_in_4bit, torch_dtype=dtype,
    )
    linker = SchemaLinker(sl_llm, beam_k=5, diversity_penalty=diversity_penalty)
    committed: dict[str, SchemaMapping] = {}
    for it in items:
        try:
            committed[it.question_id] = linker.link(it.question, schema).top1_mapping()
        except (SchemaLinkerError, KeyError, IndexError) as exc:
            print(f"  [{it.question_id}] SL gave no committable top-1 ({exc}); zero-shot only")
            committed[it.question_id] = SchemaMapping(
                question=it.question, committed={}, cypher_syntax="", resolution_mode="automated",
            )
    del sl_llm, linker
    torch.cuda.empty_cache()

    # ── 2. Query Generator with the trained QG adapter (greedy) ─────────────────────
    qg_llm = HuggingFaceLLM(
        model_name_or_path=base,
        peft_adapter_path=f"checkpoints/{args.model_key}/qg_adapter",
        load_in_4bit=load_in_4bit, torch_dtype=dtype,
    )
    qg = QueryGenerator(qg_llm)

    print("\n==================== QUERY GENERATOR OUTPUT ====================")
    clean_committed = clean_zero_shot = 0
    for it in items:
        cm = committed[it.question_id]
        print(f"\n[{it.question_id}] ({it.ambiguity_type or 'null'}) {it.question}")

        cypher_c = qg.generate(it.question, cm, schema)
        ok_c = bool(_CLEAN_RE.search(cypher_c))
        clean_committed += ok_c
        print(f"  committed pattern: {cm.cypher_syntax or '(none → zero-shot)'}")
        print(f"  C2/C3 cypher [{'clean' if ok_c else 'CHECK'}]: {cypher_c!r}")

        zs = SchemaMapping(question=it.question, committed={}, cypher_syntax="",
                           resolution_mode="automated")
        cypher_z = qg.generate(it.question, zs, schema)
        ok_z = bool(_CLEAN_RE.search(cypher_z))
        clean_zero_shot += ok_z
        print(f"  C1 zero-shot cypher [{'clean' if ok_z else 'CHECK'}]: {cypher_z!r}")

    n = len(items)
    print(f"\nClean MATCH…RETURN: committed {clean_committed}/{n}, zero-shot {clean_zero_shot}/{n}.")


if __name__ == "__main__":
    main()
