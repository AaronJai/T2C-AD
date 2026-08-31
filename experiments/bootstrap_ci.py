# experiments/bootstrap_ci.py  --records "results/qual_records_*.json"
"""Paired bootstrap confidence intervals over the per-item evaluation records (step 11.5 part A).

Every model column in this project is n=1, yet the headline claims are all *differences*
(criterion #1: ambiguous EA C3 > C2; criterion #2: monotonic C1 < C2 < C3). This module puts an
interval on those differences by resampling the **benchmark questions**, which is the source of
chance behind nearly every "at noise level" caveat written in the tracker. It says nothing about
training stochasticity (that is 11.5 part B, optional).

Method (spec 11.5):
  1. Resample question ids with replacement, n = the stratum's size, B iterations, fixed seed.
  2. Read every condition's outcome off **the same** id vector — paired, not per-condition draws.
     Both conditions saw the same benchmark, so pairing cancels question-difficulty variance.
  3. Recompute per iteration: each condition's EX and EA, and the deltas C2-C1, C3-C2, C3-C1.
  4. Report the 2.5th / 97.5th percentiles as the 95% CI; the point estimate is the observed value,
     not the bootstrap mean.

Strata: overall · the `is_ambiguous_gold` subset (criterion #1's population) · per `ambiguity_type`
(the n=20 cells the caveats are about). Each is reported twice — over all items (the HEADLINE, the
number the pipeline actually produced) and over the **SL-abort-excluded** item set (a robustness
check, never a corrected result; see `aborted_question_ids`).

Read-only: no existing `results/` or `docs/` artefact is opened for writing. Outputs are two new
files (`--out_md`, `--out_json`).

Usage:
    python -m experiments.bootstrap_ci                      # all results/qual_records_*.json
    python -m experiments.bootstrap_ci --records results/qual_records_qwen2.5-72b_v3_qwen72.json
"""
from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Condition keys as written by experiments/run_evaluation.py's `_persist_details`.
C1 = "baseline"
C2 = "schema_grounded"
C3 = "disambiguation_enhanced"
CONDITIONS: tuple[str, str, str] = (C1, C2, C3)
CONDITION_LABEL: dict[str, str] = {C1: "C1", C2: "C2", C3: "C3"}

# metric label -> per-item record field. EX is the headline, EA the relaxed secondary.
METRIC_FIELD: dict[str, str] = {"EX": "is_correct", "EA": "matches_any_interpretation"}

# (label, minuend, subtrahend) — the three differences the dissertation's claims are about.
DELTAS: tuple[tuple[str, str, str], ...] = (
    ("C2-C1", C2, C1),
    ("C3-C2", C3, C2),
    ("C3-C1", C3, C1),
)

AMBIGUITY_TYPES: tuple[str, ...] = ("schema", "entity", "intent", "temporal")
UNAMBIGUOUS = "unambiguous"          # display label for `ambiguity_type: null`
STRATA_ORDER: tuple[str, ...] = ("overall", "ambiguous", *AMBIGUITY_TYPES, UNAMBIGUOUS)

DEFAULT_ITERATIONS = 10_000
DEFAULT_SEED = 20260831
CI_PERCENTILES: tuple[float, float] = (2.5, 97.5)


# --------------------------------------------------------------------------------------- loading


@dataclass(frozen=True)
class Interval:
    """A point estimate with its bootstrap 95% percentile interval, in percentage points."""

    point: float
    lo: float
    hi: float
    n: int

    @property
    def excludes_zero(self) -> bool:
        """True when the whole interval sits on one side of zero (only meaningful for deltas)."""
        return self.lo > 0.0 or self.hi < 0.0

    def as_dict(self) -> dict[str, float | int | bool]:
        return {"point": self.point, "lo": self.lo, "hi": self.hi, "n": self.n,
                "excludes_zero": self.excludes_zero}


