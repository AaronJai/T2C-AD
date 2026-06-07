"""Contract tests for 2.3 — entropy probe re-run on the POLE-SFT Schema Linker.

Covers the now-set (no-GPU) acceptance criterion:
  1. The three scoring functions are computable from a hand-built list of beams and feed
     `roc_auc` without error (reuses the 2.2 probe_utils building blocks).
The full 125-item GPU run (criteria 2-3) is deferred; the scoring + reporting logic is pure
and unit-tested here.
"""
from __future__ import annotations

import json

import pytest

from experiments.entropy_probe import (
    ABLATION_FLAT_DELTA,
    BASELINE_AUC,
    HEADLINE_SIGNAL,
    build_finding,
    compute_auc_table,
    h_norm_beams,
    h_norm_candidates,
    read_diversity_penalty,
    top_beam_dominance,
    write_results,
)
from experiments.probe_utils import roc_auc

# Confident (collapsed, byte-identical) vs ambiguous (spread) beam sets.
_COLLAPSED = [
    "(p:Person)-[:OWNS]->(v:Vehicle)",
    "(p:Person)-[:OWNS]->(v:Vehicle)",
    "(p:Person)-[:OWNS]->(v:Vehicle)",
]
_SPREAD = [
    "(p:Person)-[:SUSPECTED_OF]->(i:Incident)",
    "(p:Person)-[:WITNESSED]->(i:Incident)",
    "(p:Person)-[:VICTIM_OF]->(i:Incident)",
]
# Same candidate three times but with different variable names (normalisation distinction).
_RENAMED = [
    "(a:Person)-[:OWNS]->(b:Vehicle)",
    "(x:Person)-[:OWNS]->(y:Vehicle)",
    "(p:Person)-[:OWNS]->(v:Vehicle)",
]


# ── Acceptance 1: the three scorers, direction + range ──────────────────────────────
@pytest.mark.parametrize("scorer", [h_norm_candidates, h_norm_beams, top_beam_dominance])
def test_scorer_low_for_collapsed_high_for_spread(scorer):
    assert scorer(_COLLAPSED) < scorer(_SPREAD)
    for s in (scorer(_COLLAPSED), scorer(_SPREAD)):
        assert 0.0 <= s <= 1.0


def test_h_norm_candidates_normalises_away_variable_names():
    # All three beams are the SAME candidate once variables are stripped -> zero entropy.
    assert h_norm_candidates(_RENAMED) == pytest.approx(0.0)


def test_h_norm_beams_treats_raw_surface_strings():
    # Raw beams differ in variable names, so the un-normalised scorer sees three distinct slots.
    assert h_norm_beams(_RENAMED) == pytest.approx(1.0)


def test_top_beam_dominance_collapsed_is_zero_spread_is_high():
    assert top_beam_dominance(_COLLAPSED) == pytest.approx(0.0)        # one candidate dominates
    assert top_beam_dominance(_SPREAD) == pytest.approx(2.0 / 3.0)     # 1 - 1/3


def test_top_beam_dominance_empty_is_zero():
    assert top_beam_dominance([]) == pytest.approx(0.0)


def test_scorers_feed_roc_auc_without_error():
    beams_per_item = [_COLLAPSED, _SPREAD, _COLLAPSED, _SPREAD]
    labels = [False, True, False, True]
    for scorer in (h_norm_candidates, h_norm_beams, top_beam_dominance):
        scores = [scorer(b) for b in beams_per_item]
        auc = roc_auc(scores, labels)
        assert 0.0 <= auc <= 1.0


# ── AUC table + finding ─────────────────────────────────────────────────────────────
def test_compute_auc_table_has_three_signals_with_priors():
    beams_per_item = [_COLLAPSED, _SPREAD, _COLLAPSED, _SPREAD]
    labels = [False, True, False, True]
    rows = compute_auc_table(beams_per_item, labels)
    assert {r["signal"] for r in rows} == {
        "h_norm_candidates", "h_norm_beams", "top_beam_dominance"}
    for r in rows:
        assert 0.0 <= r["pole_sft_auc"] <= 1.0
        assert r["prior_general_auc"] > 0.0
    # Perfectly separable hand-built set -> every scorer hits AUC 1.0.
    assert all(r["pole_sft_auc"] == pytest.approx(1.0) for r in rows)


def _rows(headline_auc, spread):
    """Three AUC rows with a chosen headline value and total spread (for finding tests)."""
    return [
        {"signal": HEADLINE_SIGNAL, "pole_sft_auc": headline_auc, "prior_general_auc": 0.622},
        {"signal": "h_norm_beams", "pole_sft_auc": headline_auc, "prior_general_auc": 0.624},
        {"signal": "top_beam_dominance",
         "pole_sft_auc": headline_auc + spread, "prior_general_auc": 0.625},
    ]


def test_build_finding_reports_improvement_and_flat_ablations():
    finding = build_finding(_rows(BASELINE_AUC + 0.05, ABLATION_FLAT_DELTA / 2))
    assert "improves" in finding
    assert "flat" in finding


def test_build_finding_reports_flat_baseline_and_non_flat_ablations():
    finding = build_finding(_rows(BASELINE_AUC - 0.02, ABLATION_FLAT_DELTA * 5))
    assert "secondary" in finding          # baseline-flat branch keeps architecture
    assert "NOT flat" in finding


# ── Locked-penalty guardrail (2.2 edge case) ────────────────────────────────────────
def test_read_diversity_penalty_reads_value(tmp_path):
    cfg = tmp_path / "schema_linker_inference.yaml"
    cfg.write_text("diversity_penalty: 0.5\n", encoding="utf-8")
    assert read_diversity_penalty(cfg) == pytest.approx(0.5)


def test_read_diversity_penalty_missing_file_points_back_to_2_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        read_diversity_penalty(tmp_path / "absent.yaml")
    assert "2.2" in str(exc.value)


def test_read_diversity_penalty_missing_key_points_back_to_2_2(tmp_path):
    cfg = tmp_path / "schema_linker_inference.yaml"
    cfg.write_text("something_else: 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        read_diversity_penalty(cfg)
    assert "2.2" in str(exc.value)


def test_write_results_round_trips_json(tmp_path):
    rows = _rows(0.70, ABLATION_FLAT_DELTA / 2)
    out = tmp_path / "results" / "entropy_probe_pole.json"
    write_results(rows, 0.5, build_finding(rows), out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["headline_signal"] == HEADLINE_SIGNAL
    assert payload["diversity_penalty"] == 0.5
    assert payload["ablations_flat"] is True
    assert payload["headline_improves_over_baseline"] is True
    assert len(payload["auc_table"]) == 3
