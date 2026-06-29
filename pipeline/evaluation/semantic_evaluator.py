# pipeline/evaluation/semantic_evaluator.py
"""Score a question's result set against benchmark ground truth, executed live."""
from __future__ import annotations

import re
from typing import Optional

import neo4j

from pipeline.types import (BenchmarkItem, Condition, EvaluationResult, ExecutionResult,
                            ValidationResult)


def _is_id_field(v: str) -> bool:
    """True if the string looks like a graph ID (INC-001, PER-007, VEH-012) — always exact-matched."""
    return bool(re.match(r"^[A-Z]{2,5}-\d{3,}$", v.strip()))


def _normalise_value(v):
    """Canonicalise a record value to a hashable form for frozenset comparison.

    Floats are rounded to absorb variance. A generated query (esp. zero-shot C1) may RETURN a
    whole node/relationship (→ a dict of properties) or a list (→ e.g. collect()); those are
    unhashable, so recurse — dict to a frozenset of normalised items (order-insensitive, like a
    record), list/tuple to a tuple (order-preserving, as Cypher lists are ordered) — keeping
    `norm`'s frozenset construction total. A node-dict vs a scalar simply compares unequal.
    """
    if isinstance(v, float):
        return round(v, 6)                              # absorb float variance
    if isinstance(v, dict):
        return frozenset((k, _normalise_value(x)) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return tuple(_normalise_value(x) for x in v)
    return v


def _result_sets_equal(generated: list[dict], ground_truth: list[dict],
                       embedding_model=None, string_sim_threshold: float = 0.95) -> bool:
    """Order-, duplicate- and COLUMN-NAME-insensitive comparison.

    Each record is reduced to the tuple of its values in RETURN-clause order, NOT its column
    names: a generated query that returns the right values under a different variable/alias
    (`x.name` vs the gold's `p.name`, or `RETURN x` vs `RETURN v`) must still count as correct.
    The benchmark gold and the model (Ozsoy-trained QG / zero-shot C1) rarely share variable
    names, so keying on `record.data()` names made EX a strict lower bound — see decisions-log
    2026-06-27. Column COUNT and per-position values must still match (values are not a bag).

    Primary: frozenset equality on records normalised to the ordered tuple of `_normalise_value`'d
      values.
    Fallback (only if the fast path fails AND row counts match AND an embedding_model is given):
      align rows by a value-based sort key, compare position-by-position, and require every field
      equal — except non-ID string fields, which pass on cosine similarity ≥ string_sim_threshold.
      ID-pattern and numeric fields are ALWAYS exact. Without an embedding_model, no fallback.
    Empty sets: equal iff both empty.
    """
    def row_values(r: dict) -> tuple:
        return tuple(_normalise_value(v) for v in r.values())

    if frozenset(row_values(r) for r in generated) == frozenset(row_values(r) for r in ground_truth):
        return True
    if len(generated) != len(ground_truth) or embedding_model is None:
        return False

    def sort_key(r): return tuple(sorted(str(v) for v in r.values()))
    for g, t in zip(sorted(generated, key=sort_key), sorted(ground_truth, key=sort_key)):
        gv_row, tv_row = list(g.values()), list(t.values())
        if len(gv_row) != len(tv_row):           # differing column count → not equal
            return False
        for gv, tv in zip(gv_row, tv_row):       # position-aligned (RETURN-clause order)
            if isinstance(gv, str) and isinstance(tv, str) and not (_is_id_field(gv) or _is_id_field(tv)):
                # cosine similarity on free-text strings (e.g. descriptions) via sentence-transformers
                import torch
                emb = embedding_model.encode([gv, tv], convert_to_tensor=True)
                if float(torch.nn.functional.cosine_similarity(emb[0:1], emb[1:2])) < string_sim_threshold:
                    return False
            elif gv != tv:
                return False
    return True


def _run_query(cypher: str, driver: neo4j.Driver, database_name: Optional[str]) -> list[dict]:
    records, _, _ = driver.execute_query(cypher, database_=database_name)
    return [r.data() for r in records]      # .data() to match db_executor's extraction (3.8)


def _execute_ground_truth(item: BenchmarkItem, driver, database_name):
    """(default_result, interp_results). interp_results empty for unambiguous items."""
    default_result = _run_query(item.cypher_default, driver, database_name)
    interp_results = [_run_query(i["cypher"], driver, database_name) for i in item.interpretations]
    return default_result, interp_results


def semantic_evaluator(
    execution_result: ExecutionResult,
    benchmark_item: BenchmarkItem,
    generated_cypher: str,
    cyver_result: Optional[ValidationResult],
    condition: Condition,
    retry_count: int,
    driver: neo4j.Driver,
    database_name: Optional[str],
    embedding_model=None,
    is_first_attempt: bool = False,
) -> EvaluationResult:
    """Full evaluation. Executes ground truth live.

    1. If execution failed OR CyVer didn't accept → failure_mode='invalid_query', is_correct=False,
       matches_any=False (never executed a valid query).
    2. Else execute ground truth; is_correct = result == default (EX); matches_any = is_correct OR
       result == any interpretation (relaxed AREA).
    3. failure_mode: None if is_correct; 'valid_non_default' if matches_any; else 'wrong_result'.
    """
    if not execution_result.success or (cyver_result is not None and cyver_result.route_to != "accept"):
        return EvaluationResult(
            question_id=benchmark_item.question_id, condition=condition,
            is_correct=False, matches_any_interpretation=False,
            ambiguity_type=benchmark_item.ambiguity_type, failure_mode="invalid_query",
            generated_cypher=generated_cypher, cyver_result=cyver_result,
            retry_count=retry_count, is_first_attempt=is_first_attempt,
        )

    default_result, interp_results = _execute_ground_truth(benchmark_item, driver, database_name)
    is_correct = _result_sets_equal(execution_result.result_set, default_result, embedding_model)
    matches_any = is_correct or any(
        _result_sets_equal(execution_result.result_set, ir, embedding_model) for ir in interp_results
    )
    failure_mode = None if is_correct else ("valid_non_default" if matches_any else "wrong_result")

    return EvaluationResult(
        question_id=benchmark_item.question_id, condition=condition,
        is_correct=is_correct, matches_any_interpretation=matches_any,
        ambiguity_type=benchmark_item.ambiguity_type, failure_mode=failure_mode,
        generated_cypher=generated_cypher, cyver_result=cyver_result,
        retry_count=retry_count, is_first_attempt=is_first_attempt,
    )