@dataclass(frozen=True)
class Column:
    """One `qual_records_*.json` file, decoded into aligned per-condition outcome arrays.

    CONTRACT: `question_ids` is the shared id vector — identical across all three conditions and
    in the same order (checked at load; a mismatch is a hard error, since it invalidates pairing).
    `outcomes[condition][metric]` is a bool array indexed by that vector.
    """

    path: str
    model: str
    substrate: str
    question_ids: list[str]
    outcomes: dict[str, dict[str, np.ndarray]]
    is_ambiguous: np.ndarray
    ambiguity_types: list[str]
    aborts: dict[str, np.ndarray]          # condition -> bool array (no query was ever generated)
    abort_crosscheck: dict[str, bool]

    @property
    def label(self) -> str:
        return f"{self.model} — {self.substrate}"

    @property
    def abort_counts(self) -> dict[str, int]:
        return {c: int(self.aborts[c].sum()) for c in CONDITIONS}

    @property
    def aborted_any(self) -> np.ndarray:
        """Union across conditions — the exclusion set, so all three stay paired on one set."""
        mask = np.zeros(len(self.question_ids), dtype=bool)
        for c in CONDITIONS:
            mask |= self.aborts[c]
        return mask

    @property
    def c2_c3_aborts_differ(self) -> bool:
        counts = self.abort_counts
        return counts[C2] != counts[C3]


def is_abort(record: dict) -> bool:
    """True when the Schema Linker aborted this item and NO query was ever generated.

    `Orchestrator.run` breaks on `SchemaLinkerError` with `failure_reason=
    "schema_linker_no_valid_beams"`, so the item scores `invalid_query` with no QG call and no
    CyVer retry. In the persisted records that shows up as an empty/whitespace
    `generated_cypher_final` — verified 2026-08-31 to be identical, item for item, to the falsy
    `final_cypher_syntax_hint` set (C2) and the `ad_predicted_ambiguous is None` set (C3) across
    all seven artefacts (`abort_detector_crosscheck` re-checks it on every run).
    """
    return not (record.get("generated_cypher_final") or "").strip()


def abort_detector_crosscheck(records: dict[str, list[dict]]) -> dict[str, bool]:
    """Re-verify the abort detector against the two corroborating fields, per condition.

    C1 never calls the linker (and never carries a syntax hint), so its corroboration is vacuous
    and reported as such; the check that matters is C2's hint and C3's `ad_predicted_ambiguous`.
    """
    out: dict[str, bool] = {}
    for cond, items in records.items():
        aborted = {r["question_id"] for r in items if is_abort(r)}
        no_hint = {r["question_id"] for r in items if not r.get("final_cypher_syntax_hint")}
        no_ad = {r["question_id"] for r in items if r.get("ad_predicted_ambiguous") is None}
        out[f"{cond}:syntax_hint"] = aborted == no_hint
        out[f"{cond}:ad_predicted_ambiguous"] = aborted == no_ad
    return out


def column_identity(path: str) -> tuple[str, str]:
    """('qwen2.5-32b', 'pole_external') from results/qual_records_qwen2.5-32b_pole_external_qwen.json."""
    stem = Path(path).stem
    stem = stem[len("qual_records_"):] if stem.startswith("qual_records_") else stem
    for marker, substrate in (("_pole_external", "pole_external"), ("_v3", "v3")):
        if marker in stem:
            return stem.split(marker, 1)[0], substrate
    return stem, "unknown"


def load_column(path: str) -> Column:
    """Read one qual_records file into aligned arrays. Never opens the file for writing."""
    records: dict[str, list[dict]] = json.loads(Path(path).read_text())
    missing = [c for c in CONDITIONS if c not in records]
    if missing:
        raise ValueError(f"{path}: missing condition key(s) {missing}")

    ids = [r["question_id"] for r in records[C1]]
    for cond in CONDITIONS:
        other = [r["question_id"] for r in records[cond]]
        if other != ids:
            raise ValueError(
                f"{path}: question ids of {cond!r} differ from {C1!r} — the paired bootstrap is "
                "only valid when all conditions cover the identical id vector in the same order."
            )

    outcomes = {
        cond: {
            metric: np.array([bool(r[field]) for r in records[cond]], dtype=bool)
            for metric, field in METRIC_FIELD.items()
        }
        for cond in CONDITIONS
    }
    base = records[C1]
    model, substrate = column_identity(path)
    return Column(
        path=path,
        model=model,
        substrate=substrate,
        question_ids=ids,
        outcomes=outcomes,
        is_ambiguous=np.array([bool(r["is_ambiguous_gold"]) for r in base], dtype=bool),
        ambiguity_types=[r["ambiguity_type"] or UNAMBIGUOUS for r in base],
        aborts={c: np.array([is_abort(r) for r in records[c]], dtype=bool) for c in CONDITIONS},
        abort_crosscheck=abort_detector_crosscheck(records),
    )


