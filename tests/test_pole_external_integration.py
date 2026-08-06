"""Tests for the 9.3 external-POLE pipeline integration (config-switched; v2/v3 byte-identical).

Mirrors tests/test_v3_integration.py's structure for the third dataset_version branch. No
GPU/Neo4j: a FakeLLM captures the system turn, a FakeDriver stands in for the entity-cache
load, and run_evaluation.resolve_dataset is exercised directly (criterion 3 — resolved without
loading any model). Criterion 1's v2/v3 regression guard is the byte-identity asserts below.
"""
from __future__ import annotations

import json

import pytest

import experiments.run_evaluation as rev
from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.ambiguity.prompts import (AD_SYSTEM_PROMPT, AD_SYSTEM_PROMPT_POLE_EXTERNAL,
                                        AD_SYSTEM_PROMPT_V3)
from pipeline.disambiguator.disambiguator import _parse_disambiguator_output, disambiguator
from pipeline.disambiguator.prompts import (DIS_SYSTEM_PROMPT, DIS_SYSTEM_PROMPT_POLE_EXTERNAL,
                                            DIS_SYSTEM_PROMPT_V3)
from pipeline.entity_lookup.cache import EntityCache
from pipeline.entity_lookup.registry import (ENTITY_REGISTRY, ENTITY_REGISTRY_POLE_EXTERNAL,
                                             ENTITY_REGISTRY_V3, registry_for_version)
from pipeline.llm import Completion, GenerationConfig
from pipeline.query_generator.generator import QueryGenerator
from pipeline.query_generator.prompts import (_QG_FEW_SHOT_API, _QG_FEW_SHOT_API_POLE_EXTERNAL,
                                              build_qg_prompt_api)
from pipeline.schema import adapter_suffix_for_version
from pipeline.types import AmbiguityResult, CandidateMapping, EntityLookupResult, SchemaMapping


# ── Fakes ───────────────────────────────────────────────────────────────────────────────
class _CapturingLLM:
    """Records the system message it is handed; returns a fixed JSON completion."""

    def __init__(self, reply: str):
        self.reply = reply
        self.system_seen: str | None = None

    def generate_chat(self, messages, config: GenerationConfig):
        self.system_seen = next(m["content"] for m in messages if m["role"] == "system")
        return [Completion(text=self.reply, score=0.0, rank=1)]


class _FakeSession:
    def __init__(self, queries_seen):
        self._queries = queries_seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query):
        self._queries.append(query)
        return iter(())          # no rows — we only assert which labels were queried


class _FakeDriver:
    def __init__(self):
        self.queries_seen: list[str] = []

    def session(self, **kwargs):
        return _FakeSession(self.queries_seen)


# ── Entity registry (touch point 2) ───────────────────────────────────────────────────────
def test_registry_for_version_pole_external() -> None:
    reg = registry_for_version("pole_external")
    assert reg is ENTITY_REGISTRY_POLE_EXTERNAL
    labels = {e["label"] for e in reg}
    assert labels == {"Person", "Officer", "Location"}
    # Excluded per the exact-identifier exclusion rule: Vehicle/Phone/Email/PostCode/Area/
    # Crime/PhoneCall/Object.
    for excluded in ("Vehicle", "Phone", "Email", "PostCode", "Area", "Crime", "PhoneCall", "Object"):
        assert excluded not in labels
    # v2/v3 registries untouched by the new key (regression guard, criterion 1).
    assert registry_for_version("v2") is ENTITY_REGISTRY
    assert registry_for_version("v3") is ENTITY_REGISTRY_V3


def test_location_keyed_by_address_not_none() -> None:
    """User-decided 2026-08-05: Location has no single id property in this schema, so it is
    keyed by `address` (zero EntityCache.load changes) rather than a null id_prop."""
    entry = next(e for e in ENTITY_REGISTRY_POLE_EXTERNAL if e["label"] == "Location")
    assert entry["id_prop"] == "address"
    assert entry["id_prop"] is not None


def test_entity_cache_load_uses_pole_external_registry() -> None:
    driver = _FakeDriver()
    EntityCache.load(driver, registry=ENTITY_REGISTRY_POLE_EXTERNAL)
    queried_labels = [q.split("(n:`")[1].split("`")[0] for q in driver.queries_seen]
    assert queried_labels == ["Person", "Officer", "Location"]
    # The Location query reads `address` as node_id (no None-id crash).
    location_query = driver.queries_seen[queried_labels.index("Location")]
    assert "n.`address` AS node_id" in location_query


# ── AD/Dis prompt selection (touch points 3–4) ─────────────────────────────────────────────
def _empty_inputs():
    cm = CandidateMapping(question="q", mentions={})
    el = EntityLookupResult(question="q", entity_mentions={})
    return cm, el


