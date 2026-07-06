"""Contract tests for pipeline.schema (spec 0.3 acceptance criteria)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.schema import (build_pole_schema_repr, build_pole_v3_schema_repr,
                             build_schema_repr)
from pipeline.types import SchemaRepr

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CYPHER_PATH = DATA_DIR / "SyntheticPoliceKG.cypher"
CYPHER_V3_PATH = DATA_DIR / "SyntheticPoliceKG-v3.cypher"

# Node labels appear as (:Label ...) or (var:Label ...); rel types as -[:TYPE ...] or -[r:TYPE ...].
_LABEL_RE = re.compile(r"\(\w*:([A-Z][A-Za-z]+)")
_REL_RE = re.compile(r"-\[\w*:([A-Z][A-Z_]+)")


def _labels_in_cypher(text: str) -> set[str]:
    return set(_LABEL_RE.findall(text))


def _rel_types_in_cypher(text: str) -> set[str]:
    return set(_REL_RE.findall(text))


def test_counts() -> None:
    """Criterion 1: 9 node labels and 28 relationship paths."""
    schema = build_pole_schema_repr()
    assert isinstance(schema, SchemaRepr)
    assert len(schema.node_labels) == 9
    assert len(schema.relationship_paths) == 28


def test_schema_consistency_with_cypher() -> None:
    """Criterion 2: builder label/rel-type sets equal those defined in the .cypher file."""
    text = CYPHER_PATH.read_text(encoding="utf-8")
    schema = build_pole_schema_repr()

    builder_labels = set(schema.node_labels)
    builder_rels = {p["type"] for p in schema.relationship_paths}

    assert builder_labels == _labels_in_cypher(text)
    assert builder_rels == _rel_types_in_cypher(text)


def test_serialisers() -> None:
    """Criterion 3: prompt string has the expected sections; cypher syntax is one line per path."""
    schema = build_pole_schema_repr()

    prompt = schema.to_prompt_string(include_properties=True)
    assert "Nodes:" in prompt
    assert "Paths:" in prompt
    assert "Properties:" in prompt

    cypher = schema.to_cypher_syntax()
    lines = cypher.splitlines()
    assert len(lines) == len(schema.relationship_paths)
    pattern = re.compile(r"^\(\w+\)-\[:[A-Z_]+\]->\(\w+\)$")
    assert all(pattern.match(line) for line in lines)


# ── v3 schema repr (spec 7.3 acceptance criterion 2 — mirror of the v2 tests above) ──────

def test_v3_counts() -> None:
    """6 node labels and 11 relationship paths."""
    schema = build_pole_v3_schema_repr()
    assert isinstance(schema, SchemaRepr)
    assert len(schema.node_labels) == 6
    assert len(schema.relationship_paths) == 11


def test_v3_schema_consistency_with_cypher() -> None:
    """Builder label/rel-type sets equal those defined in the v3 .cypher file."""
    text = CYPHER_V3_PATH.read_text(encoding="utf-8")
    schema = build_pole_v3_schema_repr()

    builder_labels = set(schema.node_labels)
    builder_rels = {p["type"] for p in schema.relationship_paths}

    assert builder_labels == _labels_in_cypher(text)
    assert builder_rels == _rel_types_in_cypher(text)
    assert "Organisation" not in builder_labels and "Evidence" not in builder_labels


def test_v3_serialisers_and_temporal_props() -> None:
    """Prompt sections present; one cypher line per path; temporal edge properties serialised."""
    schema = build_pole_v3_schema_repr()

    prompt = schema.to_prompt_string(include_properties=True)
    assert "Nodes:" in prompt and "Paths:" in prompt and "Properties:" in prompt
    # Temporal edge properties (spec 7.1) surface in the serialised block.
    for prop in ("from_date", "to_date", "active"):
        assert prop in prompt
    assert "timestamp" in prompt          # CALLED edge property

    cypher = schema.to_cypher_syntax()
    lines = cypher.splitlines()
    assert len(lines) == len(schema.relationship_paths)
    pattern = re.compile(r"^\(\w+\)-\[:[A-Z_]+\]->\(\w+\)$")
    assert all(pattern.match(line) for line in lines)


def test_build_schema_repr_selector() -> None:
    """build_schema_repr dispatches on version and rejects unknowns."""
    assert len(build_schema_repr("v2").node_labels) == 9
    assert len(build_schema_repr("v3").node_labels) == 6
    assert len(build_schema_repr().node_labels) == 9          # default → v2
    with pytest.raises(ValueError):
        build_schema_repr("v4")
