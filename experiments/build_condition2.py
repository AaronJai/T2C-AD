# experiments/build_condition2.py
"""Condition 2 builder: schema-grounded (SFT Schema Linker + Query Generator, no disambiguation)."""
from __future__ import annotations

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def build_condition2(*, neo4j_uri, neo4j_auth, database_name, base_model: str,
                     sl_adapter: str, qg_adapter: str, schema: SchemaRepr) -> PipelineComponents:
    """SFT Schema Linker (beam_k=1 → top-1, no distribution) + SFT Query Generator. No AD/Dis."""
    sl_llm = build_llm({"backend": "huggingface", "model_name_or_path": base_model,
                        "peft_adapter_path": sl_adapter})
    qg_llm = build_llm({"backend": "huggingface", "model_name_or_path": base_model,
                        "peft_adapter_path": qg_adapter})
    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm),
        schema_linker=SchemaLinker(sl_llm, beam_k=1),
        ad_llm=None, dis_llm=None,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, use_prefilter=False, load_entity_cache=False,
    )
