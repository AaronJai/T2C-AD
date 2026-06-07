# pipeline/data/benchmark_loader.py
"""Load and validate the canonical benchmark. No remapping — the file is canonical."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, get_args

from pipeline.types import AmbiguityType, BenchmarkItem

_VALID_TYPES = set(get_args(AmbiguityType))   # {"schema","entity","intent","temporal"}


def load_benchmark(path: str | Path) -> list[BenchmarkItem]:
    """Load benchmark-updated.json into validated BenchmarkItem objects.

    Raises ValueError on any structural inconsistency (invalid type, is_ambiguous
    mismatch, interpretation-presence mismatch). The file is expected to already be
    canonical; these checks guard against silent corruption from manual edits.
    """
    rows = json.loads(Path(path).read_text())
    items: list[BenchmarkItem] = []
    for row in rows:
        item = BenchmarkItem(**row)        # field-name mismatch surfaces here

        # ambiguity_type must be a canonical value or None (never "" / compound)
        if item.ambiguity_type is not None and item.ambiguity_type not in _VALID_TYPES:
            raise ValueError(
                f"{item.question_id}: invalid ambiguity_type {item.ambiguity_type!r}; "
                f"expected one of {sorted(_VALID_TYPES)} or null"
            )
        # is_ambiguous must agree with ambiguity_type presence
        if item.is_ambiguous != (item.ambiguity_type is not None):
            raise ValueError(
                f"{item.question_id}: is_ambiguous={item.is_ambiguous} disagrees with "
                f"ambiguity_type={item.ambiguity_type!r}"
            )
        # interpretation presence must agree with is_ambiguous
        if item.is_ambiguous and len(item.interpretations) < 1:
            raise ValueError(f"{item.question_id}: ambiguous but has no interpretations")
        if not item.is_ambiguous and len(item.interpretations) != 0:
            raise ValueError(f"{item.question_id}: unambiguous but carries interpretations")

        items.append(item)
    return items


def ambiguous_items(items: list[BenchmarkItem]) -> list[BenchmarkItem]:
    """The ambiguous subset (50 questions)."""
    return [it for it in items if it.is_ambiguous]


def items_by_type(items: list[BenchmarkItem]) -> dict[Optional[str], list[BenchmarkItem]]:
    """Group by ambiguity_type (None key holds the 75 unambiguous) — for stratified eval."""
    grouped: dict[Optional[str], list[BenchmarkItem]] = {}
    for it in items:
        grouped.setdefault(it.ambiguity_type, []).append(it)
    return grouped