# ------------------------------------------------------------------------------------- bootstrap


def resample_indices(n: int, iterations: int, seed: int) -> np.ndarray:
    """(iterations, n) matrix of positions drawn with replacement — ONE draw per iteration.

    The same matrix is handed to every condition and metric, which is what makes the procedure
    paired. Seeded per call so output is reproducible and independent of stratum ordering.
    """
    rng = np.random.default_rng(seed)
    return rng.integers(0, n, size=(iterations, n), dtype=np.int64)


def _percent(values: np.ndarray) -> np.ndarray:
    return values * 100.0


def stratum_intervals(
    outcomes: dict[str, dict[str, np.ndarray]], idx: np.ndarray
) -> dict[str, Interval]:
    """Per-condition and per-delta intervals for one stratum, in percentage points.

    Args:
        outcomes: condition -> metric -> bool array, ALREADY restricted to the stratum's items.
        idx: (iterations, n) index matrix from `resample_indices`, shared by every condition.
    Returns:
        keys `"{metric}_{C?}"` and `"{metric}_{delta}"`, e.g. `"EX_C2"`, `"EA_C3-C2"`.
    """
    n = idx.shape[1]
    curves: dict[str, np.ndarray] = {}      # key -> bootstrap distribution of that quantity
    points: dict[str, float] = {}
    out: dict[str, Interval] = {}

    if n == 0:                              # an empty stratum (e.g. every item aborted): no CI
        empty = Interval(float("nan"), float("nan"), float("nan"), 0)
        return {f"{m}_{k}": empty
                for m in METRIC_FIELD
                for k in [*CONDITION_LABEL.values(), *(d for d, _, _ in DELTAS)]}

    for metric in METRIC_FIELD:
        for cond in CONDITIONS:
            values = outcomes[cond][metric]
            boot = _percent(values[idx].mean(axis=1))
            key = f"{metric}_{CONDITION_LABEL[cond]}"
            curves[key] = boot
            points[key] = float(values.mean() * 100.0)
            out[key] = _interval(points[key], boot, n)
        for label, a, b in DELTAS:
            ka, kb = f"{metric}_{CONDITION_LABEL[a]}", f"{metric}_{CONDITION_LABEL[b]}"
            boot = curves[ka] - curves[kb]
            key = f"{metric}_{label}"
            out[key] = _interval(points[ka] - points[kb], boot, n)
    return out


def _interval(point: float, boot: np.ndarray, n: int) -> Interval:
    if n == 0:
        return Interval(point=float("nan"), lo=float("nan"), hi=float("nan"), n=0)
    lo, hi = np.percentile(boot, CI_PERCENTILES)
    return Interval(point=point, lo=float(lo), hi=float(hi), n=n)


def stratum_masks(column: Column) -> dict[str, np.ndarray]:
    """The item masks every stratum is computed over, in report order."""
    n = len(column.question_ids)
    types = np.array(column.ambiguity_types)
    masks: dict[str, np.ndarray] = {
        "overall": np.ones(n, dtype=bool),
        "ambiguous": column.is_ambiguous.copy(),
    }
    for t in (*AMBIGUITY_TYPES, UNAMBIGUOUS):
        masks[t] = types == t
    return masks


def analyse_column(column: Column, iterations: int, seed: int) -> dict:
    """Every stratum x {all items, SL-abort-excluded}, as plain dicts ready for JSON/markdown."""
    masks = stratum_masks(column)
    keep = ~column.aborted_any
    result: dict = {
        "path": column.path,
        "model": column.model,
        "substrate": column.substrate,
        "n_questions": len(column.question_ids),
        "iterations": iterations,
        "seed": seed,
        "abort_counts": column.abort_counts,
        "c2_c3_aborts_differ": column.c2_c3_aborts_differ,
        "abort_detector_crosscheck": column.abort_crosscheck,
        "strata": {},
    }
    for view, extra in (("all_items", None), ("abort_excluded", keep)):
        view_out: dict[str, dict[str, dict]] = {}
        for name in STRATA_ORDER:
            mask = masks[name] if extra is None else masks[name] & extra
            subset = {
                cond: {m: column.outcomes[cond][m][mask] for m in METRIC_FIELD}
                for cond in CONDITIONS
            }
            n = int(mask.sum())
            idx = resample_indices(n, iterations, seed) if n else np.zeros((iterations, 0), np.int64)
            view_out[name] = {k: v.as_dict() for k, v in stratum_intervals(subset, idx).items()}
        result["strata"][view] = view_out
    return result


