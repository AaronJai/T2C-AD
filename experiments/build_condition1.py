# experiments/build_condition1.py
"""Condition 1 builder: zero-shot baseline (base model only, no committed pattern)."""
from __future__ import annotations

from typing import Optional

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.types import SchemaRepr


def build_condition1(*, neo4j_uri: str, neo4j_auth: tuple, database_name, base_model_spec: dict,
                     schema: SchemaRepr,
                     qg_include_properties: Optional[bool] = None,
                     qg_few_shot: Optional[str] = None) -> PipelineComponents:
    """Zero-shot baseline: the base model generates Cypher with no committed pattern.
    No Schema Linker, Ambiguity Detector, Disambiguator, or entity cache.
    base_model_spec e.g. {"backend": "huggingface", "model_name_or_path": "mistralai/Mistral-7B-v0.1"}.

    `qg_include_properties` overrides the QG's properties block; None keeps the prompt_style
    default (False here), byte-identical to the pre-2026-07-17 path. Unlike the SL/QG *adapter*
    ablation — to which C1 is structurally invariant (it loads no adapter) — C1 IS affected by
    this one: it still renders a schema block, and that block was missing its Properties list.
    Note the Ozsoy corpus this zero-shot format claims comparability with is itself
    property-rich (90.3% of `data/ozsoy_qg_train.jsonl` rows), so properties=True is the
    setting that actually honours C1's stated rationale.
    """
    base = build_llm(base_model_spec)
    return PipelineComponents.build(
        query_generator=QueryGenerator(base, include_properties=qg_include_properties,
                                       few_shot_override=qg_few_shot),
        schema_linker=None, ad_llm=None, dis_llm=None,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, use_prefilter=False, load_entity_cache=False,
    )
