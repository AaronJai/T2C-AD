# tests/evaluation/test_metrics.py
"""Contract tests for Metrics & Tables (step 4.2) — pure aggregation, no GPU/DB.

Covers all five acceptance criteria, including the amended per-attempt semantics
(criterion 4 a–d): retried-then-correct records must count as incorrect for Pass@1,
as repaired for the repair rates, and must never vanish from a denominator.
"""
from __future__ import annotations

import math

from pipeline.evaluation.metrics import (
    MetricBundle,
    QuestionRecord,
    compute_metrics,
    format_metric_tables,
)
from pipeline.types import EvaluationResult, ValidationResult


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _val(*, accept: bool, syntax: bool = True, schema: float = 1.0) -> ValidationResult:
    if accept:
        return ValidationResult(
            syntax_valid=True, schema_score=1.0, properties_score=1.0,
            error_type=None, route_to="accept",
        )
    return ValidationResult(
        syntax_valid=syntax,
        schema_score=schema,
        properties_score=None,
        error_type=None if syntax else "syntax",
        route_to="schema_linker" if syntax else "query_generator",
    )


def _eval(
    qid: str,
    *,
    correct: bool = False,
    any_interp: bool = False,
    ambiguity_type=None,
    failure_mode=None,
    accept: bool = True,
    syntax: bool = True,
    retry_count: int = 0,
    is_first_attempt: bool = False,
    condition="schema_grounded",
) -> EvaluationResult:
    return EvaluationResult(
        question_id=qid,
        condition=condition,
        is_correct=correct,
        matches_any_interpretation=any_interp,
        ambiguity_type=ambiguity_type,
        failure_mode=failure_mode,
        generated_cypher="MATCH (n) RETURN n",
        cyver_result=_val(accept=accept, syntax=syntax),
        retry_count=retry_count,
        is_first_attempt=is_first_attempt,
    )


def _simple(qid: str, **kw) -> QuestionRecord:
    """A one-attempt record: history == [final], first attempt accepted+evaluated."""
    final = _eval(qid, is_first_attempt=True, **kw)
    return QuestionRecord(final=final, history=[final], first_validation=_val(accept=True))


# ── Criterion 1: overall EX / EA / KG-valid on hand-built records ─────────────────
def test_overall_metrics_hand_computed():
    records = [
        _simple("Q1", correct=True, any_interp=True),                      # correct
        _simple("Q2", correct=True, any_interp=True),                      # correct
        _simple("Q3", correct=False, any_interp=True, ambiguity_type="schema"),  # valid_non_default
        QuestionRecord(                                                    # invalid_query
            final=_eval("Q4", correct=False, any_interp=False,
                        failure_mode="invalid_query", accept=False, syntax=False,
                        is_first_attempt=True),
            history=[_eval("Q4", failure_mode="invalid_query", accept=False, syntax=False,
                           is_first_attempt=True)],
            first_validation=_val(accept=False, syntax=False),
        ),
    ]
    b = compute_metrics(records)
    assert b.ex == 2 / 4               # Q1, Q2 correct
    assert b.ea == 3 / 4               # Q1, Q2, Q3 match some interpretation
    assert b.kg_valid_pct == 3 / 4     # Q1-Q3 accepted; Q4 not
    assert b.syntax_pct == 3 / 4       # Q4's synthesized result is syntax-invalid


# ── Criterion 2: per-type EA partitions the ambiguous subset; absent type → 0.0 ───
def test_per_type_ea_partition():
    records = [
        _simple("S1", any_interp=True, ambiguity_type="schema"),
        _simple("S2", any_interp=False, ambiguity_type="schema"),
        _simple("E1", any_interp=True, ambiguity_type="entity"),
        _simple("T1", any_interp=True, ambiguity_type="temporal"),
        _simple("U1", any_interp=True),                 # unambiguous — excluded from subsets
    ]
    b = compute_metrics(records)
    assert b.per_type_ea["schema"] == 1 / 2
    assert b.per_type_ea["entity"] == 1.0
    assert b.per_type_ea["temporal"] == 1.0
    assert b.per_type_ea["intent"] == 0.0           # absent type → 0.0, no ZeroDivision
    assert b.ambiguous_ea == 3 / 4                  # 4 ambiguous, 3 match


# ── Criterion 3: detection confusion matrix; None → NaN ───────────────────────────
def test_detection_confusion_matrix():
    # GT ambiguous: Q1, Q2. GT unambiguous: Q3, Q4.
    records = [
        _simple("Q1", ambiguity_type="schema", correct=True),
        _simple("Q2", ambiguity_type="entity"),
        _simple("Q3"),
        _simple("Q4"),
    ]
    # Predictions: Q1 TP, Q2 FN, Q3 FP, Q4 TN  →  TP=1, FP=1, FN=1
    ad = [("Q1", True), ("Q2", False), ("Q3", True), ("Q4", False)]
    b = compute_metrics(records, ad_predictions=ad)
    assert b.detection_prec == 1 / 2
    assert b.detection_rec == 1 / 2
    assert b.detection_f1 == 0.5
    # DSR: flagged = {Q1, Q3}; Q1 correct, Q3 not → 1/2
    assert b.dsr == 1 / 2


