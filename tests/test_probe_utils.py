"""Contract tests for 2.2 — shared probe helpers + sweep selection.

Covers the now-set (no-GPU) acceptance criteria:
  1. normalised_entropy collapses to ~0, spreads to ~1, with a split strictly between.
  2. roc_auc separates / saturates correctly; covered + hallucinated pass hand-built cases.
The full sweep (criterion 3) is GPU-deferred; its selection logic is unit-tested here.
"""
from __future__ import annotations

import math

import pytest

from experiments.diversity_penalty_sweep import COV_GUARDRAIL, select_penalty
from experiments.probe_utils import (
    covered,
    gold_patterns,
    hallucinated,
    normalised_entropy,
    roc_auc,
)
from pipeline.types import BenchmarkItem


# ── Acceptance 1: normalised_entropy ──────────────────────────────────────────────
def test_normalised_entropy_collapsed_is_zero():
    assert normalised_entropy(["A", "A", "A", "A", "A"]) == pytest.approx(0.0)


def test_normalised_entropy_fully_spread_is_one():
    assert normalised_entropy(["A", "B", "C", "D", "E"]) == pytest.approx(1.0)


def test_normalised_entropy_split_is_strictly_between():
    h = normalised_entropy(["A", "A", "A", "B", "B"])      # 3/2 split
    assert 0.0 < h < 1.0
    # Sanity-check the closed form: H(3/5, 2/5) / log(5).
    expected = -(0.6 * math.log(0.6) + 0.4 * math.log(0.4)) / math.log(5)
    assert h == pytest.approx(expected)


# ── Acceptance 2: roc_auc ─────────────────────────────────────────────────────────
def test_roc_auc_perfectly_separated_is_one():
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [False, False, True, True]
    assert roc_auc(scores, labels) == pytest.approx(1.0)


def test_roc_auc_perfectly_inverted_is_zero():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [False, False, True, True]
    assert roc_auc(scores, labels) == pytest.approx(0.0)


def test_roc_auc_constant_scores_is_half():
    scores = [0.5, 0.5, 0.5, 0.5]
    labels = [True, False, True, False]
    assert roc_auc(scores, labels) == pytest.approx(0.5)


def test_roc_auc_single_class_is_half():
    assert roc_auc([0.1, 0.2, 0.3], [True, True, True]) == pytest.approx(0.5)


def test_roc_auc_handles_ties_with_average_rank():
    # Two positives tie with one negative at 0.5; one clean positive above, one neg below.
    scores = [0.1, 0.5, 0.5, 0.5, 0.9]
    labels = [False, True, False, True, True]
    # Manual Mann-Whitney: positives {0.5, 0.5, 0.9}, negatives {0.1, 0.5}.
    # pairs where pos>neg: 0.5>0.1 (x2), 0.9>0.1, 0.9>0.5 = 4; ties 0.5==0.5 (x2)=0.5 each → +1.
    # total favourable = 5 / (3*2) = 0.8333...
    assert roc_auc(scores, labels) == pytest.approx(5.0 / 6.0)


# ── Acceptance 2: covered ─────────────────────────────────────────────────────────
def test_covered_matches_ignoring_variable_names_and_whitespace():
    gold = ["(p:Person)-[:SUSPECTED_OF]->(i:Incident)"]
    beams = [
        "(x:Person)-[:WITNESSED]->(y:Incident)",      # wrong rel type
        "(a:Person)-[:SUSPECTED_OF]->(b:Incident)",   # right, different var names
    ]
    assert covered(beams, gold) is True


def test_covered_false_when_no_beam_matches():
    gold = ["(p:Person)-[:SUSPECTED_OF]->(i:Incident)"]
    beams = ["(p:Person)-[:VICTIM_OF]->(i:Incident)"]
    assert covered(beams, gold) is False


def test_covered_false_on_empty_gold():
    assert covered(["(p:Person)-[:OWNS]->(v:Vehicle)"], []) is False


# ── Acceptance 2: hallucinated ────────────────────────────────────────────────────
_LABELS = {"Person", "Incident", "Vehicle"}
_RELS = {"SUSPECTED_OF", "OWNS"}


