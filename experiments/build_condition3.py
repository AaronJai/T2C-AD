# experiments/build_condition3.py
"""Condition 3 builder: disambiguation-enhanced (full pipeline, swappable AD/Dis backends)."""
from __future__ import annotations

from typing import Optional

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def build_condition3(*, neo4j_uri, neo4j_auth, database_name, base_model: str,
                     sl_adapter: str, qg_adapter: str, schema: SchemaRepr,
                     diversity_penalty: float,                  # locked value from 2.2
                     ad_spec: Optional[dict] = None,            # build_llm spec; None → base model
                     dis_spec: Optional[dict] = None,           # None → share the AD backend
                     embedding_model=None) -> PipelineComponents:
    """Full pipeline. SL beam_k=5 diverse beam search at the locked diversity_penalty; SFT QG;
    few-shot AD + Disambiguator (swappable backends). Entity cache loaded.
    """
    sl_llm = build_llm({"backend": "huggingface", "model_name_or_path": base_model,
                        "peft_adapter_path": sl_adapter})
    qg_llm = build_llm({"backend": "huggingface", "model_name_or_path": base_model,
                        "peft_adapter_path": qg_adapter})
    ad_llm = build_llm(ad_spec) if ad_spec else build_llm(
        {"backend": "huggingface", "model_name_or_path": base_model})
    dis_llm = build_llm(dis_spec) if dis_spec else ad_llm     # share if both default (stateless)

    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm),
        schema_linker=SchemaLinker(sl_llm, beam_k=5, diversity_penalty=diversity_penalty),
        ad_llm=ad_llm, dis_llm=dis_llm,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, embedding_model=embedding_model,
        use_prefilter=False, load_entity_cache=True,
    )
