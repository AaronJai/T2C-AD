# experiments/validate_benchmark.py
"""Executable validation harness for a benchmark authored to the canonical contract (7.2).

Makes a benchmark's correctness *executable*: every gold Cypher must run non-empty on the
live KG and every ambiguous item's interpretations must return pairwise-distinct result
sets — the precondition that makes DSR / Execution-Accuracy measurable. Version-agnostic via
`BenchmarkProfile` (9.2): a profile carries the relationship-type inventory, expected
distribution/total, and coverage floor for whichever schema the benchmark is authored
against, so the same 8-gate harness serves v3 and the external POLE benchmark alike.

CLI:
    python -m experiments.validate_benchmark --benchmark data/benchmark-v3.json \
        [--report results/benchmark_v3_validation.json] [--profile {v3,pole_external}]

Connects via the same NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD env contract as 3.2+.
Writes a per-gate / per-item JSON report and exits non-zero on any gate failure.

Gates (all must pass):
  1. Loads          — load_benchmark (0.4) returns items without ValueError.
  2. Distribution   — 120 items; 40/20/20/20/20 by ambiguity_type; unique id + text.
  3. Syntax         — every Cypher passes CyVer SyntaxValidator (live driver).
  4. Schema closure — every label/rel-type/property exists in the v3 schema (CyVer
                      Schema + Properties validators against the loaded v3 graph).
  5. Non-empty exec — every gold Cypher runs (db_executor 3.8) success=True, non-empty.
  6. Divergence     — each ambiguous item's interpretations are pairwise distinct under
                      4.1 _result_sets_equal (value-tuple, column-name-insensitive).
  7. Hop honesty    — num_hops == relationship count of the default pattern (1.1); no
                      gold Cypher exceeds 3 hops.
  8. Coverage       — each of the 11 v3 relationship types appears in >=3 items' gold.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline.data.benchmark_loader import load_benchmark
from pipeline.evaluation.semantic_evaluator import _result_sets_equal
from pipeline.execution import db_executor
from pipeline.schema_linker.pattern_extraction import extract_schema_pattern
from pipeline.types import BenchmarkItem

# ── v3 schema inventory (7.1) — the closure target ────────────────────────────────
V3_LABELS = ["Person", "Incident", "Case", "Location", "Vehicle", "Phone"]
V3_REL_TYPES = [
    "SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES", "CONTAINS",
    "OCCURRED_AT", "LIVES_AT", "OWNS", "USES_PHONE", "CALLED", "ASSOCIATED_WITH",
]

# Distribution expected by gate 2 (None = unambiguous).
EXPECTED_DISTRIBUTION = {None: 40, "schema": 20, "entity": 20, "intent": 20, "temporal": 20}
EXPECTED_TOTAL = 120
MAX_HOPS = 3
MIN_COVERAGE = 3


# ── BenchmarkProfile (9.2) — generalizes gates 2 & 8 beyond the v3-hardcoded constants ─
@dataclass
class BenchmarkProfile:
    """The per-schema inventory/expectations gates 2 (distribution) and 8 (coverage) read.

    Gates 3-6 already route through CyVer's live-introspecting validators and db_executor
    against whatever the connection points at, so they need no profile — only the two gates
    that previously read module-level v3 constants do.
    """
    name: str
    rel_types: list[str]                              # closure target for gate 8 (coverage)
    expected_distribution: dict[Optional[str], int]    # gate 2
    expected_total: int                                # gate 2
    max_hops: int = 3                                  # gate 7
    min_coverage: int = 3                               # gate 8


V3_PROFILE = BenchmarkProfile(
    name="v3",
    rel_types=V3_REL_TYPES,
    expected_distribution=EXPECTED_DISTRIBUTION,
    expected_total=EXPECTED_TOTAL,
    max_hops=MAX_HOPS,
    min_coverage=MIN_COVERAGE,
)

# ── POLE-external schema inventory (9.1, docs/neo4jpole.md) — the closure target ──────
POLE_EXTERNAL_REL_TYPES = [
    "CURRENT_ADDRESS", "HAS_PHONE", "HAS_EMAIL", "HAS_POSTCODE", "POSTCODE_IN_AREA",
    "LOCATION_IN_AREA", "KNOWS_SN", "KNOWS", "CALLER", "CALLED", "KNOWS_PHONE",
    "OCCURRED_AT", "INVESTIGATED_BY", "INVOLVED_IN", "PARTY_TO", "FAMILY_REL", "KNOWS_LW",
]

POLE_EXTERNAL_PROFILE = BenchmarkProfile(
    name="pole_external",
    rel_types=POLE_EXTERNAL_REL_TYPES,
    expected_distribution={None: 20, "schema": 20, "entity": 20, "intent": 20, "temporal": 20},
    expected_total=100,
    max_hops=3,
    # Relaxed from v3's 3: several real relationship types are structurally rare in this
    # graph (PARTY_TO has only 55 edges total, FAMILY_REL 155) — a >=3-item bar designed
    # for the *authored* synthetic v3 schema is not realistic here without contriving
    # repetitive questions against the coverage gate. See decisions-log 2026-08-02.
    min_coverage=1,
)


# ── helpers ───────────────────────────────────────────────────────────────────────
def relationship_count(cypher: str) -> int:
    """Relationship count of the extracted schema pattern (1.1) — the gate-7 hop metric.

    extract_schema_pattern renders every relationship as one ``[...]`` group and node
    labels/property maps with ``(`` / ``{``, so the count of ``[`` is the hop count.
    """
    pattern = extract_schema_pattern(cypher)
    return pattern.count("[") if pattern else 0


def rel_types_in(cypher: str) -> set[str]:
    """The relationship types referenced by a Cypher (handles ``[:A|B|C]`` multi-type)."""
    types: set[str] = set()
    for seg in re.findall(r"\[[^\]]*\]", cypher):
        m = re.search(r":([A-Z_|]+)", seg)
        if m:
            types.update(t for t in m.group(1).split("|") if t)
    return types


def gold_cyphers(item: BenchmarkItem) -> list[str]:
    """cypher_default plus every interpretation Cypher."""
    return [item.cypher_default] + [i["cypher"] for i in item.interpretations]


# ── minimal duck-typed components for CyVer (per 3.7 handoff, CyVer lives in caller) ─
@dataclass
class _CyverComponents:
    syntax_validator: object
    schema_validator: object
    properties_validator: object
    database_name: Optional[str] = None


def build_cyver_components(driver, database_name: Optional[str]) -> _CyverComponents:
    """Construct the three real CyVer validators against the live driver (as 5.1 does)."""
    from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

    return _CyverComponents(
        syntax_validator=SyntaxValidator(driver, check_multilabeled_nodes=True),
        schema_validator=SchemaValidator(driver),
        properties_validator=PropertiesValidator(driver),
        database_name=database_name,
    )


# ── report container ──────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    name: str
    passed: bool
    failures: list[dict] = field(default_factory=list)
    detail: Optional[dict] = None

    def as_dict(self) -> dict:
        d: dict = {"passed": self.passed, "failures": self.failures}
        if self.detail is not None:
            d["detail"] = self.detail
        return d


# ── offline gates (DB-free — unit-testable) ───────────────────────────────────────
def gate_distribution(items: list[BenchmarkItem], profile: BenchmarkProfile = V3_PROFILE) -> GateResult:
    """Gate 2: count, per-type distribution, unique question_id and question text."""
    failures: list[dict] = []
    if len(items) != profile.expected_total:
        failures.append({"issue": "count", "expected": profile.expected_total, "got": len(items)})
    dist = Counter(it.ambiguity_type for it in items)
    if dict(dist) != profile.expected_distribution:
        failures.append({"issue": "distribution", "expected": {str(k): v for k, v in profile.expected_distribution.items()},
                         "got": {str(k): v for k, v in dist.items()}})
    id_dups = [q for q, n in Counter(it.question_id for it in items).items() if n > 1]
    if id_dups:
        failures.append({"issue": "duplicate_question_id", "ids": id_dups})
    text_dups = [q for q, n in Counter(it.question for it in items).items() if n > 1]
    if text_dups:
        failures.append({"issue": "duplicate_question_text", "questions": text_dups})
    return GateResult("2_distribution", not failures, failures,
                      detail={"distribution": {str(k): v for k, v in dist.items()}})


def gate_hops(items: list[BenchmarkItem]) -> GateResult:
    """Gate 7: num_hops == relationship count of the default; no gold exceeds 3 hops."""
    failures: list[dict] = []
    for it in items:
        nh = relationship_count(it.cypher_default)
        if nh != it.num_hops:
            failures.append({"question_id": it.question_id, "issue": "num_hops_mismatch",
                             "declared": it.num_hops, "actual": nh})
        for cy in gold_cyphers(it):
            hc = relationship_count(cy)
            if hc > MAX_HOPS:
                failures.append({"question_id": it.question_id, "issue": "exceeds_max_hops",
                                 "hops": hc, "cypher": cy})
    return GateResult("7_hop_honesty", not failures, failures)


def gate_coverage(items: list[BenchmarkItem], profile: BenchmarkProfile = V3_PROFILE) -> GateResult:
    """Gate 8: each of profile.rel_types appears in >=profile.min_coverage items' gold Cypher."""
    per_type: Counter[str] = Counter()
    for it in items:
        item_types: set[str] = set()
        for cy in gold_cyphers(it):
            item_types |= (rel_types_in(cy) & set(profile.rel_types))
        for rt in item_types:
            per_type[rt] += 1
    failures = [{"relationship_type": rt, "items": per_type[rt], "required": profile.min_coverage}
                for rt in profile.rel_types if per_type[rt] < profile.min_coverage]
    return GateResult("8_coverage", not failures, failures,
                      detail={rt: per_type[rt] for rt in profile.rel_types})


def run_offline_gates(items: list[BenchmarkItem], profile: BenchmarkProfile = V3_PROFILE) -> list[GateResult]:
    """Gates 2, 7, 8 — no database required (used by the offline unit tests)."""
    return [gate_distribution(items, profile), gate_hops(items), gate_coverage(items, profile)]


# ── live gates (require a driver + CyVer) ─────────────────────────────────────────
def gate_syntax_and_schema(items: list[BenchmarkItem], components: _CyverComponents) -> tuple[GateResult, GateResult]:
    """Gates 3 & 4 via CyVer (3.7 routing): syntax → gate 3; schema/properties → gate 4.

    Reuses the deterministic `cyver_validator` routing: route_to=="query_generator" is a
    syntax failure (gate 3); "schema_linker" is a schema/property closure failure (gate 4);
    "accept" passes both. Because the router short-circuits on the first failure, a syntax
    failure is reported only under gate 3 (schema is not reached), which is the intent.
    """
    from pipeline.validation import cyver_validator

    syntax_fail: list[dict] = []
    schema_fail: list[dict] = []
    for it in items:
        for role, cy in _labelled_cyphers(it):
            vr = cyver_validator(cy, components)
            if vr.route_to == "query_generator":
                syntax_fail.append({"question_id": it.question_id, "role": role, "cypher": cy,
                                    "error_type": vr.error_type})
            elif vr.route_to == "schema_linker":
                schema_fail.append({"question_id": it.question_id, "role": role, "cypher": cy,
                                    "error_type": vr.error_type, "schema_score": vr.schema_score,
                                    "properties_score": vr.properties_score})
    return (GateResult("3_syntax", not syntax_fail, syntax_fail),
            GateResult("4_schema_closure", not schema_fail, schema_fail))


def _labelled_cyphers(item: BenchmarkItem) -> list[tuple[str, str]]:
    out = [("default", item.cypher_default)]
    out += [(f"interp[{n}]", i["cypher"]) for n, i in enumerate(item.interpretations)]
    return out


def _execute_all(items: list[BenchmarkItem], driver, database: str) -> dict[str, list[dict]]:
    """Execute every gold Cypher once; cache result sets keyed by the query string."""
    cache: dict[str, list[dict]] = {}
    for it in items:
        for cy in gold_cyphers(it):
            if cy not in cache:
                res = db_executor(cy, driver, database=database)
                cache[cy] = res.result_set if res.success else None  # None marks exec failure
    return cache


def gate_nonempty(items: list[BenchmarkItem], cache: dict[str, list]) -> GateResult:
    """Gate 5: every gold Cypher executes success=True with a non-empty result set."""
    failures: list[dict] = []
    for it in items:
        for role, cy in _labelled_cyphers(it):
            rs = cache.get(cy)
            if rs is None:
                failures.append({"question_id": it.question_id, "role": role, "issue": "execution_failed", "cypher": cy})
            elif len(rs) == 0:
                failures.append({"question_id": it.question_id, "role": role, "issue": "empty_result", "cypher": cy})
    return GateResult("5_nonempty_execution", not failures, failures)


def gate_divergence(items: list[BenchmarkItem], cache: dict[str, list]) -> GateResult:
    """Gate 6: each ambiguous item's interpretation result sets are pairwise distinct."""
    failures: list[dict] = []
    for it in items:
        if not it.is_ambiguous:
            continue
        interp_cyphers = [i["cypher"] for i in it.interpretations]
        rss = [cache.get(cy) for cy in interp_cyphers]
        if any(rs is None for rs in rss):
            continue  # execution failure already reported by gate 5
        for a in range(len(rss)):
            for b in range(a + 1, len(rss)):
                if _result_sets_equal(rss[a], rss[b]):
                    failures.append({"question_id": it.question_id, "issue": "interpretations_not_distinct",
                                     "interp_a": it.interpretations[a]["interp"],
                                     "interp_b": it.interpretations[b]["interp"]})
    return GateResult("6_interpretation_divergence", not failures, failures)


# ── driver + orchestration ────────────────────────────────────────────────────────
def _open_driver():
    import neo4j

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]  # fail loud if unset
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def validate(benchmark_path: str, report_path: Optional[str] = None,
            profile: BenchmarkProfile = V3_PROFILE) -> dict:
    """Run all 8 gates against the live KG; write the report; return the report dict."""
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    gates: list[GateResult] = []

    # Gate 1: loads.
    try:
        items = load_benchmark(benchmark_path)
        gates.append(GateResult("1_loads", True, detail={"items": len(items)}))
    except (ValueError, TypeError) as e:
        report = {"benchmark": benchmark_path, "profile": profile.name, "passed": False,
                  "gates": {"1_loads": {"passed": False, "failures": [{"error": str(e)}]}}}
        _write_report(report, report_path)
        return report

    # Gates 2, 7, 8 (offline).
    gates.extend(run_offline_gates(items, profile))

    # Gates 3–6 (live).
    driver = _open_driver()
    try:
        components = build_cyver_components(driver, database if database != "neo4j" else None)
        g3, g4 = gate_syntax_and_schema(items, components)
        gates.extend([g3, g4])
        cache = _execute_all(items, driver, database)
        gates.append(gate_nonempty(items, cache))
        gates.append(gate_divergence(items, cache))
    finally:
        driver.close()

    passed = all(g.passed for g in gates)
    report = {"benchmark": benchmark_path, "profile": profile.name, "passed": passed,
              "gates": {g.name: g.as_dict() for g in sorted(gates, key=lambda g: g.name)}}
    _write_report(report, report_path)
    return report


def _write_report(report: dict, report_path: Optional[str]) -> None:
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2))


def _print_summary(report: dict) -> None:
    print(f"Benchmark: {report['benchmark']}")
    for name, g in report["gates"].items():
        status = "PASS" if g["passed"] else "FAIL"
        n = len(g.get("failures", []))
        print(f"  [{status}] {name}" + (f"  ({n} failure(s))" if n else ""))
        for f in g.get("failures", [])[:10]:
            print(f"        - {f}")
    print("OVERALL:", "PASS" if report["passed"] else "FAIL")


_PROFILES = {"v3": V3_PROFILE, "pole_external": POLE_EXTERNAL_PROFILE}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Executable benchmark validation harness (7.2).")
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--report", default=None)
    ap.add_argument("--profile", choices=sorted(_PROFILES), default="v3")
    args = ap.parse_args(argv)
    report = validate(args.benchmark, args.report, _PROFILES[args.profile])
    _print_summary(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
