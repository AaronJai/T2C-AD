"""Contract tests for pipeline.data.benchmark_loader (spec 0.4 acceptance criteria)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.data.benchmark_loader import (
    ambiguous_items,
    items_by_type,
    load_benchmark,
)

BENCHMARK_PATH = Path(__file__).resolve().parents[2] / "data" / "benchmark-updated.json"

# A minimal valid unambiguous row, used as the base for crafting negative cases.
_BASE_ROW = {
    "question_id": "Q-TEST",
    "question": "How many incidents are there?",
    "num_hops": 1,
    "is_ambiguous": False,
    "ambiguity_type": None,
    "default_interp": "count of Incident nodes",
    "cypher_default": "MATCH (i:Incident) RETURN count(i)",
    "interpretations": [],
}


def test_load_returns_125_items() -> None:
    """Criterion 1: the canonical file loads into 125 BenchmarkItem objects."""
    items = load_benchmark(BENCHMARK_PATH)
    assert len(items) == 125


def test_ambiguous_split() -> None:
    """Criterion 2: 50 ambiguous, 75 unambiguous."""
    items = load_benchmark(BENCHMARK_PATH)
    ambiguous = ambiguous_items(items)
    assert len(ambiguous) == 50
    assert len(items) - len(ambiguous) == 75


def test_items_by_type_counts() -> None:
    """Criterion 3: stratified counts match the canonical distribution."""
    items = load_benchmark(BENCHMARK_PATH)
    grouped = items_by_type(items)
    counts = {k: len(v) for k, v in grouped.items()}
    assert counts["schema"] == 13
    assert counts["entity"] == 11
    assert counts["intent"] == 11
    assert counts["temporal"] == 15
    assert counts[None] == 75


def _write_rows(tmp_path: Path, row: dict) -> Path:
    import json

    path = tmp_path / "crafted.json"
    path.write_text(json.dumps([row]))
    return path


def test_empty_string_type_raises(tmp_path: Path) -> None:
    """Criterion 4: ambiguity_type="" raises ValueError."""
    row = {**_BASE_ROW, "is_ambiguous": True, "ambiguity_type": "", "interpretations": [{"interp": "x", "cypher": "y"}]}
    with pytest.raises(ValueError):
        load_benchmark(_write_rows(tmp_path, row))


def test_is_ambiguous_type_mismatch_raises(tmp_path: Path) -> None:
    """Criterion 4: is_ambiguous=True with ambiguity_type=None raises ValueError."""
    row = {**_BASE_ROW, "is_ambiguous": True, "ambiguity_type": None}
    with pytest.raises(ValueError):
        load_benchmark(_write_rows(tmp_path, row))


def test_compound_type_raises(tmp_path: Path) -> None:
    """Criterion 4: a compound ambiguity_type raises ValueError."""
    row = {**_BASE_ROW, "is_ambiguous": True, "ambiguity_type": "schema,temporal", "interpretations": [{"interp": "x", "cypher": "y"}]}
    with pytest.raises(ValueError):
        load_benchmark(_write_rows(tmp_path, row))
