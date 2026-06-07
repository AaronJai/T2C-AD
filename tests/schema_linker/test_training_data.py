"""Contract tests for 1.2 Schema Linker training data (spec acceptance criteria)."""
from __future__ import annotations

import json

from pipeline.schema_linker.prompts import SL_SYSTEM, build_sl_prompt
from pipeline.schema_linker.training_data import (
    build_sl_dataset,
    build_sl_training_instance,
)


# ── Acceptance 1: prompt builder framing ──────────────────────────────────────────
def test_build_sl_prompt_framing():
    prompt = build_sl_prompt("Where does X live?", "<schema>")
    assert prompt.endswith("Schema pattern:")
    assert SL_SYSTEM in prompt
    assert "Question: Where does X live?" in prompt
    assert "Schema:\n<schema>" in prompt


# ── Acceptance 2: per-row instance ────────────────────────────────────────────────
def test_instance_kept_for_relationship_bearing_cypher():
    inst = build_sl_training_instance(
        "Where does James live?",
        "Node properties: Person, Location",
        "MATCH (p:Person {name:'James'})-[:LIVES_AT {active:true}]->(l:Location) "
        "RETURN l.address",
    )
    assert inst is not None
    assert set(inst.keys()) == {"prompt", "completion"}
    assert inst["completion"] == "(p:Person)-[:LIVES_AT {active:true}]->(l:Location)"
    assert inst["prompt"] == build_sl_prompt(
        "Where does James live?", "Node properties: Person, Location"
    )


def test_instance_none_for_node_only_cypher():
    assert build_sl_training_instance(
        "Find James.", "schema", "MATCH (p:Person {name:'James'}) RETURN p"
    ) is None


def test_instance_none_for_parse_failure():
    assert build_sl_training_instance("broken?", "schema", "RETURN 1") is None
    assert build_sl_training_instance("broken?", "schema", "") is None


# ── Acceptance 3: dataset build over a small mixed-format fixture ──────────────────
def _fixture_rows() -> list[dict]:
    """~20 dataset-shaped rows mixing schema formats and exclusion reasons.

    Kept (relationship-bearing): 14. Excluded node-only: 4. Excluded parse-fail: 2.
    """
    rel_cyphers = [
        "MATCH (c:Case)-[:CONTAINS]->(i:Incident)<-[:SUSPECTED_OF]-(p:Person) RETURN p.name",
        "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address",
        "MATCH (p:Person)-[:OWNS {from_date:'2020-01-01'}]->(v:Vehicle) RETURN v",
        "MATCH (p:Person)-[:USES_PHONE]->(ph:Phone) RETURN ph.number",
        "MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN i",
        "MATCH (p:Person)-[:VICTIM_OF]->(i:Incident) RETURN i.crime_type",
        "MATCH (o:Organisation)<-[:WORKS_FOR]-(p:Person) RETURN p",
        "MATCH (p:Person)-[:ASSOCIATED_WITH]-(q:Person) RETURN q.name",
        "MATCH (c:Communication)-[:INVOLVES]->(p:Person) RETURN p",
        "MATCH (e:Evidence)-[:FOUND_AT]->(l:Location) RETURN l",
        "MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) RETURN l.suburb",
        "MATCH (p:Person)-[:INVESTIGATES]->(c:Case) RETURN c",
        "MATCH (v:Vehicle)-[:SEEN_AT]->(l:Location) RETURN l",
        "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN i",
    ]
    node_only_cyphers = [
        "MATCH (p:Person {name:'James'}) RETURN p",
        "MATCH (l:Location {suburb:'CBD'}) RETURN l",
        "MATCH (v:Vehicle) RETURN v",
        "MATCH (i:Incident)-[*2]->(x) RETURN x",   # typeless traversal → node-only
    ]
    parse_fail_cyphers = ["RETURN 1", ""]

    # Cycle a few visibly different schema-block formats over the rows.
    schema_formats = [
        "Node properties:\n- **Person** - `name`: STRING\n- **Location** - `address`: STRING",
        'Graph schema: Relevant node labels and their properties: Person {name}, Location',
        '{"Person": {"properties": {"name": "STRING"}}, "Location": {"properties": {}}}',
        "Person | name:STRING\nLocation | address:STRING",
    ]
    rows: list[dict] = []
    all_cyphers = rel_cyphers + node_only_cyphers + parse_fail_cyphers
    for idx, cypher in enumerate(all_cyphers):
        rows.append(
            {
                "question": f"question {idx}?",
                "schema": schema_formats[idx % len(schema_formats)],
                "cypher": cypher,
            }
        )
    return rows


def test_build_sl_dataset(tmp_path):
    out_train = tmp_path / "train.jsonl"
    out_eval = tmp_path / "eval.jsonl"

    report = build_sl_dataset(_fixture_rows(), out_train, out_eval, eval_fraction=0.10, seed=13)

    # Exclusion counts match the fixture (syntax filtering deferred → no syntax exclusions).
    assert report["total_rows"] == 20
    assert report["kept"] == 14
    assert report["excluded_node_only"] == 4
    assert report["excluded_parse_fail"] == 2
    assert report["excluded_syntax_fail"] == 0
    assert report["train"] + report["eval"] == report["kept"]

    # Both files exist; every line parses as JSON with exactly the two-key contract.
    for path, count in ((out_train, report["train"]), (out_eval, report["eval"])):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == count
        for line in lines:
            record = json.loads(line)
            assert set(record.keys()) == {"prompt", "completion"}
            assert record["prompt"].endswith("Schema pattern:")
            assert "-[:" in record["completion"]


def test_build_sl_dataset_split_is_deterministic(tmp_path):
    rows = _fixture_rows()
    r1 = build_sl_dataset(rows, tmp_path / "t1.jsonl", tmp_path / "e1.jsonl", seed=13)
    r2 = build_sl_dataset(rows, tmp_path / "t2.jsonl", tmp_path / "e2.jsonl", seed=13)
    assert (tmp_path / "t1.jsonl").read_text(encoding="utf-8") == (
        tmp_path / "t2.jsonl"
    ).read_text(encoding="utf-8")
    assert r1 == r2
