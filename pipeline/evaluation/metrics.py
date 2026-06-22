# pipeline/evaluation/metrics.py
"""Aggregate per-question records into a MetricBundle; render the three result tables."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from pipeline.types import Condition, EvaluationResult, ValidationResult


@dataclass
class QuestionRecord:
    """One question's full evaluation data for one condition (assembled by 5.4).

    final: the terminal EvaluationResult (synthesized invalid_query for failed runs — 5.4).
    history: every evaluated attempt in order, final included. For a run that never reached
      evaluation, history == [final] (the synthesized record, is_first_attempt=True).
    first_validation: the run's first CyVer result (PipelineState.first_validation_result);
      None only if the QG never produced a query.
    """
    final: EvaluationResult
    history: list[EvaluationResult] = field(default_factory=list)
    first_validation: Optional[ValidationResult] = None

    def first_evaluated(self) -> Optional[EvaluationResult]:
        """The first-attempt evaluation, or None if the first attempt never executed."""
        return next((r for r in self.history if r.is_first_attempt), None)


@dataclass
class MetricBundle:
    # Table 1 — overall (all 125)
    ex: float                 # primary: Execution Accuracy vs default interpretation
    ea: float                 # secondary: relaxed AREA (matches any interpretation)
    kg_valid_pct: float       # % CyVer-accept (final state)
    syntax_pct: float
    schema_pct: float         # schema-pass GIVEN syntax-pass
    pass_at_1: float          # EX on the first attempt, before any retry loop
    # Table 2 — ambiguity-specific (50 ambiguous)
    ambiguous_ea: float
    dsr: float                # Condition 3 only; NaN otherwise
    detection_f1: float       # Condition 3 only; NaN otherwise
    detection_prec: float
    detection_rec: float
    per_type_ea: dict         # {"schema":…, "entity":…, "intent":…, "temporal":…}
    # Table 3 — repair/routing (C2, C3)
    initial_valid_pct: float
    post_cyver_valid_pct: float
    structural_repair_pct: float
    semantic_repair_pct: float   # C3 only
    avg_iterations: float


def compute_metrics(
    records: list[QuestionRecord],
    ad_predictions: Optional[list[tuple[str, bool]]] = None,   # [(question_id, AD_pred)] — C3 only
) -> MetricBundle:
    """All metrics from one condition's QuestionRecords (one per question, all 125 present).

    ad_predictions is required for dsr / detection_*; pass None for C1 and C2 (those become NaN).
    Final-state metrics read rec.final; first-attempt metrics read rec.first_evaluated() /
    rec.first_validation. Every denominator below is over questions, never over attempts.
    """
    n = len(records)
    finals = [rec.final for rec in records]
    ambiguous = [r for r in finals if r.ambiguity_type is not None]

    ex = sum(r.is_correct for r in finals) / n
    ea = sum(r.matches_any_interpretation for r in finals) / n
    kg_valid = sum(1 for r in finals if r.cyver_result and r.cyver_result.route_to == "accept") / n
    syntax_pct = sum(1 for r in finals if r.cyver_result and r.cyver_result.syntax_valid) / n
    syntax_passed = [r for r in finals if r.cyver_result and r.cyver_result.syntax_valid]
    schema_pct = (sum(1 for r in syntax_passed if r.cyver_result.schema_score >= 1.0)
                  / len(syntax_passed)) if syntax_passed else 0.0

    # Pass@1: ALL n questions in the denominator. A question whose first attempt never
    # produced an accepted+evaluated query counts as incorrect (first_evaluated() is None).
    firsts = [rec.first_evaluated() for rec in records]
    pass_at_1 = sum(1 for fr in firsts if fr is not None and fr.is_correct) / n

    ambiguous_ea = (sum(r.matches_any_interpretation for r in ambiguous) / len(ambiguous)) if ambiguous else 0.0
    per_type_ea = {}
    for t in ("schema", "entity", "intent", "temporal"):
        sub = [r for r in ambiguous if r.ambiguity_type == t]
        per_type_ea[t] = (sum(r.matches_any_interpretation for r in sub) / len(sub)) if sub else 0.0

    if ad_predictions is not None:
        flagged = {qid for qid, pred in ad_predictions if pred}
        fr_ = [r for r in finals if r.question_id in flagged]
        dsr = (sum(r.is_correct for r in fr_) / len(fr_)) if fr_ else 0.0
        pred_map = dict(ad_predictions)        # outer retries may duplicate qids; last wins
        gt_map = {r.question_id: (r.ambiguity_type is not None) for r in finals}
        tp = sum(1 for q in pred_map if pred_map[q] and gt_map.get(q, False))
        fp = sum(1 for q in pred_map if pred_map[q] and not gt_map.get(q, False))
        fn = sum(1 for q in pred_map if not pred_map[q] and gt_map.get(q, False))
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec_ = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec_ / (prec + rec_) if (prec + rec_) else 0.0
    else:
        dsr = prec = rec_ = f1 = float("nan")

    # Table 3 — first-attempt validity and repair, from first_validation + history.
    initially_valid = [rec for rec in records
                       if rec.first_validation and rec.first_validation.route_to == "accept"]
    initial_valid_pct = len(initially_valid) / n
    initially_invalid = [rec for rec in records
                         if not (rec.first_validation and rec.first_validation.route_to == "accept")]
    repaired = [rec for rec in initially_invalid
                if rec.final.cyver_result and rec.final.cyver_result.route_to == "accept"]
    structural_repair_pct = (len(repaired) / len(initially_invalid)) if initially_invalid else 0.0

    first_wrong = [rec for rec in records
                   if (fe := rec.first_evaluated()) is not None and fe.failure_mode == "wrong_result"]
    sem_repaired = [rec for rec in first_wrong if rec.final.is_correct]
    semantic_repair_pct = (len(sem_repaired) / len(first_wrong)) if first_wrong else 0.0

    avg_iterations = (sum(r.retry_count for r in finals) / n) if n else 0.0

    return MetricBundle(
        ex=ex, ea=ea, kg_valid_pct=kg_valid, syntax_pct=syntax_pct, schema_pct=schema_pct,
        pass_at_1=pass_at_1, ambiguous_ea=ambiguous_ea, dsr=dsr,
        detection_f1=f1, detection_prec=prec, detection_rec=rec_, per_type_ea=per_type_ea,
        initial_valid_pct=initial_valid_pct, post_cyver_valid_pct=kg_valid,
        structural_repair_pct=structural_repair_pct, semantic_repair_pct=semantic_repair_pct,
        avg_iterations=avg_iterations,
    )


# ── Table rendering ────────────────────────────────────────────────────────────
# Canonical column order. C1≤C2≤C3 is the headline ordering the tables make visible.
_CONDITION_ORDER: tuple[Condition, ...] = ("baseline", "schema_grounded", "disambiguation_enhanced")
_CONDITION_LABEL: dict[Condition, str] = {
    "baseline": "C1",
    "schema_grounded": "C2",
    "disambiguation_enhanced": "C3",
}
# Table 3 is repair/routing only — the baseline has no repair loop.
_REPAIR_CONDITIONS: tuple[Condition, ...] = ("schema_grounded", "disambiguation_enhanced")


def _fmt_pct(value: float) -> str:
    """Render a proportion ∈ [0,1] as a one-decimal percentage; NaN → em dash (C1/C2 cells)."""
    if value != value:   # NaN
        return "—"
    return f"{value * 100:.1f}"


def _fmt_num(value: float) -> str:
    """Render a raw count/mean (e.g. avg_iterations) to two decimals; NaN → em dash."""
    if value != value:   # NaN
        return "—"
    return f"{value:.2f}"


def _render_table(
    title: str,
    conditions: list[Condition],
    rows: list[tuple[str, Callable[[MetricBundle], str]]],
    bundles: dict[Condition, MetricBundle],
) -> str:
    """One markdown table: a Metric column plus one column per present condition."""
    header = "| Metric | " + " | ".join(_CONDITION_LABEL[c] for c in conditions) + " |"
    sep = "| --- " + "| --- " * len(conditions) + "|"
    lines = [f"### {title}", "", header, sep]
    for label, fn in rows:
        cells = " | ".join(fn(bundles[c]) for c in conditions)
        lines.append(f"| {label} | {cells} |")
    return "\n".join(lines)


def format_metric_tables(bundles: dict[Condition, MetricBundle]) -> str:
    """Render Tables 1–3 as markdown from the per-condition MetricBundles.

    Columns are emitted in canonical C1→C2→C3 order for whichever conditions are present.
    DSR / Detection / semantic-repair cells render as `—` wherever the underlying value is
    NaN (C1/C2 pass ad_predictions=None). Table 3 covers the repair conditions only (C2, C3).
    """
    present = [c for c in _CONDITION_ORDER if c in bundles]
    repair = [c for c in _REPAIR_CONDITIONS if c in bundles]

    table1 = _render_table(
        "Table 1 — Overall (125)", present,
        [
            ("EX", lambda b: _fmt_pct(b.ex)),
            ("EA / AREA", lambda b: _fmt_pct(b.ea)),
            ("KG-Valid %", lambda b: _fmt_pct(b.kg_valid_pct)),
            ("Syntax %", lambda b: _fmt_pct(b.syntax_pct)),
            ("Schema %", lambda b: _fmt_pct(b.schema_pct)),
            ("Pass@1", lambda b: _fmt_pct(b.pass_at_1)),
        ],
        bundles,
    )

    table2 = _render_table(
        "Table 2 — Ambiguity-specific (50)", present,
        [
            ("Ambiguous EA", lambda b: _fmt_pct(b.ambiguous_ea)),
            ("DSR", lambda b: _fmt_pct(b.dsr)),
            ("Detection F1", lambda b: _fmt_pct(b.detection_f1)),
            ("Detection Prec", lambda b: _fmt_pct(b.detection_prec)),
            ("Detection Rec", lambda b: _fmt_pct(b.detection_rec)),
            ("EA — schema (n=13)", lambda b: _fmt_pct(b.per_type_ea["schema"])),
            ("EA — entity (n=11)", lambda b: _fmt_pct(b.per_type_ea["entity"])),
            ("EA — intent (n=11)", lambda b: _fmt_pct(b.per_type_ea["intent"])),
            ("EA — temporal (n=15)", lambda b: _fmt_pct(b.per_type_ea["temporal"])),
        ],
        bundles,
    )

    table3 = _render_table(
        "Table 3 — Repair/routing (C2, C3)", repair,
        [
            ("Initial Valid %", lambda b: _fmt_pct(b.initial_valid_pct)),
            ("Post-CyVer Valid %", lambda b: _fmt_pct(b.post_cyver_valid_pct)),
            ("Structural Repair %", lambda b: _fmt_pct(b.structural_repair_pct)),
            ("Semantic Repair %", lambda b: _fmt_pct(b.semantic_repair_pct)),
            ("Avg Iterations", lambda b: _fmt_num(b.avg_iterations)),
        ],
        bundles,
    )

    return "\n\n".join((table1, table2, table3))
