"""Contract tests for pipeline.schema (spec 0.3 acceptance criteria)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.schema import (adapter_suffix_for_version, build_pole_external_schema_repr,
                             build_pole_schema_repr, build_pole_v3_schema_repr,
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
    assert len(build_schema_repr("pole_external").node_labels) == 11
    with pytest.raises(ValueError):
        build_schema_repr("v4")


# ── pole_external schema repr (spec 9.3 acceptance criterion 2) ──────────────────────────

def test_pole_external_counts() -> None:
    """11 node labels and 17 relationship paths (9.1 audit)."""
    schema = build_pole_external_schema_repr()
    assert isinstance(schema, SchemaRepr)
    assert len(schema.node_labels) == 11
    assert len(schema.relationship_paths) == 17


def test_pole_external_labels_and_rel_types() -> None:
    schema = build_pole_external_schema_repr()
    assert set(schema.node_labels) == {
        "Person", "Location", "Phone", "Email", "Officer", "PostCode",
        "Area", "PhoneCall", "Crime", "Object", "Vehicle",
    }
    rel_types = {p["type"] for p in schema.relationship_paths}
    assert rel_types == {
        "CURRENT_ADDRESS", "HAS_PHONE", "HAS_EMAIL", "HAS_POSTCODE", "POSTCODE_IN_AREA",
        "LOCATION_IN_AREA", "KNOWS_SN", "KNOWS", "CALLER", "CALLED", "KNOWS_PHONE",
        "OCCURRED_AT", "INVESTIGATED_BY", "INVOLVED_IN", "PARTY_TO", "FAMILY_REL", "KNOWS_LW",
    }
    # INVOLVED_IN's listed source is the dominant Vehicle->Crime pattern (9.1: 978 vs 7 Object).
    involved_in = next(p for p in schema.relationship_paths if p["type"] == "INVOLVED_IN")
    assert involved_in == {"type": "INVOLVED_IN", "source": "Vehicle", "target": "Crime"}


def test_pole_external_serialisers() -> None:
    schema = build_pole_external_schema_repr()
    prompt = schema.to_prompt_string(include_properties=True)
    assert "Nodes:" in prompt and "Paths:" in prompt and "Properties:" in prompt
    assert "rel_type" in prompt          # FAMILY_REL's one relationship property

    cypher = schema.to_cypher_syntax()
    lines = cypher.splitlines()
    assert len(lines) == len(schema.relationship_paths)
    pattern = re.compile(r"^\(\w+\)-\[:[A-Z_]+\]->\(\w+\)$")
    assert all(pattern.match(line) for line in lines)


def test_build_schema_repr_pole_external_resolves_without_raising() -> None:
    schema = build_schema_repr("pole_external")
    assert isinstance(schema, SchemaRepr)
    assert len(schema.node_labels) == 11


def test_adapter_suffix_for_version_pole_external() -> None:
    """A distinct, non-empty suffix — never '' — so a future local model on this dataset
    version can't silently collide with v2's checkpoint path (9.3)."""
    assert adapter_suffix_for_version("pole_external") == "_pole_external"
    with pytest.raises(ValueError):
        adapter_suffix_for_version("not_a_version")