def test_pole_external_prompts_are_distinct_and_grounded() -> None:
    assert AD_SYSTEM_PROMPT_POLE_EXTERNAL != AD_SYSTEM_PROMPT
    assert AD_SYSTEM_PROMPT_POLE_EXTERNAL != AD_SYSTEM_PROMPT_V3
    assert DIS_SYSTEM_PROMPT_POLE_EXTERNAL != DIS_SYSTEM_PROMPT
    assert DIS_SYSTEM_PROMPT_POLE_EXTERNAL != DIS_SYSTEM_PROMPT_V3
    # Real external schema labels present; v2/v3-only labels absent.
    assert "Officer" in AD_SYSTEM_PROMPT_POLE_EXTERNAL and "PhoneCall" in AD_SYSTEM_PROMPT_POLE_EXTERNAL
    for dropped in ("Incident", "Organisation", "Evidence", "Communication"):
        assert dropped not in AD_SYSTEM_PROMPT_POLE_EXTERNAL
    # The SCHEMA few-shot uses the digital-comm axis (KNOWS_SN vs KNOWS_PHONE), not the
    # non-divergent KNOWS-family broad-vs-narrow framing (9.2 amendment).
    assert "KNOWS_SN" in AD_SYSTEM_PROMPT_POLE_EXTERNAL and "KNOWS_PHONE" in AD_SYSTEM_PROMPT_POLE_EXTERNAL
    # Real seed data grounds the few-shots (9.1/9.2 sessions, no invented data).
    assert "Andrea George" in AD_SYSTEM_PROMPT_POLE_EXTERNAL          # entity
    assert "Nettles Worthy" in AD_SYSTEM_PROMPT_POLE_EXTERNAL         # intent (I01)
    assert "BL1" in AD_SYSTEM_PROMPT_POLE_EXTERNAL                    # temporal (T16)
    # Temporal rule is rewritten for this graph's lack of active/from_date/to_date edge state.
    assert "no active/from_date/to_date" in DIS_SYSTEM_PROMPT_POLE_EXTERNAL
    assert "SAME-DAY" in DIS_SYSTEM_PROMPT_POLE_EXTERNAL


def test_detector_uses_injected_pole_external_prompt() -> None:
    cm, el = _empty_inputs()
    llm = _CapturingLLM('{"is_ambiguous": false, "detected_types": [], "rationale": "x"}')
    ambiguity_detector("q", cm, el, llm, system_prompt=AD_SYSTEM_PROMPT_POLE_EXTERNAL)
    assert llm.system_seen == AD_SYSTEM_PROMPT_POLE_EXTERNAL

    # Regression guard: default (no system_prompt kwarg) stays v2, byte-identical.
    llm2 = _CapturingLLM('{"is_ambiguous": false, "detected_types": [], "rationale": "x"}')
    ambiguity_detector("q", cm, el, llm2)
    assert llm2.system_seen == AD_SYSTEM_PROMPT


def test_disambiguator_uses_injected_pole_external_prompt() -> None:
    cm, el = _empty_inputs()
    ar = AmbiguityResult(is_ambiguous=True, detected_types=["schema"], schema_entropy=0.9,
                         entity_entropy=0.0, llm_rationale="", threshold_schema=0.6,
                         threshold_entity=0.8)
    llm = _CapturingLLM('{"committed_pattern": null, "rationale": "x"}')
    disambiguator("q", ar, cm, el, llm, previously_tried=[],
                  system_prompt=DIS_SYSTEM_PROMPT_POLE_EXTERNAL)
    assert llm.system_seen == DIS_SYSTEM_PROMPT_POLE_EXTERNAL

    llm2 = _CapturingLLM('{"committed_pattern": null, "rationale": "x"}')
    disambiguator("q", ar, cm, el, llm2, previously_tried=[])   # default → v2, byte-identical
    assert llm2.system_seen == DIS_SYSTEM_PROMPT


# ── run_evaluation.resolve_dataset (touch point 5; acceptance criteria 1 & 3) ──────────────
def test_resolve_dataset_pole_external() -> None:
    """Resolved without loading any model or touching the network (criterion 3)."""
    cfg = {"dataset_version": "pole_external", "results_tag": "pole_external_local",
          "benchmark": "data/benchmark-pole-external.json"}
    ds = rev.resolve_dataset(cfg)
    assert ds["dataset_version"] == "pole_external"
    assert len(ds["schema"].node_labels) == 11
    assert len(ds["schema"].relationship_paths) == 17
    assert {e["label"] for e in ds["entity_registry"]} == {"Person", "Officer", "Location"}
    assert ds["ad_system_prompt"] is AD_SYSTEM_PROMPT_POLE_EXTERNAL
    assert ds["dis_system_prompt"] is DIS_SYSTEM_PROMPT_POLE_EXTERNAL
    assert ds["adapter_suffix"] == "_pole_external"
    assert ds["results_tag"] == "pole_external_local"
    assert ds["benchmark"] == "data/benchmark-pole-external.json"


