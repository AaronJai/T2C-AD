"""Offline contract tests for the benchmark validation harness (step 7.2).

No Neo4j: exercises the DB-free gates on small hand-built fixtures per acceptance
criterion 1 — gate 2 catches a wrong distribution / duplicate id / duplicate text, and
gate 7 catches a mislabeled num_hops and an over-3-hop gold Cypher. Also confirms the
offline gates pass on the real committed benchmark-v3.json (a bonus over criterion 3).
The live gates (3–6) run for real on Kaya.
"""
from __future__ import annotations

from pathlib import Path

from experiments.validate_benchmark import (EXPECTED_DISTRIBUTION, POLE_EXTERNAL_PROFILE,
                                            V3_PROFILE, gate_coverage, gate_distribution,
                                            gate_hops, relationship_count, rel_types_in,
                                            run_offline_gates)
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.types import BenchmarkItem

ROOT = Path(__file__).resolve().parents[1]


def _item(qid: str, question: str, num_hops: int, atype, cypher_default: str,
          interps: list[str] | None = None) -> BenchmarkItem:
    interp_objs = [{"interp": f"i{n}", "cypher": c} for n, c in enumerate(interps or [])]
    return BenchmarkItem(
        question_id=qid, question=question, num_hops=num_hops,
        is_ambiguous=atype is not None, ambiguity_type=atype,
        default_interp="d", cypher_default=cypher_default, interpretations=interp_objs,
    )


def _balanced_120() -> list[BenchmarkItem]:
    """A minimally-valid 120-item set with the exact expected distribution + unique ids/text."""
    items: list[BenchmarkItem] = []
    n = 0
    cy = "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name"
    for atype, count in EXPECTED_DISTRIBUTION.items():
        for _ in range(count):
            n += 1
            interps = ["MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN p.name",
                       "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident) RETURN p.name"] if atype else None
            items.append(_item(f"Q-{n:03d}", f"question {n}", 1, atype, cy, interps))
    return items


# ── gate 2: distribution ──────────────────────────────────────────────────────────
def test_gate2_passes_on_balanced_set():
    assert gate_distribution(_balanced_120()).passed


def test_gate2_catches_wrong_distribution():
    items = _balanced_120()
    # Flip one 'schema' item to 'null' → 41 null / 19 schema.
    items[-1] = _item(items[-1].question_id, items[-1].question, 1, None,
                      items[-1].cypher_default)
    res = gate_distribution(items)
    assert not res.passed
    assert any(f["issue"] == "distribution" for f in res.failures)


def test_gate2_catches_wrong_count():
    res = gate_distribution(_balanced_120()[:118])
    assert not res.passed
    assert any(f["issue"] == "count" for f in res.failures)


def test_gate2_catches_duplicate_id_and_text():
    items = _balanced_120()
    items[1] = _item(items[0].question_id, items[0].question, 1, items[1].ambiguity_type,
                     items[1].cypher_default,
                     ["MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN p.name",
                      "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident) RETURN p.name"])
    res = gate_distribution(items)
    assert not res.passed
    issues = {f["issue"] for f in res.failures}
    assert "duplicate_question_id" in issues
    assert "duplicate_question_text" in issues


# ── gate 7: hop honesty ───────────────────────────────────────────────────────────
def test_gate7_passes_when_hops_match():
    items = [_item("Q-1", "q1", 1, None, "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name"),
             _item("Q-2", "q2", 2, None, "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)-[:OCCURRED_AT]->(l:Location) RETURN l.address")]
    assert gate_hops(items).passed


def test_gate7_catches_mislabeled_num_hops():
    # Declared 2 but the default is a single relationship.
    items = [_item("Q-1", "q1", 2, None, "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name")]
    res = gate_hops(items)
    assert not res.passed
    assert res.failures[0]["issue"] == "num_hops_mismatch"
    assert res.failures[0]["declared"] == 2 and res.failures[0]["actual"] == 1


def test_gate7_catches_over_three_hops():
    four = ("MATCH (a:Person)-[:OWNS]->(b:Vehicle)-[:OWNS]->(c:Person)-[:OWNS]->"
            "(d:Vehicle)-[:OWNS]->(e:Person) RETURN a")
    items = [_item("Q-1", "q1", relationship_count(four), None, four)]
    res = gate_hops(items)
    assert not res.passed
    assert any(f["issue"] == "exceeds_max_hops" for f in res.failures)


