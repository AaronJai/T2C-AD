"""Contract tests for the three condition builders (step 5.3, generalized for API backends).

No GPU/Neo4j: build_llm, PipelineComponents.build, SchemaLinker, and QueryGenerator
are monkeypatched, so the tests assert only the wiring each builder produces — which
specs are built (local HF or API), the SL decoding/beam_k, AD/Dis sharing, HF-only
device-pinning, and cache loading. Live model/DB loading is deferred to a Kaya run.

The builders are now SPEC-DRIVEN: run_evaluation (5.4) constructs full build_llm specs
(local HF base+adapter, or the same API spec for every stage) and the SL decoding block,
then passes them in. So the SL/QG backend is config-driven (an API model can run the whole
pipeline), not hardcoded HuggingFace.
"""
from __future__ import annotations

import pytest

import experiments.build_condition1 as c1mod
import experiments.build_condition2 as c2mod
import experiments.build_condition3 as c3mod
from pipeline.components import PipelineComponents


# ── Fakes ────────────────────────────────────────────────────────────────────────
class _BuiltLLM:
    """Stand-in for a BaseLLM; carries the spec it was built from."""

    def __init__(self, spec: dict) -> None:
        self.spec = spec


class _FakeSchemaLinker:
    def __init__(self, llm, beam_k=5, diversity_penalty=1.0, min_valid_beams=1,
                 *, decoding=None, prompt_style="completion") -> None:
        self.llm = llm
        self.beam_k = beam_k
        self.diversity_penalty = diversity_penalty
        self.decoding = decoding
        self.prompt_style = prompt_style


class _FakeQueryGenerator:
    def __init__(self, llm) -> None:
        self.llm = llm


class _Captured:
    """What PipelineComponents.build was called with."""

    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs


@pytest.fixture
def patched(monkeypatch):
    """Patch build_llm + the stage classes in every builder module, and the shared build()."""
    specs: list[dict] = []

    def fake_build_llm(spec: dict) -> _BuiltLLM:
        specs.append(spec)
        return _BuiltLLM(spec)

    def fake_build(cls, **kwargs):
        return _Captured(kwargs)

    for mod in (c1mod, c2mod, c3mod):
        monkeypatch.setattr(mod, "build_llm", fake_build_llm)
    for mod in (c2mod, c3mod):
        monkeypatch.setattr(mod, "SchemaLinker", _FakeSchemaLinker)
    for mod in (c1mod, c2mod, c3mod):
        monkeypatch.setattr(mod, "QueryGenerator", _FakeQueryGenerator)
    monkeypatch.setattr(PipelineComponents, "build", classmethod(fake_build))

    return specs


_SCHEMA = object()  # opaque SchemaRepr stand-in; builders only pass it through

# Representative specs, as run_evaluation builds them.
_HF = {"backend": "huggingface", "model_name_or_path": "base",
       "load_in_4bit": True, "torch_dtype": "float16"}
_HF_SL = {**_HF, "peft_adapter_path": "sl"}
_HF_QG = {**_HF, "peft_adapter_path": "qg"}
_API = {"backend": "anthropic", "model": "claude-sonnet-4-6"}
_BEAM = {"strategy": "beam", "diversity_penalty": 0.2, "k": 5}
_SAMPLE = {"strategy": "sample", "temperature": 0.7, "top_p": 0.95, "k": 5}


# ── build_condition1 (unchanged; already generic) ──────────────────────────────────
def test_condition1_single_model_no_extras(patched):
    specs = patched
    spec = {"backend": "huggingface", "model_name_or_path": "base"}
    out = c1mod.build_condition1(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model_spec=spec, schema=_SCHEMA,
    )
    assert len(specs) == 1                                  # exactly one model loaded
    assert specs[0] == spec
    kw = out.kwargs
    assert kw["schema_linker"] is None
    assert kw["ad_llm"] is None and kw["dis_llm"] is None
    assert kw["load_entity_cache"] is False
    assert kw["use_prefilter"] is False
    assert isinstance(kw["query_generator"], _FakeQueryGenerator)


# ── build_condition2 ───────────────────────────────────────────────────────────────
def test_condition2_builds_sl_qg_specs_beam1_no_disambig(patched):
    specs = patched
    out = c2mod.build_condition2(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
    )
    # Exactly the two specs handed in are built (SL then QG), verbatim.
    assert len(specs) == 2
    assert {s["peft_adapter_path"] for s in specs} == {"sl", "qg"}
    assert all(s["load_in_4bit"] is True and s["torch_dtype"] == "float16" for s in specs)
    kw = out.kwargs
    sl = kw["schema_linker"]
    assert isinstance(sl, _FakeSchemaLinker) and sl.beam_k == 1   # top-1, no distribution
    assert sl.prompt_style == "completion"                        # default (local path)
    assert kw["ad_llm"] is None and kw["dis_llm"] is None
    assert kw["load_entity_cache"] is False


