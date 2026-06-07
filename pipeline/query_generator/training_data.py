# pipeline/query_generator/training_data.py
"""Build Query Generator SFT data from the neo4j/text2cypher-2025v1 training split."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterable, Optional

from datasets import load_dataset

from pipeline.schema_linker.pattern_extraction import extract_schema_pattern
from pipeline.query_generator.prompts import build_qg_prompt


def build_qg_training_instance(question: str, schema_block: str, gold_cypher: str) -> Optional[dict]:
    """One QG example, or None if pattern extraction fails (row excluded).

    Note: QG keeps node-only rows (no relationship filter) — generating Cypher for a
    node-only question is still a valid QG target. Only parse failure excludes a row.
    """
    pattern = extract_schema_pattern(gold_cypher)
    if pattern is None:
        return None
    return {
        "prompt": build_qg_prompt(question, schema_block, committed_pattern=pattern),
        "completion": gold_cypher,
    }


def build_qg_dataset(
    rows: Iterable[dict],            # 2025v1 rows: question / schema / cypher (+3 unused)
    out_train: str | Path,
    out_eval: str | Path,
    eval_fraction: float = 0.10,
    seed: int = 13,
) -> dict:
    """For each row call build_qg_training_instance(row["question"], row["schema"],
    row["cypher"]); drop None; deterministic shuffle (seed) then 90:10 slice; write both
    jsonl files. `rows` is typically load_dataset("neo4j/text2cypher-2025v1", split="train").
    Returns a counts report.

    The eval split is the first ``eval_fraction`` of the shuffled examples; the remainder
    is train. The ``seed`` matches 1.2 so the train/eval partition is consistent across the
    SL and QG adapters (a question in SL-eval should not land in QG-train).
    """
    examples: list[dict] = []
    total = 0
    excluded_parse_fail = 0

    for row in rows:
        total += 1
        instance = build_qg_training_instance(row["question"], row["schema"], row["cypher"])
        if instance is not None:
            examples.append(instance)
        else:
            # A None return can only mean parse failure here — QG keeps node-only rows.
            excluded_parse_fail += 1

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
    }


def _write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    """Write one JSON object per line (utf-8), creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