def test_no_ad_predictions_gives_nan():
    b = compute_metrics([_simple("Q1", correct=True)], ad_predictions=None)
    assert math.isnan(b.dsr)
    assert math.isnan(b.detection_f1)
    assert math.isnan(b.detection_prec)
    assert math.isnan(b.detection_rec)


# ── Criterion 4: per-attempt semantics (the amended core) ─────────────────────────
def test_4a_retried_then_correct_is_semantic_repair_not_pass_at_1():
    # history = [wrong_result(first), correct(final)]
    first = _eval("Q1", correct=False, failure_mode="wrong_result",
                  is_first_attempt=True, retry_count=0)
    final = _eval("Q1", correct=True, retry_count=1)
    rec = QuestionRecord(final=final, history=[first, final],
                         first_validation=_val(accept=True))
    b = compute_metrics([rec])
    assert b.ex == 1.0              # final is correct
    assert b.pass_at_1 == 0.0       # first attempt was wrong
    assert b.semantic_repair_pct == 1.0


def test_4b_structural_repair():
    # first_validation routed to schema_linker, final accepted → repaired.
    repaired = QuestionRecord(
        final=_eval("Q1", correct=True, accept=True, is_first_attempt=True),
        history=[_eval("Q1", correct=True, accept=True, is_first_attempt=True)],
        first_validation=_val(accept=False, syntax=True, schema=0.5),  # route_to=schema_linker
    )
    never = QuestionRecord(
        final=_eval("Q2", failure_mode="invalid_query", accept=False, is_first_attempt=True),
        history=[_eval("Q2", failure_mode="invalid_query", accept=False, is_first_attempt=True)],
        first_validation=_val(accept=False, syntax=True, schema=0.5),
    )
    b = compute_metrics([repaired, never])
    assert b.initial_valid_pct == 0.0                 # neither initially accepted
    assert b.structural_repair_pct == 1 / 2           # only Q1 reached accept


def test_4c_first_attempt_never_evaluated():
    # history has no is_first_attempt=True entry → first_evaluated() is None.
    final = _eval("Q1", failure_mode="invalid_query", accept=False)
    rec = QuestionRecord(final=final, history=[final],
                         first_validation=_val(accept=False))
    assert rec.first_evaluated() is None
    b = compute_metrics([rec])
    assert b.pass_at_1 == 0.0                          # counts as incorrect
    assert b.initial_valid_pct == 0.0                  # initially invalid


def test_4d_regression_guard_retried_correct_in_every_denominator():
    # The original final-only bug: a retried (is_first_attempt=False) final vanished from
    # the Pass@1 denominator, inflating it. Mix one such record with two clean firsts.
    clean1 = _simple("Q1", correct=True)
    clean2 = _simple("Q2", correct=True)
    retried = QuestionRecord(
        final=_eval("Q3", correct=True, retry_count=1),                  # is_first_attempt=False
        history=[_eval("Q3", correct=False, failure_mode="wrong_result", is_first_attempt=True),
                 _eval("Q3", correct=True, retry_count=1)],
        first_validation=_val(accept=True),
    )
    b = compute_metrics([clean1, clean2, retried])
    assert b.ex == 1.0                 # all three finals correct
    assert b.pass_at_1 == 2 / 3        # Q3's first attempt was wrong; denominator stays 3
    assert b.avg_iterations == 1 / 3   # only Q3 retried once


# ── Criterion 5: table rendering ──────────────────────────────────────────────────
def _bundle(ad: bool) -> MetricBundle:
    recs = [
        _simple("Q1", correct=True, any_interp=True, ambiguity_type="schema"),
        _simple("Q2", correct=False, any_interp=True),
    ]
    return compute_metrics(recs, ad_predictions=[("Q1", True), ("Q2", False)] if ad else None)


def test_format_metric_tables_three_tables_with_em_dash():
    bundles = {
        "baseline": _bundle(ad=False),
        "schema_grounded": _bundle(ad=False),
        "disambiguation_enhanced": _bundle(ad=True),
    }
    out = format_metric_tables(bundles)
    # Three markdown tables present.
    assert out.count("### Table") == 3
    # Denominators are derived from the data, not hardcoded: 2 questions, 1 ambiguous (schema).
    assert "Table 1 — Overall (2)" in out
    assert "Table 2 — Ambiguity-specific (1)" in out
    assert "EA — schema (n=1)" in out
    assert "EA — entity (n=0)" in out
    assert "Table 3 — Repair/routing (C2, C3)" in out
    # DSR / Detection render as em dash for C1/C2 (NaN), numeric for C3.
    lines = out.splitlines()
    dsr_row = next(line for line in lines if line.startswith("| DSR"))
    # C1 and C2 cells are em dashes; C3 carries a number.
    assert dsr_row.count("—") == 2
    f1_row = next(line for line in lines if line.startswith("| Detection F1"))
    assert f1_row.count("—") == 2


def test_format_tables_partial_conditions():
    # Only C2/C3 present — Table 1 shows two columns; Table 3 shows both repair columns.
    bundles = {"schema_grounded": _bundle(ad=False), "disambiguation_enhanced": _bundle(ad=True)}
    out = format_metric_tables(bundles)
    header = next(line for line in out.splitlines() if line.startswith("| Metric"))
    assert "C1" not in header
    assert "C2" in header and "C3" in header
