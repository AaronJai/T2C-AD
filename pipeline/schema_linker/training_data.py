# pipeline/schema_linker/training_data.py
"""Build Schema Linker SFT data from the neo4j/text2cypher-2025v1 training split."""
from __future__ import annotations

import json
import os
import random
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from datasets import load_dataset

from pipeline.schema_linker.pattern_extraction import (
    extract_schema_pattern,
    has_relationship_type,
)
from pipeline.schema_linker.prompts import build_sl_prompt


def load_ozsoy_split(split: str = "train") -> Iterable[dict]:
    """Stream the dataset rows. Auto-downloads/caches; no manual download."""
    return load_dataset("neo4j/text2cypher-2025v1", split=split)


def build_sl_training_instance(question: str, schema_block: str, gold_cypher: str) -> Optional[dict]:
    """One SL example, or None if the row is excluded (per 1.1 filtering).

    Returns a dict with keys exactly {"prompt", "completion"} for a relationship-bearing,
    syntactically valid gold Cypher; None for a parse failure, a node-only pattern, or a
    pattern CyVer's SyntaxValidator rejects.
    """
    pattern = extract_schema_pattern(gold_cypher)
    if pattern is None:                         # parse failure → excluded
        return None
    if not _has_relationship(pattern):          # node-only → excluded
        return None
    if not _syntax_ok(pattern):                 # CyVer SyntaxValidator on the pattern
        return None
    return {"prompt": build_sl_prompt(question, schema_block), "completion": pattern}


def build_sl_dataset(
    rows: Iterable[dict],            # 2025v1 rows: fields question / schema / cypher (+3 unused)
    out_train: str | Path,
    out_eval: str | Path,
    eval_fraction: float = 0.10,
    seed: int = 13,
) -> dict:
    """For each row call build_sl_training_instance(row["question"], row["schema"],
    row["cypher"]); drop None; deterministic shuffle (seed) then 90:10 slice; write both
    jsonl files. Returns a report dict (kept, excluded-by-reason counts).

    The eval split is the first ``eval_fraction`` of the shuffled examples; the remainder
    is train. With a fixed ``seed`` the partition is reproducible across runs.
    """
    examples: list[dict] = []
    total = 0
    excluded_parse_fail = 0
    excluded_node_only = 0
    excluded_syntax_fail = 0

    for row in rows:
        total += 1
        instance = build_sl_training_instance(row["question"], row["schema"], row["cypher"])
        if instance is not None:
            examples.append(instance)
            continue
        # Re-derive the exclusion reason for the report. Extraction is pure and cheap, and
        # only excluded rows (~10–15%) are re-examined here.
        pattern = extract_schema_pattern(row["cypher"])
        if pattern is None:
            excluded_parse_fail += 1
        elif not _has_relationship(pattern):
            excluded_node_only += 1
        else:
            excluded_syntax_fail += 1

    rng = random.Random(seed)
    rng.shuffle(examples)
    n_eval = int(len(examples) * eval_fraction)
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]

    _write_jsonl(out_train, train_examples)
    _write_jsonl(out_eval, eval_examples)

    return {
        "total_rows": total,
        "kept": len(examples),
        "train": len(train_examples),
        "eval": len(eval_examples),
        "excluded_parse_fail": excluded_parse_fail,
        "excluded_node_only": excluded_node_only,
        "excluded_syntax_fail": excluded_syntax_fail,
    }


# ── Filtering predicates ─────────────────────────────────────────────────────────
def _has_relationship(pattern: str) -> bool:
    """True iff the pattern contains a typed relationship (``-[:TYPE]-``).

    Delegates to 1.1's ``has_relationship_type`` so the rel-type exclusion has one source
    of truth. Typeless/variable-length traversals (``-[*3]->``) are excluded — they don't
    exercise relationship-type linking.
    """
    return has_relationship_type(pattern)


def _syntax_ok(pattern: str) -> bool:
    """True if CyVer's SyntaxValidator accepts the pattern.

    CyVer runs ``EXPLAIN`` against a *live* neo4j driver; there is no offline mode. When no
    Neo4j is configured (this phase has no DB), syntax filtering is deferred and the pattern
    passes this check so the offline node-only / parse-fail filters still run. With a live
    driver, returns the validator's boolean verdict. See decisions-log (2026-06-07, 1.2).
    """
    validator = _get_syntax_validator()
    if validator is None:
        return True
    try:
        ok, _metadata = validator.validate(pattern)
        return bool(ok)
    except Exception:
        return False


@lru_cache(maxsize=1)
def _get_syntax_validator():
    """Lazily build a CyVer SyntaxValidator from a live Neo4j driver, or None if unavailable.

    Connection is read from NEO4J_URI / NEO4J_USERNAME (or NEO4J_USER) / NEO4J_PASSWORD.
    Any missing config or import/connection failure yields None (syntax filtering deferred).
    """
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        return None
    try:
        from CyVer import SyntaxValidator
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, password))
        return SyntaxValidator(driver)
    except Exception:
        return None


# ── Output ───────────────────────────────────────────────────────────────────────
def _write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    """Write one JSON object per line (utf-8), creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
