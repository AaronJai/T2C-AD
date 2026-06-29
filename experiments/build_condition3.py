# experiments/build_condition3.py
"""Condition 3 builder: disambiguation-enhanced (full pipeline, swappable AD/Dis backends)."""
from __future__ import annotations

from typing import Optional

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def _device_maps() -> tuple[object, object, object]:
    """(sl, qg, ad) device_map for the three internally-built 7B loads.

    With ≥2 visible GPUs, pin them explicitly instead of letting three independent
    `device_map="auto"` loads collide on one card (the C3 OOM, decisions-log 2026-06-26):
    the SL — the beam_k=5 group-beam KV-cache hog — gets cuda:0 to itself, QG + AD share
    cuda:1. On a single GPU (or CPU/tests), return None so the HuggingFaceLLM default
    ("auto") applies — the 4-bit trio (~14 GB) targets the one card as before.
    """
    import torch

    if torch.cuda.device_count() >= 2:
        return {"": 0}, {"": 1}, {"": 1}
    return None, None, None


def build_condition3(*, neo4j_uri, neo4j_auth, database_name, base_model: str,
                     sl_adapter: str, qg_adapter: str, schema: SchemaRepr,
                     diversity_penalty: float,                  # locked value from 2.2
                     ad_spec: Optional[dict] = None,            # build_llm spec; None → base model
                     dis_spec: Optional[dict] = None,           # None → share the AD backend
                     load_in_4bit: bool = False,                # registry-driven (5.4); QLoRA fit on 16 GB
                     torch_dtype: str = "bfloat16",
                     embedding_model=None) -> PipelineComponents:
    """Full pipeline. SL beam_k=5 diverse beam search at the locked diversity_penalty; SFT QG;
    few-shot AD + Disambiguator (swappable backends). Entity cache loaded.

    `load_in_4bit`/`torch_dtype` come from config/models.yaml via run_evaluation (5.4) and apply
    only to the internally-built HF loads (SL/QG and the default base AD/Dis); a caller-supplied
    `ad_spec`/`dis_spec` is passed through verbatim. Without 4-bit the three full 7B loads OOM a
    32 GB (2×16 GB V100) node — see decisions-log 2026-06-23.
    """
    quant = {"load_in_4bit": load_in_4bit, "torch_dtype": torch_dtype}
    sl_dm, qg_dm, ad_dm = _device_maps()      # spread the three loads across both V100s

    def _hf(extra: dict, device_map) -> dict:
        spec = {"backend": "huggingface", "model_name_or_path": base_model, **extra, **quant}
        if device_map is not None:
            spec["device_map"] = device_map
        return spec

    sl_llm = build_llm(_hf({"peft_adapter_path": sl_adapter}, sl_dm))
    qg_llm = build_llm(_hf({"peft_adapter_path": qg_adapter}, qg_dm))
    ad_llm = build_llm(ad_spec) if ad_spec else build_llm(_hf({}, ad_dm))
    dis_llm = build_llm(dis_spec) if dis_spec else ad_llm     # share if both default (stateless)

    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm),
        schema_linker=SchemaLinker(sl_llm, beam_k=5, diversity_penalty=diversity_penalty),
        ad_llm=ad_llm, dis_llm=dis_llm,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, embedding_model=embedding_model,
        use_prefilter=False, load_entity_cache=True,
    )
