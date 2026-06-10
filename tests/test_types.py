"""Contract tests for pipeline.types (spec 0.1 acceptance criteria)."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.types import (
    BenchmarkItem,
    CandidateMapping,
    PipelineState,
    SchemaCandidate,
    SchemaElement,
    SchemaMapping,
    _build_cypher_pattern,
)

BENCHMARK_PATH = Path(__file__).resolve().parent.parent / "data" / "benchmark-updated.json"
_CANONICAL_TYPES = {"schema", "entity", "intent", "temporal", None}


def test_import_and_construct() -> None:
    """Criterion 1: types import cleanly and dataclasses construct with valid args."""
    el = SchemaElement(element_type="node_label", name="Person")
    assert el.source_label is None


def test_benchmark_contract() -> None:
    """Criterion 2: all 125 rows load via BenchmarkItem(**row); ambiguity_type canonical."""
    rows = json.loads(BENCHMARK_PATH.read_text())
    assert len(rows) == 125
    for row in rows:
        item = BenchmarkItem(**row)
        assert item.ambiguity_type in _CANONICAL_TYPES


def test_top1_mapping_contract() -> None:
    """Criterion 3: top1_mapping commits the rank-1 element per mention, automated mode."""
    mapping = CandidateMapping(
        question="Who is connected to the incident?",
        mentions={
            "connected to": [
                SchemaCandidate(
                    element=SchemaElement(
                        element_type="relationship_type",
                        name="SUSPECTED_OF",
                        source_label="Person",
                        target_label="Incident",
                    ),
                    score=0.6,
                    beam_rank=1,
                ),
                SchemaCandidate(
                    element=SchemaElement(
                        element_type="relationship_type",
                        name="WITNESSED",
                        source_label="Person",
                        target_label="Incident",
                    ),
                    score=0.4,
                    beam_rank=2,
                ),
            ],
            "incident": [
                SchemaCandidate(
                    element=SchemaElement(element_type="node_label", name="Incident"),
                    score=0.7,
                    beam_rank=1,
                ),
                SchemaCandidate(
                    element=SchemaElement(element_type="node_label", name="Case"),
                    score=0.3,
                    beam_rank=2,
                ),
            ],
        },
    )

    result = mapping.top1_mapping()

    assert isinstance(result, SchemaMapping)
    assert result.resolution_mode == "automated"
    assert result.committed["connected to"].name == "SUSPECTED_OF"
    assert result.committed["incident"].name == "Incident"


def test_pipeline_state_attempt_history_fields() -> None:
    """Spec 0.1 (amended 2026-06-10): attempt-history fields exist with safe defaults and
    are per-instance (no shared mutable default)."""
    s1 = PipelineState(question="q?", benchmark_item=None, condition="baseline")
    s2 = PipelineState(question="q?", benchmark_item=None, condition="baseline")
    assert s1.evaluation_history == []
    assert s1.first_validation_result is None
    assert s1.previously_tried_mappings == []
    s1.evaluation_history.append("sentinel")  # type: ignore[arg-type]
    assert s2.evaluation_history == []        # default_factory, not shared state


def test_build_cypher_pattern_contract() -> None:
    """Criterion 4: rel + property render into one comma-joined hint string."""
    committed = {
        "connected to": SchemaElement(
            element_type="relationship_type",
            name="SUSPECTED_OF",
            source_label="Person",
            target_label="Incident",
        ),
        "crime type": SchemaElement(
            element_type="property",
            name="crime_type",
            parent="Incident",
        ),
    }

    pattern = _build_cypher_pattern(committed)

    assert isinstance(pattern, str)
    assert "[:SUSPECTED_OF]" in pattern
    assert "{crime_type}" in pattern