# --------------------------------------------------------------------------------------- reports


def _fmt(entry: dict, is_delta: bool = False) -> str:
    """`point [lo, hi]` — signed and starred when the entry is a delta whose CI excludes zero."""
    if entry["n"] == 0:
        return "—"
    if not is_delta:
        return f"{entry['point']:.1f} [{entry['lo']:.1f}, {entry['hi']:.1f}]"
    star = " *" if entry["excludes_zero"] else ""
    return f"{entry['point']:+.1f} [{entry['lo']:+.1f}, {entry['hi']:+.1f}]{star}"


def _stratum_table(view: dict[str, dict[str, dict]]) -> list[str]:
    header = ("| stratum | n | metric | C1 | C2 | C3 | Δ C2−C1 | Δ C3−C2 | Δ C3−C1 |\n"
              "|---|---|---|---|---|---|---|---|---|")
    lines = [header]
    for name in STRATA_ORDER:
        entries = view[name]
        n = entries["EX_C1"]["n"]
        for metric in METRIC_FIELD:
            cells = [_fmt(entries[f"{metric}_{CONDITION_LABEL[c]}"]) for c in CONDITIONS]
            cells += [_fmt(entries[f"{metric}_{d}"], is_delta=True) for d, _, _ in DELTAS]
            label = name if metric == "EX" else ""
            n_cell = str(n) if metric == "EX" else ""
            lines.append(f"| {label} | {n_cell} | {metric} | " + " | ".join(cells) + " |")
    return lines


def _criteria_rows(result: dict) -> list[str]:
    """Criterion #1 (ambiguous EA, C3>C2) and #2 (monotonic) read off both strata."""
    rows: list[str] = []
    for view, view_label in (("all_items", "all items"), ("abort_excluded", "abort-excluded")):
        s = result["strata"][view]
        crit1 = s["ambiguous"]["EA_C3-C2"]
        mono_ex = [s["overall"]["EX_C2-C1"], s["overall"]["EX_C3-C2"]]
        mono_ea = [s["ambiguous"]["EA_C2-C1"], s["ambiguous"]["EA_C3-C2"]]
        rows.append(
            f"| {result['model']} — {result['substrate']} | {view_label} | "
            f"{_fmt(crit1, is_delta=True)} | "
            f"{'yes' if crit1['point'] > 0 else 'no'} / "
            f"{'clears 0' if crit1['excludes_zero'] else 'spans 0'} | "
            f"{'yes' if all(e['point'] >= 0 for e in mono_ex) else 'no'} | "
            f"{'yes' if all(e['point'] >= 0 for e in mono_ea) else 'no'} |"
        )
    return rows