def test_hallucinated_zero_when_all_in_schema():
    beams = [
        "(p:Person)-[:SUSPECTED_OF]->(i:Incident)",
        "(p:Person)-[:OWNS]->(v:Vehicle)",
    ]
    assert hallucinated(beams, _LABELS, _RELS) == pytest.approx(0.0)


def test_hallucinated_counts_out_of_schema_label_and_rel():
    beams = [
        "(p:Person)-[:SUSPECTED_OF]->(i:Incident)",      # clean
        "(p:Person)-[:DRIVES]->(v:Vehicle)",             # bad rel
        "(p:Person)-[:OWNS]->(w:Weapon)",                # bad label
        "(p:Spaceship)-[:WARPS]->(g:Galaxy)",            # both bad → still one beam
    ]
    assert hallucinated(beams, _LABELS, _RELS) == pytest.approx(3.0 / 4.0)


def test_hallucinated_empty_beams_is_zero():
    assert hallucinated([], _LABELS, _RELS) == pytest.approx(0.0)


# ── gold_patterns derivation ──────────────────────────────────────────────────────
def _item(**kw) -> BenchmarkItem:
    base = dict(
        question_id="Q1", question="q", num_hops=1,
        is_ambiguous=False, ambiguity_type=None,
        default_interp="d", cypher_default="", interpretations=[],
    )
    base.update(kw)
    return BenchmarkItem(**base)


def test_gold_patterns_unambiguous_uses_default_only():
    item = _item(cypher_default="MATCH (p:Person)-[:OWNS]->(v:Vehicle) RETURN p")
    assert gold_patterns(item) == ["(p:Person)-[:OWNS]->(v:Vehicle)"]


def test_gold_patterns_ambiguous_adds_interpretations():
    item = _item(
        is_ambiguous=True, ambiguity_type="schema",
        cypher_default="MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p",
        interpretations=[
            {"interp": "witness", "cypher": "MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN p"},
            {"interp": "victim", "cypher": "MATCH (p:Person)-[:VICTIM_OF]->(i:Incident) RETURN p"},
        ],
    )
    patterns = gold_patterns(item)
    assert "(p:Person)-[:SUSPECTED_OF]->(i:Incident)" in patterns
    assert "(p:Person)-[:WITNESSED]->(i:Incident)" in patterns
    assert "(p:Person)-[:VICTIM_OF]->(i:Incident)" in patterns
    assert len(patterns) == 3


def test_gold_patterns_drops_parse_failures():
    item = _item(cypher_default="RETURN 1")   # no MATCH → extract returns None
    assert gold_patterns(item) == []


# ── Sweep selection logic ─────────────────────────────────────────────────────────
def _row(penalty, auc, cov, hall):
    return {"diversity_penalty": penalty, "entropy_auc": auc,
            "cov_at_5": cov, "hallucination_rate": hall}


def test_select_penalty_picks_highest_auc_among_qualified():
    rows = [
        _row(0.2, 0.70, 0.90, 0.02),
        _row(0.5, 0.75, 0.88, 0.05),   # best AUC, clears guardrail
        _row(1.0, 0.80, 0.60, 0.30),   # higher AUC but fails Cov@5
    ]
    chosen, reason = select_penalty(rows)
    assert chosen == 0.5
    assert str(COV_GUARDRAIL) in reason


def test_select_penalty_breaks_auc_ties_by_lower_hallucination():
    rows = [
        _row(0.2, 0.75, 0.90, 0.10),
        _row(0.5, 0.75, 0.90, 0.03),   # same AUC, lower hallucination → wins
    ]
    chosen, _ = select_penalty(rows)
    assert chosen == 0.5


def test_select_penalty_falls_back_and_flags_when_guardrail_unmet():
    rows = [
        _row(0.2, 0.60, 0.70, 0.05),
        _row(0.5, 0.65, 0.80, 0.10),   # best Cov@5 among the failing set
        _row(1.0, 0.90, 0.50, 0.40),
    ]
    chosen, reason = select_penalty(rows)
    assert chosen == 0.5
    assert "decisions-log" in reason