def test_condition2_threads_instruct_prompt_style(patched):
    out = c2mod.build_condition2(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        sl_spec=dict(_API), qg_spec=dict(_API), schema=_SCHEMA, prompt_style="instruct",
    )
    assert out.kwargs["schema_linker"].prompt_style == "instruct"   # 8.2: API SL prompt


def test_condition2_accepts_api_specs(patched):
    specs = patched
    c2mod.build_condition2(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        sl_spec=dict(_API), qg_spec=dict(_API), schema=_SCHEMA,
    )
    # The SL/QG backend is config-driven: an API model can run C2 (no adapters, no quant).
    assert all(s["backend"] == "anthropic" for s in specs)
    assert all("peft_adapter_path" not in s and "load_in_4bit" not in s for s in specs)


# ── build_condition3 ───────────────────────────────────────────────────────────────
def test_condition3_beam_decoding_shared_addis_cache(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
    )
    kw = out.kwargs
    sl = kw["schema_linker"]
    assert isinstance(sl, _FakeSchemaLinker)
    assert sl.beam_k == 5 and sl.diversity_penalty == 0.2     # read from sl_decoding
    assert sl.decoding == _BEAM
    assert sl.prompt_style == "completion"                    # default (local path, byte-identical)
    assert kw["load_entity_cache"] is True
    # ad_spec=None, dis_spec=None → dis_llm shares the single AD instance.
    assert kw["dis_llm"] is kw["ad_llm"]


def test_condition3_sampling_decoding_for_api(patched):
    specs = patched
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_API), sl_spec=dict(_API), qg_spec=dict(_API), schema=_SCHEMA,
        sl_decoding=dict(_SAMPLE), prompt_style="instruct",
    )
    sl = out.kwargs["schema_linker"]
    assert sl.decoding["strategy"] == "sample" and sl.beam_k == 5
    assert sl.prompt_style == "instruct"                          # 8.2: API SL prompt
    # API specs carry no device_map even if GPUs are present (no local load).
    assert all("device_map" not in s for s in specs)
    # Default AD (ad_spec None) is the same API model as the base.
    assert out.kwargs["ad_llm"].spec["backend"] == "anthropic"


def test_condition3_dis_spec_distinct_backend(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
        dis_spec={"backend": "anthropic", "model": "claude"},
    )
    kw = out.kwargs
    assert kw["dis_llm"] is not kw["ad_llm"]
    assert kw["dis_llm"].spec["backend"] == "anthropic"


def test_condition3_ad_spec_overrides_backend(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
        ad_spec={"backend": "openai", "model": "gpt-4o"},
    )
    kw = out.kwargs
    # AD overridden, Dis defaults to sharing AD.
    assert kw["ad_llm"].spec["backend"] == "openai"
    assert kw["dis_llm"] is kw["ad_llm"]


# ── Specs passed through verbatim (run_evaluation owns quant/dtype) ─────────────────
def test_condition3_specs_passed_through_verbatim(patched):
    specs = patched
    c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
    )
    # SL/QG and the default-base AD all carry the quant the caller put in the specs.
    hf = [s for s in specs if s["backend"] == "huggingface"]
    assert len(hf) == 3
    assert all(s["load_in_4bit"] is True and s["torch_dtype"] == "float16" for s in hf)


# ── C3 device pinning (decisions-log 2026-06-26): pin HF loads across both V100s ─────
def test_condition3_pins_devices_when_two_gpus(patched, monkeypatch):
    """≥2 GPUs → SL alone on cuda:0, QG+default-AD on cuda:1 (HF specs only)."""
    import torch
    specs = patched
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 2)
    c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
    )
    by_adapter = {s.get("peft_adapter_path"): s for s in specs}
    assert by_adapter["sl"]["device_map"] == {"": 0}     # SL (beam_k=5 hog) owns cuda:0
    assert by_adapter["qg"]["device_map"] == {"": 1}
    assert by_adapter[None]["device_map"] == {"": 1}     # default base AD shares cuda:1


def test_condition3_no_pin_on_single_gpu(patched, monkeypatch):
    """1 GPU (or CPU) → no device_map injected; HuggingFaceLLM's 'auto' default applies."""
    import torch
    specs = patched
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
    )
    assert all("device_map" not in s for s in specs)


def test_condition3_caller_ad_spec_passed_through_without_device(patched, monkeypatch):
    import torch
    specs = patched
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 2)
    c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_spec=dict(_HF), sl_spec=dict(_HF_SL), qg_spec=dict(_HF_QG), schema=_SCHEMA,
        sl_decoding=dict(_BEAM),
        ad_spec={"backend": "anthropic", "model": "claude"},
    )
    api_specs = [s for s in specs if s["backend"] == "anthropic"]
    assert len(api_specs) == 1
    assert "device_map" not in api_specs[0]                  # API spec untouched
