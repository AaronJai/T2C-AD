"""Contract tests for PipelineComponents (step 5.1).

No live Neo4j: `neo4j.GraphDatabase.driver`, the three CyVer constructors, and
`EntityCache.load` are monkeypatched. Live checks (real cache counts, validator
construction against the POLE graph) are deferred — see the spec's acceptance criteria.
"""
from __future__ import annotations

import pytest

import pipeline.components as components_mod
from pipeline.components import PipelineComponents


# ── Fakes ──────────────────────────────────────────────────────────────────────
class _FakeDriver:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _FakeValidator:
    """Stand-in for a CyVer validator; records the driver it was built with."""

    def __init__(self, driver) -> None:
        self.driver = driver


class _FakeCache:
    pass


@pytest.fixture
def patched(monkeypatch):
    """Patch the driver factory, CyVer constructors, and EntityCache.load."""
    driver = _FakeDriver()
    cache = _FakeCache()

    monkeypatch.setattr(
        components_mod.neo4j.GraphDatabase, "driver", lambda uri, auth: driver
    )
    monkeypatch.setattr(components_mod, "SyntaxValidator", _FakeValidator)
    monkeypatch.setattr(components_mod, "SchemaValidator", _FakeValidator)
    monkeypatch.setattr(components_mod, "PropertiesValidator", _FakeValidator)
    monkeypatch.setattr(
        components_mod.EntityCache, "load",
        classmethod(lambda cls, drv, db, registry=None: cache)
    )
    return driver, cache


def _build(load_entity_cache: bool = True) -> PipelineComponents:
    return PipelineComponents.build(
        query_generator=object(),
        schema_linker=None,
        ad_llm=None,
        dis_llm=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_auth=("neo4j", "pw"),
        schema=object(),
        load_entity_cache=load_entity_cache,
    )


# ── Criterion 1: kw_only ─────────────────────────────────────────────────────────
def test_kw_only_rejects_positional_args():
    with pytest.raises(TypeError):
        PipelineComponents(object(), None)  # positional → TypeError


def test_kw_only_requires_non_default_fields():
    with pytest.raises(TypeError):
        # missing the non-default fields (query_generator, neo4j_driver, validators, schema)
        PipelineComponents(schema_linker=None)


# ── Criterion 2: build() wires patched resources ─────────────────────────────────
def test_build_populates_container(patched):
    driver, _ = patched
    c = _build()
    assert c.neo4j_driver is driver
    assert isinstance(c.syntax_validator, _FakeValidator)
    assert isinstance(c.schema_validator, _FakeValidator)
    assert isinstance(c.properties_validator, _FakeValidator)
    # validators built with the opened driver
    assert c.syntax_validator.driver is driver


def test_build_loads_cache_when_requested(patched):
    _, cache = patched
    c = _build(load_entity_cache=True)
    assert c.entity_cache is cache


def test_build_skips_cache_when_disabled(patched):
    c = _build(load_entity_cache=False)
    assert c.entity_cache is None


# ── Criterion 3: context manager closes the driver exactly once ──────────────────
def test_context_manager_closes_driver_once(patched):
    driver, _ = patched
    with _build() as c:
        assert c.neo4j_driver is driver
    assert driver.close_calls == 1
