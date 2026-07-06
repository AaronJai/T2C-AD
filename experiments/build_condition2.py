# experiments/build_condition2.py
"""Condition 2 builder: schema-grounded (Schema Linker + Query Generator, no disambiguation)."""
from __future__ import annotations

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def build_condition2(*, neo4j_uri, neo4j_auth, database_name,
                     sl_spec: dict, qg_spec: dict, schema: SchemaRepr) -> PipelineComponents:
    """Schema Linker (beam_k=1 → top-1, no distribution) + Query Generator. No AD/Dis.

    `sl_spec`/`qg_spec` are full `build_llm` specs (run_evaluation, 5.4, builds them from the
    active model). For a local model they are HuggingFace base+adapter specs carrying the
    registry's 4-bit/dtype; for an API model they are the same API spec (no adapter). The SL
    runs at beam_k=1, so a single deterministic completion suffices on any backend — C2
    isolates the schema-grounding STAGE, not (for an API model) fine-tuning.
    """
    sl_llm = build_llm(sl_spec)
    qg_llm = build_llm(qg_spec)
    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm),
        schema_linker=SchemaLinker(sl_llm, beam_k=1),
        ad_llm=None, dis_llm=None,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, use_prefilter=False, load_entity_cache=False,
    )
