"""Contract tests for cyver_validator typed routing (step 3.7).

No live Neo4j: `components` is faked with stub validators returning canned
`(result, metadata)` tuples. Criterion 6 (real CyVer against the POLE graph) is an
integration check run on Kaya — see the spec's acceptance criteria.
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.types import ValidationResult
from pipeline.validation import cyver_validator


# ── Stub validators / fake components ──────────────────────────────────────────
class _StubValidator:
    """Returns a canned (result, metadata); records the (query, database_name) it saw."""

    def __init__(self, result, metadata):
        self._result = result
        self._metadata = metadata
        self.calls: list[tuple] = []

    def validate(self, query, database_name=None):
        self.calls.append((query, database_name))
        return self._result, self._metadata


@dataclass
class _FakeComponents:
    syntax_validator: _StubValidator
    schema_validator: _StubValidator
    properties_validator: _StubValidator
    database_name: str | None = None


def _components(syntax, schema, properties):
    return _FakeComponents(
        syntax_validator=_StubValidator(*syntax),
        schema_validator=_StubValidator(*schema),
        properties_validator=_StubValidator(*properties),
    )


# ── Criterion 1: syntax failure → query_generator ─────────────────────────────
def test_syntax_failure_routes_to_query_generator():
    meta = [{"SyntaxError": "boom"}]
    comp = _components(syntax=(False, meta), schema=(1.0, []), properties=(1.0, []))

    result = cyver_validator("MATCH (n RETURN n", comp)

    assert isinstance(result, ValidationResult)
    assert result.syntax_valid is False
    assert result.error_type == "syntax"
    assert result.route_to == "query_generator"
    assert result.schema_score == 0.0
    assert result.properties_score is None
    assert result.metadata is meta              # passed through unchanged
    # short-circuit: schema/properties never consulted
    assert comp.schema_validator.calls == []
    assert comp.properties_validator.calls == []


# ── Criterion 2: schema score < 1.0 → schema_linker ───────────────────────────
def test_schema_failure_routes_to_schema_linker():
    meta = [{"UnknownLabelWarning": "Persn"}]
    comp = _components(syntax=(True, []), schema=(0.5, meta), properties=(1.0, []))

    result = cyver_validator("MATCH (p:Persn) RETURN p", comp)

    assert result.syntax_valid is True
    assert result.error_type == "schema"
    assert result.route_to == "schema_linker"
    assert result.schema_score == 0.5
    assert result.properties_score is None
    assert result.metadata is meta
    # short-circuit: properties never consulted after schema failure
    assert comp.properties_validator.calls == []


# ── Criterion 3: properties score < 1.0 → schema_linker ───────────────────────
def test_properties_failure_routes_to_schema_linker():
    meta = [{"UnknownPropertyWarning": "naem"}]
    comp = _components(syntax=(True, []), schema=(1.0, []), properties=(0.5, meta))

    result = cyver_validator("MATCH (p:Person {naem: 'x'}) RETURN p", comp)

    assert result.syntax_valid is True
    assert result.error_type == "properties"
    assert result.route_to == "schema_linker"
    assert result.schema_score == 1.0
    assert result.properties_score == 0.5
    assert result.metadata is meta


# ── Criterion 4: properties None (no properties accessed) → accept ────────────
def test_properties_none_accepts():
    comp = _components(syntax=(True, []), schema=(1.0, []), properties=(None, []))

    result = cyver_validator("MATCH (p:Person) RETURN p", comp)

    assert result.error_type is None
    assert result.route_to == "accept"
    assert result.syntax_valid is True
    assert result.schema_score == 1.0
    assert result.properties_score is None      # None is NOT a failure
    assert result.metadata == []


# ── Criterion 5: all pass (properties 1.0) → accept ───────────────────────────
def test_all_pass_accepts():
    comp = _components(syntax=(True, []), schema=(1.0, []), properties=(1.0, []))

    result = cyver_validator("MATCH (p:Person {name: 'Jo'}) RETURN p", comp)

    assert result.error_type is None
    assert result.route_to == "accept"
    assert result.schema_score == 1.0
    assert result.properties_score == 1.0
    assert result.metadata == []


# ── database_name threading ───────────────────────────────────────────────────
def test_database_name_passed_through_to_validators():
    comp = _components(syntax=(True, []), schema=(1.0, []), properties=(1.0, []))
    comp.database_name = "neo4j"

    cyver_validator("MATCH (p:Person) RETURN p", comp)

    assert comp.syntax_validator.calls[0][1] == "neo4j"
    assert comp.schema_validator.calls[0][1] == "neo4j"
    assert comp.properties_validator.calls[0][1] == "neo4j"
