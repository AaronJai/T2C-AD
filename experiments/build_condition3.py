# experiments/build_condition3.py
"""Condition 3 builder: disambiguation-enhanced (full pipeline, swappable backends)."""
from __future__ import annotations

from typing import Optional

from pipeline.components import PipelineComponents
from pipeline.llm import build_llm
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr


def _device_maps() -> tuple[object, object, object]:
    """(sl, qg, ad) device_map for three co-located HuggingFace 7B loads.

    With ≥2 visible GPUs, pin them explicitly instead of letting three independent
    `device_map="auto"` loads collide on one card (the C3 OOM, decisions-log 2026-06-26):
    the SL — the beam_k=5 group-beam KV-cache hog — gets cuda:0 to itself, QG + AD share
    cuda:1. On a single GPU (or CPU/tests), return None so the HuggingFaceLLM default
    ("auto") applies. Applied only to HuggingFace specs (see `_with_device`); an API run has
    no local load, so pinning is a no-op there.
    """
    import torch

    if torch.cuda.device_count() >= 2:
        return {"": 0}, {"": 1}, {"": 1}
    return None, None, None


def _with_device(spec: dict, device_map) -> dict:
    """Inject `device_map` into a HuggingFace spec only; API specs are returned untouched."""
    if device_map is not None and spec.get("backend") == "huggingface":
        return {**spec, "device_map": device_map}
    return spec


def build_condition3(*, neo4j_uri, neo4j_auth, database_name,
                     base_spec: dict, sl_spec: dict, qg_spec: dict, schema: SchemaRepr,
                     sl_decoding: dict,                         # locked SL decoding block (2.2)
                     ad_spec: Optional[dict] = None,            # build_llm spec; None → base_spec
                     dis_spec: Optional[dict] = None,           # None → share the AD backend
                     embedding_model=None,
                     entity_registry: Optional[list] = None,    # None → frozen v2; 7.3 passes v3
                     ad_system_prompt: Optional[str] = None,    # None → v2 default (PipelineComponents)
                     dis_system_prompt: Optional[str] = None,   # None → v2 default (PipelineComponents)
                     prompt_style: str = "completion",          # 8.2/Phase-8-follow-up: "instruct" for an API SL+QG
                     qg_include_properties: Optional[bool] = None,  # QG properties block override; None → from prompt_style
                     ) -> PipelineComponents:
    """Full pipeline. SL candidate distribution per `sl_decoding` (beam search for a local
    model, temperature sampling for an API model); QG; few-shot AD + Disambiguator.

    `sl_spec`/`qg_spec`/`base_spec` are full `build_llm` specs from run_evaluation (5.4):
    for a local model the HF base + the SL/QG adapters (carrying the registry 4-bit/dtype);
    for an API model the same API spec three times (no adapter). HF-only device-pinning is
    applied only to HuggingFace specs. A caller-supplied `ad_spec`/`dis_spec` is passed
    through verbatim; when `ad_spec` is None the Ambiguity Detector defaults to `base_spec`
    (the same model — one model the whole way through).

    `entity_registry`/`ad_system_prompt`/`dis_system_prompt` carry the dataset-version selection
    (7.3): run_evaluation passes the v3 registry + v3 prompts for a v3 run; None keeps the frozen
    v2 defaults baked into PipelineComponents (so an unversioned caller is byte-identical).

    `sl_decoding` keys: `strategy` ("beam"|"sample"), `k` (number of completions; default 5),
    `diversity_penalty` (beam), `temperature`/`top_p` (sample).
    """
    sl_dm, qg_dm, ad_dm = _device_maps()      # spread co-located HF loads across both V100s

    sl_llm = build_llm(_with_device(sl_spec, sl_dm))
    qg_llm = build_llm(_with_device(qg_spec, qg_dm))
    ad_llm = build_llm(ad_spec) if ad_spec else build_llm(_with_device(base_spec, ad_dm))
    dis_llm = build_llm(dis_spec) if dis_spec else ad_llm     # share if both default (stateless)

    beam_k = sl_decoding.get("k", 5)
    diversity_penalty = sl_decoding.get("diversity_penalty", 1.0)

    # Only pass the prompt kwargs when set, so None falls back to PipelineComponents' v2 defaults.
    prompt_kwargs = {}
    if ad_system_prompt is not None:
        prompt_kwargs["ad_system_prompt"] = ad_system_prompt
    if dis_system_prompt is not None:
        prompt_kwargs["dis_system_prompt"] = dis_system_prompt

    return PipelineComponents.build(
        query_generator=QueryGenerator(qg_llm, prompt_style=prompt_style,
                                       include_properties=qg_include_properties),
        schema_linker=SchemaLinker(sl_llm, beam_k=beam_k, diversity_penalty=diversity_penalty,
                                   decoding=sl_decoding, prompt_style=prompt_style),
        ad_llm=ad_llm, dis_llm=dis_llm,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, embedding_model=embedding_model,
        use_prefilter=False, load_entity_cache=True,
        entity_registry=entity_registry, **prompt_kwargs,
    )