def test_resolve_dataset_v2_v3_unaffected_by_pole_external_branch() -> None:
    """Regression guard (criterion 1): adding the third branch doesn't change v2/v3 output."""
    v2 = rev.resolve_dataset({"benchmark": "data/benchmark-updated.json"})
    assert v2["dataset_version"] == "v2"
    assert v2["ad_system_prompt"] is AD_SYSTEM_PROMPT
    assert v2["dis_system_prompt"] is DIS_SYSTEM_PROMPT
    assert v2["adapter_suffix"] == ""

    v3 = rev.resolve_dataset({"dataset_version": "v3", "benchmark": "data/benchmark-v3.json"})
    assert v3["dataset_version"] == "v3"
    assert v3["ad_system_prompt"] is AD_SYSTEM_PROMPT_V3
    assert v3["dis_system_prompt"] is DIS_SYSTEM_PROMPT_V3
    assert v3["adapter_suffix"] == "_v3"


def test_resolve_dataset_unknown_version_raises() -> None:
    with pytest.raises(SystemExit):
        rev.resolve_dataset({"dataset_version": "nope", "benchmark": "x.json"})


def test_adapter_suffix_for_version_pole_external() -> None:
    assert adapter_suffix_for_version("pole_external") == "_pole_external"
    assert adapter_suffix_for_version("v2") == ""               # regression guard
    assert adapter_suffix_for_version("v3") == "_v3"             # regression guard


def test_resolve_model_specs_pole_external_api_carries_no_adapter() -> None:
    """The API model this step runs never reads adapter_suffix, but the suffix must still
    resolve without raising if a future local model were pointed at pole_external (spec note)."""
    base_api, sl_api, qg_api, kind_api = rev._resolve_model_specs(
        {"kind": "api", "backend": "anthropic", "model": "claude-sonnet-4-6"},
        "claude-sonnet", "_pole_external")
    assert kind_api == "api"
    assert "peft_adapter_path" not in sl_api and "peft_adapter_path" not in qg_api

    _, sl_local, qg_local, kind_local = rev._resolve_model_specs(
        {"base": "mistralai/Mistral-7B-v0.3", "dtype": "float16", "load_in_4bit": True},
        "mistral7b", "_pole_external")
    assert kind_local == "local"
    assert sl_local["peft_adapter_path"] == "checkpoints/mistral7b/sl_adapter_pole_external"
    assert qg_local["peft_adapter_path"] == "checkpoints/mistral7b/qg_adapter_pole_external"


# ── 9.4: temporal fix — AD 5th few-shot (touch point 1, criterion 2) ──────────────────────
def test_ad_pole_external_has_five_few_shots_covering_both_temporal_mechanisms() -> None:
    assert AD_SYSTEM_PROMPT_POLE_EXTERNAL.count("### Example") == 5
    assert "most-recent" in AD_SYSTEM_PROMPT_POLE_EXTERNAL.lower()
    assert "9-(776)276-2772" in AD_SYSTEM_PROMPT_POLE_EXTERNAL   # Q-POLE-T05 grounding


# ── 9.4: temporal fix — Dis few-shots embed the resolved decision (criterion 3) ────────────
def test_dis_pole_external_temporal_few_shots_embed_resolved_clause() -> None:
    assert DIS_SYSTEM_PROMPT_POLE_EXTERNAL.count("### Example") == 5
    assert "WHERE toInteger(split(c.date,'/')[0]) = 15" in DIS_SYSTEM_PROMPT_POLE_EXTERNAL
    assert "CALLER|CALLED" in DIS_SYSTEM_PROMPT_POLE_EXTERNAL
    assert "ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1" in DIS_SYSTEM_PROMPT_POLE_EXTERNAL


