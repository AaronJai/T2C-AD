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
    """(sl, qg, ad) device_map for three co-located HuggingFace loads.

    With ≥2 visible GPUs, pin them explicitly instead of letting three independent
    `device_map="auto"` loads collide on one card (the C3 OOM, decisions-log 2026-06-26):
    the SL — the beam_k=5 group-beam KV-cache hog — gets cuda:0 to itself, QG + AD share
    cuda:1. On a single GPU (or CPU/tests), return None so the HuggingFaceLLM default
    ("auto") applies. Applied only to HuggingFace specs (see `_with_device`); an API run has
    no local load, so pinning is a no-op there.

    **≥3 GPUs → AD gets its own card (11.4).** Sharing card 1 was comfortable while a 4-bit
    load was 20.2 GiB (32B, 10.5) — 20 GiB on card 0, 40 GiB on card 1 of a 93.6 GiB H100 NVL.
    At the 72B's MEASURED 42.5 GiB per 4-bit load (11.2 leg 1, job 1144935) card 1 would hold
    ~85 GiB of weights before any KV cache, and C3 runs `beam_k=5` group beams: 11.2 leg 5 put
    the worst case at 90.4 GiB of 93.1, i.e. it fits on 2 cards with only ~2.7 GiB of margin.
    Spreading AD to `cuda:2` is what makes the extra cards the 11.4 G4 runners request actually
    relieve card 1 — 11.2 recorded that a third card was inert until this arm existed. Those
    runners ask for FOUR cards, not three, and the reason is a load the pinning does not control:
    `run_evaluation.main()` holds C1's and C2's models alive while C3 builds, so six 4-bit loads
    (~249 GiB) are resident at the peak. A measured probe put the 3-card case at OOM and the
    4-card case at 66.5 / 69.2 / 69.1 GiB on the pinned cards (jobs 1148895 / 1148924); this
    function is unchanged either way, since at `device_count() == 4` it still returns (0, 1, 2)
    and card 3 is the spill space `device_map="auto"` uses for C1/C2. See decisions-log.

    The 2-GPU and 1-GPU returns are deliberately byte-identical to the pre-11.4 function, so
    every earlier run's device placement is reproducible (guarded by
    tests/test_condition_builders.py — the "gate the new behaviour, freeze the old" pattern
    10.6 used for `gradient_checkpointing`).
    """
    import torch

    count = torch.cuda.device_count()
    if count >= 3:
        return {"": 0}, {"": 1}, {"": 2}
    if count >= 2:
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
                     qg_few_shot: Optional[str] = None,         # 9.4: dataset-specific QG few-shot override
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
    sl_dm, qg_dm, ad_dm = _device_maps()      # spread the co-located HF loads across the visible GPUs

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
                                       include_properties=qg_include_properties,
                                       few_shot_override=qg_few_shot),
        schema_linker=SchemaLinker(sl_llm, beam_k=beam_k, diversity_penalty=diversity_penalty,
                                   decoding=sl_decoding, prompt_style=prompt_style),
        ad_llm=ad_llm, dis_llm=dis_llm,
        neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database_name,
        schema=schema, embedding_model=embedding_model,
        use_prefilter=False, load_entity_cache=True,
        entity_registry=entity_registry, **prompt_kwargs,
    )
