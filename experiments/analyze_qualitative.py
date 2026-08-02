# experiments/analyze_qualitative.py
"""Qualitative C2-vs-C3 comparison, added 2026-07-27 (see decisions-log) to answer: is the
disambiguation module (C3) actually resolving ambiguity, or is its ex/ea lift over the
schema-grounded baseline (C2) just retry-budget noise?

Reads the per-question `qual_records_{model_key}{suffix}.json` written by the
`_persist_details` addition to experiments/run_evaluation.py (NOT the aggregated
metrics_*.json — those only hold MetricBundle summaries). Joins C2 and C3 by question_id,
buckets every question into:
    both_correct / both_wrong / fixed (C2 wrong, C3 right) / regressed (C2 right, C3 wrong)
stratifies by ambiguity_type, and writes a markdown report with full case studies for the
fixed/regressed buckets — the only buckets that tell you anything about the module's
behaviour, since both_correct/both_wrong are indistinguishable from "C3 did nothing".

Usage:
    python -m experiments.analyze_qualitative results/qual_records_claude-sonnet_v3.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

C2 = "schema_grounded"
C3 = "disambiguation_enhanced"


def load_details(path: str) -> dict[str, list[dict]]:
    return json.loads(Path(path).read_text())


def index_by_question(details: list[dict]) -> dict[str, dict]:
    return {d["question_id"]: d for d in details}


def bucket(c2_by_qid: dict[str, dict], c3_by_qid: dict[str, dict]) -> dict[str, list[str]]:
    """EX-based bucketing (is_correct == matches cypher_default). Only question_ids present
    in both conditions are compared; a mismatch in benchmark coverage is reported, not silently
    dropped."""
    common = sorted(set(c2_by_qid) & set(c3_by_qid))
    only_c2 = sorted(set(c2_by_qid) - set(c3_by_qid))
    only_c3 = sorted(set(c3_by_qid) - set(c2_by_qid))
    if only_c2 or only_c3:
        print(f"WARNING: question_id mismatch between conditions — only-in-C2={only_c2}, "
              f"only-in-C3={only_c3}", file=sys.stderr)

    buckets: dict[str, list[str]] = {"both_correct": [], "both_wrong": [], "fixed": [], "regressed": []}
    for qid in common:
        c2_ok = c2_by_qid[qid]["is_correct"]
        c3_ok = c3_by_qid[qid]["is_correct"]
        if c2_ok and c3_ok:
            buckets["both_correct"].append(qid)
        elif not c2_ok and not c3_ok:
            buckets["both_wrong"].append(qid)
        elif not c2_ok and c3_ok:
            buckets["fixed"].append(qid)
        else:
            buckets["regressed"].append(qid)
    return buckets


def stratify_by_type(qids: list[str], by_qid: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for qid in qids:
        t = by_qid[qid]["ambiguity_type"] or "unambiguous"
        counts[t] = counts.get(t, 0) + 1
    return counts


def sample_by_type(qids: list[str], by_qid: dict[str, dict], n_per_type: int = 3) -> list[str]:
    """Deterministic (sorted question_id, not random) sample of up to n_per_type qids per
    ambiguity_type, for characterising a large bucket (both_wrong) without dumping all of it.
    Grouped/returned in type order so the report reads by-type, not interleaved."""
    by_type: dict[str, list[str]] = {}
    for qid in sorted(qids):
        t = by_qid[qid]["ambiguity_type"] or "unambiguous"
        by_type.setdefault(t, []).append(qid)
    sample: list[str] = []
    for t in sorted(by_type):
        sample.extend(by_type[t][:n_per_type])
    return sample


def _fmt_interp(interp: dict) -> str:
    return f"  - *{interp.get('interp', '?')}*: `{interp.get('cypher', '')}`"


def _case_study(qid: str, c2: dict, c3: dict) -> str:
    lines = [f"### {qid} — {c2['question']}", ""]
    lines.append(f"- ambiguity_type (gold): **{c2['ambiguity_type'] or 'none'}**"
                 f" | is_ambiguous (gold): {c2['is_ambiguous_gold']}")
    lines.append(f"- default_interp: *{c2['default_interp']}* — `{c2['cypher_default']}`")
    if c2["interpretations"]:
        lines.append("- alternative gold interpretations:")
        lines.extend(_fmt_interp(i) for i in c2["interpretations"])
    lines.append("")
    lines.append(f"**C2 (schema_grounded)** — correct={c2['is_correct']}, "
                 f"matches_any={c2['matches_any_interpretation']}, failure_mode={c2['failure_mode']}")
    lines.append(f"  cypher: `{c2['generated_cypher_final']}`")
    lines.append("")
    lines.append(f"**C3 (disambiguation_enhanced)** — correct={c3['is_correct']}, "
                 f"matches_any={c3['matches_any_interpretation']}, failure_mode={c3['failure_mode']}")
    lines.append(f"  cypher: `{c3['generated_cypher_final']}`")
    lines.append(f"  AD predicted ambiguous: {c3['ad_predicted_ambiguous']}"
                 f" | detected_types: {c3['ad_detected_types']}")
    if c3.get("ad_llm_rationale"):
        lines.append(f"  AD rationale: {c3['ad_llm_rationale']}")
    lines.append(f"  committed mapping: {c3['final_committed_mapping']}"
                 f" | resolution_mode: {c3['resolution_mode']} | n_mappings_tried: {c3['n_mappings_tried']}")
    lines.append("")
    return "\n".join(lines)


def build_report(c2_by_qid: dict[str, dict], c3_by_qid: dict[str, dict],
                  buckets: dict[str, list[str]], both_wrong_n_per_type: int = 3) -> str:
    n = len(c2_by_qid)
    out = ["# Qualitative C2 vs C3 comparison", ""]
    out.append(f"n_total joined = {n}")
    out.append("")
    out.append("## Overall (EX: matches default interpretation)")
    out.append("")
    out.append("| bucket | count | % of n |")
    out.append("|---|---|---|")
    for name in ["both_correct", "both_wrong", "fixed", "regressed"]:
        c = len(buckets[name])
        out.append(f"| {name} | {c} | {c / n:.1%} |")
    out.append("")
    out.append("`fixed` = C2 wrong -> C3 right (candidate evidence the module helps).")
    out.append("`regressed` = C2 right -> C3 wrong (candidate evidence the module hurts).")
    out.append("Net lift should roughly match `ex(C3) - ex(C2)` from metrics_*.json; if it")
    out.append("doesn't, something in this join is off — check the question_id mismatch warning.")
    out.append("")

    out.append("## Stratified by ambiguity_type")
    out.append("")
    out.append("All four buckets, so \"handled well\" vs \"still struggling\" is visible per type,")
    out.append("not just the fixed/regressed pair below:")
    out.append("")
    all_types = sorted({(c2_by_qid[q]['ambiguity_type'] or 'unambiguous') for q in c2_by_qid})
    out.append("| ambiguity_type | both_correct | both_wrong | fixed | regressed |")
    out.append("|---|---|---|---|---|")
    for t in all_types:
        row = []
        for name in ["both_correct", "both_wrong", "fixed", "regressed"]:
            counts = stratify_by_type(buckets[name], c2_by_qid)
            row.append(str(counts.get(t, 0)))
        out.append(f"| {t} | " + " | ".join(row) + " |")
    out.append("")
    out.append(f"**fixed** by type: {stratify_by_type(buckets['fixed'], c2_by_qid)}")
    out.append(f"**regressed** by type: {stratify_by_type(buckets['regressed'], c2_by_qid)}")
    out.append("")
    out.append("If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and")
    out.append("`regressed` is flat/rare, that's consistent with the module resolving real")
    out.append("ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions")
    out.append("at similar rates, that points to retry-budget luck (C3 gets more regeneration")
    out.append("attempts than C2) rather than disambiguation actually working. A type with a high")
    out.append("`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is")
    out.append("where the module is still struggling — see the both_wrong sample below.")
    out.append("")

    out.append("## Detection sanity check (fixed + regressed only)")
    out.append("")
    for name in ["fixed", "regressed"]:
        qids = buckets[name]
        detected_correctly = sum(
            1 for qid in qids
            if c3_by_qid[qid]["ad_predicted_ambiguous"] == c3_by_qid[qid]["is_ambiguous_gold"]
        )
        out.append(f"- {name}: AD's is_ambiguous call matched gold for {detected_correctly}/{len(qids)}")
    out.append("")

    out.append("## Case studies — fixed (C2 wrong, C3 right)")
    out.append("")
    for qid in buckets["fixed"]:
        out.append(_case_study(qid, c2_by_qid[qid], c3_by_qid[qid]))

    out.append("## Case studies — regressed (C2 right, C3 wrong)")
    out.append("")
    for qid in buckets["regressed"]:
        out.append(_case_study(qid, c2_by_qid[qid], c3_by_qid[qid]))
    if not buckets["regressed"]:
        out.append("*(none)*")
        out.append("")

    both_wrong_sample = sample_by_type(buckets["both_wrong"], c2_by_qid, n_per_type=both_wrong_n_per_type)
    out.append(f"## Case studies — both_wrong sample (up to {both_wrong_n_per_type} per ambiguity_type, "
               f"{len(both_wrong_sample)} of {len(buckets['both_wrong'])} total)")
    out.append("")
    out.append("Both conditions fail these — the module neither helps nor hurts, so this is where")
    out.append("the pipeline's remaining ceiling lives (QG/schema-linking capability, not")
    out.append("disambiguation). Sampled deterministically by sorted question_id, grouped by type.")
    out.append("")
    for qid in both_wrong_sample:
        out.append(_case_study(qid, c2_by_qid[qid], c3_by_qid[qid]))

    return "\n".join(out)


def main(records_path: str, out_path: str | None = None, both_wrong_n_per_type: int = 3) -> None:
    data = load_details(records_path)
    if C2 not in data or C3 not in data:
        raise SystemExit(f"Expected '{C2}' and '{C3}' keys in {records_path}, found {list(data)}")
    c2_by_qid = index_by_question(data[C2])
    c3_by_qid = index_by_question(data[C3])
    buckets = bucket(c2_by_qid, c3_by_qid)
    report = build_report(c2_by_qid, c3_by_qid, buckets, both_wrong_n_per_type=both_wrong_n_per_type)

    out_path = out_path or str(Path(records_path).with_name(
        Path(records_path).stem.replace("qual_records", "qualitative_analysis") + ".md"))
    Path(out_path).write_text(report)
    print(f"Wrote {out_path}")
    print(f"both_correct={len(buckets['both_correct'])} both_wrong={len(buckets['both_wrong'])} "
          f"fixed={len(buckets['fixed'])} regressed={len(buckets['regressed'])}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m experiments.analyze_qualitative <qual_records_*.json> [out.md] [n_per_type]")
    _out = sys.argv[2] if len(sys.argv) > 2 else None
    _n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    main(sys.argv[1], _out, _n)
