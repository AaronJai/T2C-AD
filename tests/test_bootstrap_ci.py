# tests/test_bootstrap_ci.py
"""Contract tests for the 11.5A paired bootstrap: pairing, known answers, abort detection."""
from __future__ import annotations

import json

import numpy as np
import pytest

from experiments.bootstrap_ci import (
    C1,
    C2,
    C3,
    UNAMBIGUOUS,
    Column,
    abort_detector_crosscheck,
    analyse_column,
    column_identity,
    is_abort,
    load_column,
    render_markdown,
    resample_indices,
    stratum_intervals,
    stratum_masks,
)


def _outcomes(ex: dict[str, list[bool]], ea: dict[str, list[bool]] | None = None):
    ea = ea if ea is not None else ex
    return {
        cond: {"EX": np.array(ex[cond], dtype=bool), "EA": np.array(ea[cond], dtype=bool)}
        for cond in (C1, C2, C3)
    }


# ------------------------------------------------------------------------------ paired resampling


def test_same_ids_used_for_every_condition_within_an_iteration():
    """C2 identical to C1 item-for-item ⇒ the paired delta is exactly 0 in EVERY iteration.

    This is the property that fails under independent per-condition resampling, which would give
    a wide, non-degenerate interval around 0.
    """
    per_item = [True, False, True, False, False, True, True, False]
    outcomes = _outcomes({C1: per_item, C2: list(per_item), C3: [not v for v in per_item]})
    idx = resample_indices(len(per_item), iterations=500, seed=7)

    intervals = stratum_intervals(outcomes, idx)

    for metric in ("EX", "EA"):
        delta = intervals[f"{metric}_C2-C1"]
        assert (delta.point, delta.lo, delta.hi) == (0.0, 0.0, 0.0)
        # ...while the individual conditions genuinely vary under the same draws.
        assert intervals[f"{metric}_C1"].lo < intervals[f"{metric}_C1"].hi


def test_resample_indices_is_seeded_shaped_and_in_range():
    a = resample_indices(12, iterations=50, seed=3)
    b = resample_indices(12, iterations=50, seed=3)
    c = resample_indices(12, iterations=50, seed=4)
    assert a.shape == (50, 12)
    assert a.min() >= 0 and a.max() <= 11
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


# ---------------------------------------------------------------------------------- known answers


def test_known_answer_hand_built_index_matrix():
    """Two hand-picked iterations over 4 items — every number checkable by hand."""
    outcomes = _outcomes({
        C1: [True, False, False, False],     # 25%
        C2: [True, True, False, False],      # 50%
        C3: [True, True, True, False],       # 75%
    })
    idx = np.array([[0, 1, 2, 3], [0, 0, 1, 1]], dtype=np.int64)

    intervals = stratum_intervals(outcomes, idx)

    assert intervals["EX_C1"].point == pytest.approx(25.0)
    assert intervals["EX_C3"].point == pytest.approx(75.0)
    assert intervals["EX_C3-C2"].point == pytest.approx(25.0)
    assert intervals["EX_C1"].n == 4
    # iteration draws: [0,1,2,3] → C1 25 / C2 50; [0,0,1,1] → C1 50 / C2 100.
    lo, hi = np.percentile(np.array([25.0, 50.0]), [2.5, 97.5])
    assert (intervals["EX_C1"].lo, intervals["EX_C1"].hi) == pytest.approx((lo, hi))
    dlo, dhi = np.percentile(np.array([25.0, 50.0]), [2.5, 97.5])   # C2-C1 = 25 then 50
    assert (intervals["EX_C2-C1"].lo, intervals["EX_C2-C1"].hi) == pytest.approx((dlo, dhi))


def test_degenerate_condition_gives_a_zero_width_interval():
    outcomes = _outcomes({C1: [True] * 5, C2: [False] * 5, C3: [True] * 5})
    intervals = stratum_intervals(outcomes, resample_indices(5, iterations=200, seed=1))

    assert (intervals["EX_C1"].point, intervals["EX_C1"].lo, intervals["EX_C1"].hi) == (100.0,) * 3
    assert (intervals["EX_C2"].point, intervals["EX_C2"].lo, intervals["EX_C2"].hi) == (0.0,) * 3
    d = intervals["EX_C2-C1"]
    assert (d.point, d.lo, d.hi) == (-100.0, -100.0, -100.0)
    assert d.excludes_zero


def test_excludes_zero_flag():
    """A delta with equal marginals spans zero; a uniformly dominant one clears it."""
    alternating = [i % 2 == 0 for i in range(20)]
    outcomes = _outcomes({C1: alternating, C2: [not v for v in alternating], C3: [True] * 20})
    intervals = stratum_intervals(outcomes, resample_indices(20, iterations=2000, seed=11))

    assert intervals["EX_C2-C1"].point == 0.0
    assert not intervals["EX_C2-C1"].excludes_zero      # equal marginals, delta spans zero
    assert intervals["EX_C3-C1"].point == pytest.approx(50.0)
    assert intervals["EX_C3-C1"].excludes_zero          # C3 dominates item-for-item


# --------------------------------------------------------------------------------- abort detector


@pytest.mark.parametrize(
    "value,expected",
    [("MATCH (p:Person) RETURN p", False), ("", True), ("   ", True), ("\n\t", True),
     (None, True)],
)
def test_is_abort_known_answers(value, expected):
    assert is_abort({"generated_cypher_final": value}) is expected
    assert is_abort({}) is True                            # field absent ⇒ nothing was generated


