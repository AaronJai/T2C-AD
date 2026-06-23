"""Contract tests for the three condition builders (step 5.3).

No GPU/Neo4j: build_llm, PipelineComponents.build, SchemaLinker, and QueryGenerator
are monkeypatched, so the tests assert only the wiring each builder produces (which
backends/specs are built, beam_k/diversity_penalty, AD/Dis sharing, cache loading).
Live model/DB loading (criterion 5) is deferred to a Kaya run — see the spec.
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
    def __init__(self, llm, beam_k=5, diversity_penalty=1.0, min_valid_beams=1) -> None:
        self.llm = llm
        self.beam_k = beam_k
        self.diversity_penalty = diversity_penalty


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


# ── Criterion 1: build_condition1 ──────────────────────────────────────────────────
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


# ── Criterion 2: build_condition2 ──────────────────────────────────────────────────
def test_condition2_two_hf_backends_beam1_no_disambig(patched):
    specs = patched
    out = c2mod.build_condition2(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model="base", sl_adapter="sl", qg_adapter="qg", schema=_SCHEMA,
    )
    # Two HF backends built: SL (sl adapter) and QG (qg adapter).
    assert len(specs) == 2
    assert all(s["backend"] == "huggingface" for s in specs)
    assert {s["peft_adapter_path"] for s in specs} == {"sl", "qg"}
    kw = out.kwargs
    sl = kw["schema_linker"]
    assert isinstance(sl, _FakeSchemaLinker) and sl.beam_k == 1
    assert kw["ad_llm"] is None and kw["dis_llm"] is None
    assert kw["load_entity_cache"] is False


# ── Criterion 3: build_condition3 ──────────────────────────────────────────────────
def test_condition3_beam5_penalty_shared_addis_cache(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model="base", sl_adapter="sl", qg_adapter="qg", schema=_SCHEMA,
        diversity_penalty=0.2,
    )
    kw = out.kwargs
    sl = kw["schema_linker"]
    assert isinstance(sl, _FakeSchemaLinker)
    assert sl.beam_k == 5 and sl.diversity_penalty == 0.2
    assert kw["load_entity_cache"] is True
    # ad_spec=None, dis_spec=None → dis_llm shares the single AD instance.
    assert kw["dis_llm"] is kw["ad_llm"]


def test_condition3_dis_spec_distinct_backend(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model="base", sl_adapter="sl", qg_adapter="qg", schema=_SCHEMA,
        diversity_penalty=1.0,
        dis_spec={"backend": "anthropic", "model": "claude"},
    )
    kw = out.kwargs
    assert kw["dis_llm"] is not kw["ad_llm"]
    assert kw["dis_llm"].spec["backend"] == "anthropic"


def test_condition3_ad_spec_overrides_backend(patched):
    out = c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model="base", sl_adapter="sl", qg_adapter="qg", schema=_SCHEMA,
        diversity_penalty=1.0,
        ad_spec={"backend": "openai", "model": "gpt-4o"},
    )
    kw = out.kwargs
    # AD overridden, Dis defaults to sharing AD.
    assert kw["ad_llm"].spec["backend"] == "openai"
    assert kw["dis_llm"] is kw["ad_llm"]


# ── Criterion 4: SL/QG backend is hardcoded HuggingFace (no swap point) ─────────────
def test_sl_qg_specs_always_huggingface(patched):
    specs = patched
    c3mod.build_condition3(
        neo4j_uri="bolt://x", neo4j_auth=("u", "p"), database_name=None,
        base_model="base", sl_adapter="sl", qg_adapter="qg", schema=_SCHEMA,
        diversity_penalty=0.5,
        ad_spec={"backend": "anthropic", "model": "claude"},
    )
    # The SL/QG specs (those carrying an adapter path) are always huggingface; the
    # builder hardcodes the backend, so a non-HF SL/QG cannot be requested.
    adapter_specs = [s for s in specs if "peft_adapter_path" in s]
    assert len(adapter_specs) == 2
    assert all(s["backend"] == "huggingface" for s in adapter_specs)
