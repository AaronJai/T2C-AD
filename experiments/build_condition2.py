# experiments/build_condition2.py
"""Condition 2 builder: schema-grounded (Schema Linker + Query Generator, no disambiguation)."""
from __future__ import annotations

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from typing import Optional

from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def build_condition2(*, neo4j_uri, neo4j_auth, database_name,
                     sl_spec: dict, qg_spec: dict, schema: SchemaRepr,
                     prompt_style: str = "completion",
                     qg_include_properties: Optional[bool] = None) -> PipelineComponents:
    """Schema Linker (beam_k=1 → top-1, no distribution) + Query Generator. No AD/Dis.

    `sl_spec`/`qg_spec` are full `build_llm` specs (run_evaluation, 5.4, builds them from the
    active model). For a local model they are HuggingFace base+adapter specs carrying the
    registry's 4-bit/dtype; for an API model they are the same API spec (no adapter). The SL
    runs at beam_k=1, so a single deterministic completion suffices on any backend — C2
    isolates the schema-grounding STAGE, not (for an API model) fine-tuning.

    `prompt_style` (8.2, extended to the QG as a Phase-8 follow-up) selects the SL *and* QG
    prompt: "completion" (default) for the local fine-tuned model — byte-identical to the
    pre-8.1/pre-follow-up path — or "instruct" for an API model, threaded in by run_evaluation
    from the registry `kind`.

    `qg_include_properties` overrides the QG's properties block only (the SL always gets it on
    every backend). None → derived from `prompt_style`, byte-identical to the pre-ablation path.
    """
    sl_llm = build_llm(sl_spec)
    qg_llm = build_llm(qg_spec)
    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm, prompt_style=prompt_style,
                                       include_properties=qg_include_properties),
        schema_linker=SchemaLinker(sl_llm, beam_k=1, prompt_style=prompt_style),
        ad_llm=None, dis_llm=None,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, use_prefilter=False, load_entity_cache=False,
    )