def render_markdown(results: list[dict], iterations: int, seed: int,
                    notes: str | None = None) -> str:
    """The docs table: one section per column, headline stratum first, abort-excluded beside it.

    Args:
        notes: optional hand-written markdown (the readings the intervals are used to defend),
            spliced in verbatim after the summary tables. Kept outside the module so the tool
            stays generic over whatever record files it is pointed at.
    """
    out: list[str] = [
        "# Variance and error bars — paired bootstrap CIs (step 11.5, part A)",
        "",
        f"Generated by `python -m experiments.bootstrap_ci` · B={iterations:,} iterations · "
        f"fixed seed {seed} · read-only over `results/qual_records_*.json`.",
        "",
        "All figures are **percentage points**. Each cell is `point [2.5th, 97.5th]`; a `*` on a "
        "delta marks an interval that excludes zero. Question ids are resampled **with "
        "replacement within the stratum**, and every condition is read off the same id vector "
        "(paired), so question-difficulty variance cancels out of the deltas.",
        "",
        "**What this is not.** A CI over these questions describes sampling from *this* "
        "benchmark's question distribution; it does not make an unrepresentative benchmark "
        "representative, and it says nothing about model or training stochasticity (11.5 part B, "
        "not run). Overlapping per-condition CIs do **not** imply no effect when the paired delta "
        "CI excludes zero — always say which of the two is being quoted.",
        "",
        "**The SL-abort-excluded stratum.** C2 links at `beam_k=1` and C3 at `beam_k=5`, so C2 "
        "aborts (`SchemaLinkerError` → no query ever generated) strictly more often than C3, and "
        "C1 never aborts at all. That is a decoding-robustness difference, not an effect of "
        "disambiguation, and it flows into C3−C2. The excluded view drops every item that aborted "
        "in **any** condition (union, so all three stay paired on one set). It is reported "
        "**beside** the headline, never in place of it: the unexcluded number is the one the "
        "pipeline actually produced and stays the number of record. It removes those items from "
        "the arithmetic; it does **not** make C2 and C3 decode identically — only re-running C2 at "
        "`beam_k=5` with an argmax commit would, and that is GPU work outside this step. The "
        "excluded figure is a robustness check, never a corrected or debiased result.",
        "",
        "## Aborts per column",
        "",
        "| column | n | aborts C1 / C2 / C3 | C2≠C3? | detector cross-check |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        counts = r["abort_counts"]
        checks = r["abort_detector_crosscheck"]
        ok = checks[f"{C2}:syntax_hint"] and checks[f"{C3}:ad_predicted_ambiguous"]
        flag = "⚠️ **yes — delta not cancelled by pairing**" if r["c2_c3_aborts_differ"] else "no"
        out.append(
            f"| {r['model']} — {r['substrate']} | {r['n_questions']} | "
            f"{counts[C1]} / {counts[C2]} / {counts[C3]} | {flag} | "
            f"{'✅ agrees' if ok else '❌ DISAGREES'} |"
        )
    out += [
        "",
        "Cross-check: the abort set (`generated_cypher_final` empty/whitespace) is compared, item "
        "for item, against the falsy `final_cypher_syntax_hint` set in C2 and the "
        "`ad_predicted_ambiguous is None` set in C3.",
        "",
        "## Criteria at a glance",
        "",
        "| column | stratum | criterion #1: ambiguous EA Δ C3−C2 | C3>C2 / interval | "
        "monotonic overall EX | monotonic ambiguous EA |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        out += _criteria_rows(r)
    out.append("")
    if notes:
        out += [notes.strip(), ""]
    for r in results:
        out += [
            f"## {r['model']} — {r['substrate']}",
            "",
            f"`{r['path']}` · n={r['n_questions']} · aborts "
            f"{r['abort_counts'][C1]}/{r['abort_counts'][C2]}/{r['abort_counts'][C3]}"
            + ("  ⚠️ **C2 and C3 abort counts differ**" if r["c2_c3_aborts_differ"] else ""),
            "",
            "### All items — HEADLINE (the number of record)",
            "",
        ]
        out += _stratum_table(r["strata"]["all_items"])
        out += [
            "",
            "### SL-abort-excluded — robustness check, NOT a corrected result",
            "",
        ]
        out += _stratum_table(r["strata"]["abort_excluded"])
        out.append("")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description="Paired bootstrap CIs over qual_records (11.5A).")
    ap.add_argument("--records", default="results/qual_records_*.json",
                    help="glob (or explicit path) of qual_records files to analyse")
    ap.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out_md", default="docs/variance-and-error-bars.md")
    ap.add_argument("--out_json", default="results/bootstrap_ci.json")
    ap.add_argument("--notes", default="docs/error-bars-notes.md",
                    help="hand-written readings spliced into --out_md (skipped if absent)")
    args = ap.parse_args()

    paths = sorted(glob.glob(args.records))
    if not paths:
        raise SystemExit(f"no files matched {args.records!r}")

    results = []
    for path in paths:
        column = load_column(path)
        print(f"[bootstrap_ci] {path}  n={len(column.question_ids)}  "
              f"aborts={column.abort_counts}")
        results.append(analyse_column(column, args.iterations, args.seed))

    Path(args.out_json).write_text(json.dumps(
        {"iterations": args.iterations, "seed": args.seed, "percentiles": list(CI_PERCENTILES),
         "columns": results}, indent=2) + "\n")
    notes_path = Path(args.notes) if args.notes else None
    notes = notes_path.read_text() if notes_path and notes_path.is_file() else None
    if notes is None:
        print(f"[bootstrap_ci] no notes file at {args.notes!r} — writing tables only")
    Path(args.out_md).write_text(render_markdown(results, args.iterations, args.seed, notes))
    print(f"[bootstrap_ci] wrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