def test_abort_detector_crosscheck_agrees_and_disagrees():
    agreeing = {
        C2: [
            {"question_id": "Q-1", "generated_cypher_final": "", "final_cypher_syntax_hint": "",
             "ad_predicted_ambiguous": None},
            {"question_id": "Q-2", "generated_cypher_final": "MATCH (n) RETURN n",
             "final_cypher_syntax_hint": "(p:Person)", "ad_predicted_ambiguous": True},
        ]
    }
    checks = abort_detector_crosscheck(agreeing)
    assert checks[f"{C2}:syntax_hint"] is True
    assert checks[f"{C2}:ad_predicted_ambiguous"] is True

    disagreeing = {C2: [{"question_id": "Q-1", "generated_cypher_final": "MATCH (n) RETURN n",
                         "final_cypher_syntax_hint": "", "ad_predicted_ambiguous": True}]}
    assert abort_detector_crosscheck(disagreeing)[f"{C2}:syntax_hint"] is False


def test_abort_exclusion_is_the_union_across_conditions():
    column = Column(
        path="x", model="m", substrate="v3", question_ids=["Q-1", "Q-2", "Q-3"],
        outcomes=_outcomes({C1: [True] * 3, C2: [True] * 3, C3: [True] * 3}),
        is_ambiguous=np.array([True, False, True]),
        ambiguity_types=["schema", UNAMBIGUOUS, "temporal"],
        aborts={C1: np.array([False, False, False]),
                C2: np.array([True, False, False]),
                C3: np.array([False, True, False])},
        abort_crosscheck={},
    )
    assert column.abort_counts == {C1: 0, C2: 1, C3: 1}
    assert column.c2_c3_aborts_differ is False              # counts match even though items differ
    assert list(column.aborted_any) == [True, True, False]  # union, not intersection


# -------------------------------------------------------------------------------- strata + column


def _fake_records(n_per_type: int = 2) -> dict[str, list[dict]]:
    types = ["schema", "entity", "intent", "temporal", None]
    items = []
    for t in types:
        for i in range(n_per_type):
            items.append({"question_id": f"Q-{t}-{i}", "is_ambiguous_gold": t is not None,
                          "ambiguity_type": t})
    def cond(correct: bool, abort_first: bool) -> list[dict]:
        out = []
        for j, it in enumerate(items):
            aborted = abort_first and j == 0
            out.append({**it,
                        "is_correct": correct and not aborted,
                        "matches_any_interpretation": correct and not aborted,
                        "generated_cypher_final": "" if aborted else "MATCH (n) RETURN n",
                        "final_cypher_syntax_hint": "" if aborted else "(n)",
                        "ad_predicted_ambiguous": None if aborted else False})
        return out
    return {C1: cond(False, False), C2: cond(True, True), C3: cond(True, False)}


def test_load_column_rejects_mismatched_question_ids(tmp_path):
    records = _fake_records()
    records[C3][0] = {**records[C3][0], "question_id": "Q-other"}
    path = tmp_path / "qual_records_fake_v3_tag.json"
    path.write_text(json.dumps(records))

    with pytest.raises(ValueError, match="question ids"):
        load_column(str(path))


def test_column_identity():
    assert column_identity("results/qual_records_qwen2.5-32b_pole_external_qwen.json") == \
        ("qwen2.5-32b", "pole_external")
    assert column_identity("results/qual_records_claude-sonnet_v3_localdb.json") == \
        ("claude-sonnet", "v3")


def test_end_to_end_on_a_synthetic_column(tmp_path):
    path = tmp_path / "qual_records_fake_v3_tag.json"
    before = json.dumps(_fake_records())
    path.write_text(before)

    column = load_column(str(path))
    masks = stratum_masks(column)
    assert masks["overall"].sum() == 10
    assert masks["ambiguous"].sum() == 8
    assert masks["schema"].sum() == 2 and masks[UNAMBIGUOUS].sum() == 2

    result = analyse_column(column, iterations=200, seed=5)
    assert result["abort_counts"] == {C1: 0, C2: 1, C3: 0}
    assert result["c2_c3_aborts_differ"] is True
    assert result["abort_detector_crosscheck"][f"{C2}:syntax_hint"] is True

    all_items = result["strata"]["all_items"]["overall"]
    excluded = result["strata"]["abort_excluded"]["overall"]
    assert all_items["EX_C2"]["point"] == pytest.approx(90.0)   # one aborted item of ten
    assert excluded["EX_C2"]["point"] == pytest.approx(100.0)   # ...dropped from both conditions
    assert excluded["EX_C1"]["n"] == 9
    assert excluded["EX_C3-C2"]["point"] == pytest.approx(0.0)  # the whole C3−C2 gap was the abort

    # markdown renders and the input file is untouched (the tool is read-only).
    md = render_markdown([result], iterations=200, seed=5)
    assert "SL-abort-excluded" in md and "HEADLINE" in md
    assert path.read_text() == before


def test_analysis_is_reproducible_under_a_fixed_seed(tmp_path):
    path = tmp_path / "qual_records_fake_v3_tag.json"
    path.write_text(json.dumps(_fake_records()))
    column = load_column(str(path))
    assert analyse_column(column, 300, 42) == analyse_column(column, 300, 42)


def test_empty_stratum_yields_no_interval(tmp_path):
    """A stratum can empty out under abort exclusion; every key must still be present, as NaN."""
    outcomes = _outcomes({C1: [], C2: [], C3: []})
    intervals = stratum_intervals(outcomes, np.zeros((10, 0), dtype=np.int64))

    assert set(intervals) == {f"{m}_{k}" for m in ("EX", "EA")
                              for k in ("C1", "C2", "C3", "C2-C1", "C3-C2", "C3-C1")}
    for interval in intervals.values():
        assert interval.n == 0 and np.isnan(interval.point) and np.isnan(interval.lo)
    assert not intervals["EX_C3-C2"].excludes_zero
