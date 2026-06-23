# experiments/build_condition1.py
"""Condition 1 builder: zero-shot baseline (base model only, no committed pattern)."""
from __future__ import annotations

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.types import SchemaRepr


def build_condition1(*, neo4j_uri: str, neo4j_auth: tuple, database_name, base_model_spec: dict,
                     schema: SchemaRepr) -> PipelineComponents:
    """Zero-shot baseline: the base model generates Cypher with no committed pattern.
    No Schema Linker, Ambiguity Detector, Disambiguator, or entity cache.
    base_model_spec e.g. {"backend": "huggingface", "model_name_or_path": "mistralai/Mistral-7B-v0.1"}.
    """
    base = build_llm(base_model_spec)
    return PipelineComponents.build(
        query_generator=QueryGenerator(base),
        schema_linker=None, ad_llm=None, dis_llm=None,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, use_prefilter=False, load_entity_cache=False,
    )