# ── gate 8: coverage ──────────────────────────────────────────────────────────────
def test_gate8_catches_missing_relationship_type():
    # Only SUSPECTED_OF is exercised; the other 10 types are missing.
    items = [_item(f"Q-{n}", f"q{n}", 1, None,
                   "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name") for n in range(5)]
    res = gate_coverage(items)
    assert not res.passed
    missing = {f["relationship_type"] for f in res.failures}
    assert "OCCURRED_AT" in missing and "CALLED" in missing


def test_rel_types_in_handles_multitype():
    assert rel_types_in("MATCH (p)-[:A|B|C]->(i) RETURN p") == {"A", "B", "C"}
    assert rel_types_in("MATCH (p)-[r:CALLED {x:1}]->(b) RETURN p") == {"CALLED"}
    assert rel_types_in("MATCH (p)-[r]->(i) RETURN p") == set()


# ── real committed benchmark passes the offline gates ─────────────────────────────
def test_real_benchmark_offline_gates_pass():
    items = load_benchmark(str(ROOT / "data" / "benchmark-v3.json"))
    assert len(items) == 120
    for g in run_offline_gates(items):
        assert g.passed, (g.name, g.failures[:5])


# ── BenchmarkProfile (9.2) ──────────────────────────────────────────────────────────
def _balanced_pole_external(n_total: int = 100) -> list[BenchmarkItem]:
    """A minimally-valid pole_external-shaped set: 20 each of None/schema/entity/intent/temporal."""
    items: list[BenchmarkItem] = []
    n = 0
    cy = "MATCH (p:Person)-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"
    for atype, count in POLE_EXTERNAL_PROFILE.expected_distribution.items():
        for _ in range(count):
            n += 1
            interps = ["MATCH (p:Person)-[:KNOWS]->(p2:Person) RETURN p2.name",
                       "MATCH (p:Person)-[:FAMILY_REL]->(p2:Person) RETURN p2.name"] if atype else None
            items.append(_item(f"Q-POLE-{n:03d}", f"pole question {n}", 1, atype, cy, interps))
    return items[:n_total]


def test_gate2_pole_external_profile_passes_on_balanced_set():
    assert gate_distribution(_balanced_pole_external(), POLE_EXTERNAL_PROFILE).passed


def test_gate2_pole_external_profile_catches_wrong_distribution():
    items = _balanced_pole_external()
    # Flip one 'schema' item to 'null' → 21 null / 19 schema, still 100 total.
    idx = next(i for i, it in enumerate(items) if it.ambiguity_type == "schema")
    items[idx] = _item(items[idx].question_id, items[idx].question, 1, None, items[idx].cypher_default)
    res = gate_distribution(items, POLE_EXTERNAL_PROFILE)
    assert not res.passed
    assert any(f["issue"] == "distribution" for f in res.failures)


def test_gate2_v3_profile_is_default_and_unaffected_by_pole_external():
    # Same fixture, default (v3) profile — count 100 != v3's expected_total 120.
    res = gate_distribution(_balanced_pole_external())
    assert not res.passed
    assert any(f["issue"] == "count" for f in res.failures)


def test_gate8_pole_external_profile_catches_zero_coverage_relationship_type():
    # Only CURRENT_ADDRESS is exercised; the other 16 pole_external types are missing.
    items = [_item(f"Q-POLE-{n}", f"pole q{n}", 1, None,
                   "MATCH (p:Person)-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address")
             for n in range(3)]
    res = gate_coverage(items, POLE_EXTERNAL_PROFILE)
    assert not res.passed
    missing = {f["relationship_type"] for f in res.failures}
    assert "PARTY_TO" in missing and "FAMILY_REL" in missing
    # min_coverage=1 (relaxed from v3's 3): a type appearing in exactly 1 item clears the gate.
    assert "CURRENT_ADDRESS" not in missing


def test_gate8_pole_external_profile_min_coverage_is_one():
    assert POLE_EXTERNAL_PROFILE.min_coverage == 1
    assert V3_PROFILE.min_coverage == 3