@pytest.mark.parametrize("committed_pattern", [
    "(c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) "
    "WHERE toInteger(split(c.date,'/')[0]) = 11",
    "(ph:Phone)<-[:CALLER|CALLED]-(pc:PhoneCall) "
    "WHERE toInteger(split(pc.call_date,'/')[0]) >= 2 AND toInteger(split(pc.call_date,'/')[0]) <= 8",
    "(p1:Phone)<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone) "
    "ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1",
])
def test_dis_temporal_committed_pattern_parses_and_survives_verbatim(committed_pattern) -> None:
    """Criterion 3: fed through a fake LLM returning each new example's expected
    committed_pattern, _parse_disambiguator_output must not raise, and the resulting
    SchemaMapping.cypher_syntax must contain the WHERE/ORDER BY/LIMIT text verbatim."""
    cm, _ = _empty_inputs()
    text = json.dumps({"committed_pattern": committed_pattern, "rationale": "x"})
    result = _parse_disambiguator_output(text, "q", cm, [])
    assert isinstance(result, SchemaMapping)
    assert result.cypher_syntax == committed_pattern
    for clause in ("WHERE", "ORDER BY", "LIMIT"):
        if clause in committed_pattern:
            assert clause in result.cypher_syntax


# ── 9.4: QG few-shot branch (touch points 5–6, criterion 4) ────────────────────────────────
def test_qg_few_shot_api_pole_external_is_distinct_and_grounded() -> None:
    assert _QG_FEW_SHOT_API_POLE_EXTERNAL != _QG_FEW_SHOT_API
    assert "toInteger(split(" in _QG_FEW_SHOT_API_POLE_EXTERNAL
    assert "CALLER|CALLED" in _QG_FEW_SHOT_API_POLE_EXTERNAL
    assert "call_date" in _QG_FEW_SHOT_API_POLE_EXTERNAL and "call_time" in _QG_FEW_SHOT_API_POLE_EXTERNAL


def test_build_qg_prompt_api_default_is_byte_identical_to_pre_9_4() -> None:
    """v2/v3 regression guard (criterion 1): no few_shot override -> untouched output."""
    with_override = build_qg_prompt_api("q", "schema", few_shot=None)
    without_arg = build_qg_prompt_api("q", "schema")
    assert with_override == without_arg
    assert _QG_FEW_SHOT_API in without_arg
    assert "copy that" not in without_arg.lower()


def test_build_qg_prompt_api_with_override_uses_new_few_shot_and_instruction() -> None:
    rendered = build_qg_prompt_api("q", "schema", committed_pattern="(a)-[:R]->(b) WHERE x = 1",
                                   few_shot=_QG_FEW_SHOT_API_POLE_EXTERNAL)
    assert _QG_FEW_SHOT_API_POLE_EXTERNAL in rendered
    assert _QG_FEW_SHOT_API not in rendered.replace(_QG_FEW_SHOT_API_POLE_EXTERNAL, "")
    assert "copy that" in rendered.lower()


class _FakeQGLLM:
    def __init__(self):
        self.last_prompt: str | None = None

    def generate(self, prompt, config):
        self.last_prompt = prompt
        return [Completion(text="MATCH (n) RETURN n", score=0.0, rank=1)]


def test_query_generator_threads_few_shot_override_only_on_instruct_path() -> None:
    from pipeline.schema import build_pole_external_schema_repr

    schema = build_pole_external_schema_repr()
    mapping = SchemaMapping(question="q", committed={}, cypher_syntax="(a)-[:R]->(b)",
                            resolution_mode="automated")

    llm = _FakeQGLLM()
    qg = QueryGenerator(llm, prompt_style="instruct", few_shot_override=_QG_FEW_SHOT_API_POLE_EXTERNAL)
    qg.generate("q", mapping, schema)
    assert _QG_FEW_SHOT_API_POLE_EXTERNAL in llm.last_prompt

    # completion (local) path ignores few_shot_override entirely — untouched by 9.4.
    llm2 = _FakeQGLLM()
    qg2 = QueryGenerator(llm2, prompt_style="completion", few_shot_override=_QG_FEW_SHOT_API_POLE_EXTERNAL)
    qg2.generate("q", mapping, schema)
    assert _QG_FEW_SHOT_API_POLE_EXTERNAL not in llm2.last_prompt


# ── 9.4: resolve_dataset qg_few_shot key (criterion 4) ──────────────────────────────────────
def test_resolve_dataset_qg_few_shot_pole_external() -> None:
    cfg = {"dataset_version": "pole_external", "benchmark": "data/benchmark-pole-external.json"}
    ds = rev.resolve_dataset(cfg)
    assert ds["qg_few_shot"] is _QG_FEW_SHOT_API_POLE_EXTERNAL


def test_resolve_dataset_qg_few_shot_v2_v3_none() -> None:
    v2 = rev.resolve_dataset({"benchmark": "data/benchmark-updated.json"})
    assert v2["qg_few_shot"] is None
    v3 = rev.resolve_dataset({"dataset_version": "v3", "benchmark": "data/benchmark-v3.json"})
    assert v3["qg_few_shot"] is None
