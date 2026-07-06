"""Tests for the 7.3 v3 pipeline integration (config-switched; v2 path byte-identical).

No GPU/Neo4j: a FakeLLM captures the system turn, a FakeDriver stands in for the entity-cache
load, and run_evaluation.resolve_dataset is exercised directly (criterion 3 — resolved without
loading any model). Criterion 1's v2 regression guard is the byte-identity asserts below.
"""
from __future__ import annotations

import experiments.run_evaluation as rev
from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT, AD_SYSTEM_PROMPT_V3
from pipeline.disambiguator.disambiguator import disambiguator
from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT, DIS_SYSTEM_PROMPT_V3
from pipeline.entity_lookup.cache import EntityCache
from pipeline.entity_lookup.registry import (ENTITY_REGISTRY, ENTITY_REGISTRY_V3,
                                             registry_for_version)
from pipeline.llm import Completion, GenerationConfig
from pipeline.types import (AmbiguityResult, CandidateMapping, EntityLookupResult)


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
def test_registry_for_version() -> None:
    assert registry_for_version("v2") is ENTITY_REGISTRY
    assert registry_for_version() is ENTITY_REGISTRY            # default → v2
    v3 = registry_for_version("v3")
    assert v3 is ENTITY_REGISTRY_V3
    labels = {e["label"] for e in v3}
    assert labels == {"Person", "Case", "Location"}            # Organisation dropped in v3


def test_entity_cache_load_uses_selected_registry() -> None:
    driver = _FakeDriver()
    EntityCache.load(driver, registry=ENTITY_REGISTRY_V3)
    queried_labels = [q.split("(n:`")[1].split("`")[0] for q in driver.queries_seen]
    assert queried_labels == ["Person", "Case", "Location"]    # no Organisation query

    driver2 = _FakeDriver()
    EntityCache.load(driver2)                                  # default → v2 registry
    v2_labels = [q.split("(n:`")[1].split("`")[0] for q in driver2.queries_seen]
    assert "Organisation" in v2_labels


# ── AD/Dis prompt selection (touch points 3–4) ─────────────────────────────────────────────
def _empty_inputs():
    cm = CandidateMapping(question="q", mentions={})
    el = EntityLookupResult(question="q", entity_mentions={})
    return cm, el


def test_v3_prompts_are_distinct_and_v3_grounded() -> None:
    assert AD_SYSTEM_PROMPT_V3 != AD_SYSTEM_PROMPT
    assert DIS_SYSTEM_PROMPT_V3 != DIS_SYSTEM_PROMPT
    # v3 schema block: 6 labels, no dropped v2 labels/edges.
    for dropped in ("Organisation", "Evidence", "WORKS_FOR", "Communication"):
        assert dropped not in AD_SYSTEM_PROMPT_V3
    assert "Node labels: Person, Incident, Case, Location, Vehicle, Phone" in AD_SYSTEM_PROMPT_V3
    assert "PER-V3-007" in AD_SYSTEM_PROMPT_V3                  # re-grounded few-shot entity


def test_detector_uses_injected_system_prompt() -> None:
    cm, el = _empty_inputs()
    llm = _CapturingLLM('{"is_ambiguous": false, "detected_types": [], "rationale": "x"}')
    ambiguity_detector("q", cm, el, llm, system_prompt=AD_SYSTEM_PROMPT_V3)
    assert llm.system_seen == AD_SYSTEM_PROMPT_V3

    llm2 = _CapturingLLM('{"is_ambiguous": false, "detected_types": [], "rationale": "x"}')
    ambiguity_detector("q", cm, el, llm2)                      # default → v2, byte-identical
    assert llm2.system_seen == AD_SYSTEM_PROMPT


def test_disambiguator_uses_injected_system_prompt() -> None:
    cm, el = _empty_inputs()
    ar = AmbiguityResult(is_ambiguous=True, detected_types=["schema"], schema_entropy=0.9,
                         entity_entropy=0.0, llm_rationale="", threshold_schema=0.6,
                         threshold_entity=0.8)
    llm = _CapturingLLM('{"committed_pattern": null, "rationale": "x"}')
    disambiguator("q", ar, cm, el, llm, previously_tried=[], system_prompt=DIS_SYSTEM_PROMPT_V3)
    assert llm.system_seen == DIS_SYSTEM_PROMPT_V3

    llm2 = _CapturingLLM('{"committed_pattern": null, "rationale": "x"}')
    disambiguator("q", ar, cm, el, llm2, previously_tried=[])   # default → v2
    assert llm2.system_seen == DIS_SYSTEM_PROMPT


# ── run_evaluation.resolve_dataset (touch point 1/5; acceptance criteria 1 & 3) ─────────────
def test_resolve_dataset_v3() -> None:
    cfg = {"dataset_version": "v3", "results_tag": "v3", "benchmark": "data/benchmark-v3.json"}
    ds = rev.resolve_dataset(cfg)
    assert ds["dataset_version"] == "v3"
    assert len(ds["schema"].node_labels) == 6
    assert {e["label"] for e in ds["entity_registry"]} == {"Person", "Case", "Location"}
    assert ds["ad_system_prompt"] is AD_SYSTEM_PROMPT_V3
    assert ds["dis_system_prompt"] is DIS_SYSTEM_PROMPT_V3
    assert ds["results_tag"] == "v3"
    assert ds["benchmark"] == "data/benchmark-v3.json"


def test_resolve_dataset_v2_default_is_byte_identical() -> None:
    """Absent dataset_version → v2 objects + empty tag (regression guard, criterion 1)."""
    cfg = {"benchmark": "data/benchmark-updated.json"}
    ds = rev.resolve_dataset(cfg)
    assert ds["dataset_version"] == "v2"
    assert len(ds["schema"].node_labels) == 9
    assert ds["entity_registry"] is ENTITY_REGISTRY
    assert ds["ad_system_prompt"] is AD_SYSTEM_PROMPT
    assert ds["dis_system_prompt"] is DIS_SYSTEM_PROMPT
    assert ds["results_tag"] == ""


def test_persist_tag_paths(tmp_path) -> None:
    """Empty tag → today's names (v2 untouched); non-empty tag → suffixed names."""
    rev._persist(str(tmp_path), "mistral7b", {}, "TABLES", "")
    assert (tmp_path / "tables_mistral7b.md").exists()
    assert (tmp_path / "metrics_mistral7b.json").exists()

    rev._persist(str(tmp_path), "mistral7b", {}, "TABLES", "v3")
    assert (tmp_path / "tables_mistral7b_v3.md").exists()
    assert (tmp_path / "metrics_mistral7b_v3.json").exists()
