"""Contract tests for 1.3 Query Generator training data (spec acceptance criteria)."""
from __future__ import annotations

import json

from pipeline.query_generator.prompts import (
    SYSTEM_PROMPT_WITH_PATTERN,
    SYSTEM_PROMPT_ZERO_SHOT,
    build_qg_prompt,
)
from pipeline.query_generator.training_data import (
    build_qg_dataset,
    build_qg_training_instance,
)
from pipeline.schema import build_pole_schema_repr
from pipeline.schema_linker.pattern_extraction import extract_schema_pattern
from pipeline.types import CandidateMapping, SchemaCandidate, SchemaElement


# ── Acceptance 1: prompt builder, both modes ──────────────────────────────────────
def test_build_qg_prompt_with_pattern():
    prompt = build_qg_prompt(
        "Where does X live?",
        "<schema block>",
        committed_pattern="(p:Person)-[:LIVES_AT]->(l:Location)",
    )
    assert SYSTEM_PROMPT_WITH_PATTERN in prompt
    assert "Committed pattern:\n(p:Person)-[:LIVES_AT]->(l:Location)" in prompt
    assert "Schema:\n<schema block>" in prompt
    assert "Question: Where does X live?" in prompt
    assert prompt.endswith("Cypher:")


def test_build_qg_prompt_zero_shot_omits_pattern():
    prompt = build_qg_prompt("Where does X live?", "<schema block>")
    assert SYSTEM_PROMPT_ZERO_SHOT in prompt
    assert SYSTEM_PROMPT_WITH_PATTERN not in prompt
    assert "Committed pattern:" not in prompt
    assert prompt.endswith("Cypher:")


def test_build_qg_prompt_empty_pattern_is_zero_shot():
    # An empty string is falsy → zero-shot, never an empty Committed pattern block.
    assert "Committed pattern:" not in build_qg_prompt("q?", "<schema>", committed_pattern="")


# ── Acceptance 1b: error_feedback retry block ───────
def test_build_qg_prompt_without_feedback_is_byte_identical_to_training_format():
    """error_feedback=None must produce the EXACT training-time prompt — the guarantee that
    the in-flight fine-tune is unaffected by the retry-feedback amendment."""
    expected_with_pattern = (
        f"{SYSTEM_PROMPT_WITH_PATTERN}\n\n"
        "Schema:\n<schema block>\n\n"
        "Committed pattern:\n(p:Person)-[:LIVES_AT]->(l:Location)\n\n"
        "Question: Where does X live?\n"
        "Cypher:"
    )
    assert build_qg_prompt(
        "Where does X live?", "<schema block>",
        committed_pattern="(p:Person)-[:LIVES_AT]->(l:Location)",
    ) == expected_with_pattern

    expected_zero_shot = (
        f"{SYSTEM_PROMPT_ZERO_SHOT}\n\n"
        "Schema:\n<schema block>\n\n"
        "Question: Where does X live?\n"
        "Cypher:"
    )
    assert build_qg_prompt("Where does X live?", "<schema block>") == expected_zero_shot


def test_build_qg_prompt_with_feedback_inserts_block_before_question():
    prompt = build_qg_prompt(
        "Where does X live?", "<schema block>",
        committed_pattern="(p:Person)-[:LIVES_AT]->(l:Location)",
        error_feedback="MATCH (p:Person -> RETURN p\nValidation errors (syntax): unbalanced",
    )
    assert "Previous attempt (rejected by the validator" in prompt
    assert "unbalanced" in prompt
    # Block sits between the committed pattern and the question, prompt still ends with Cypher:
    assert prompt.index("Committed pattern:") < prompt.index("Previous attempt") < prompt.index("Question:")
    assert prompt.endswith("Cypher:")
    # Zero-shot mode carries the block too (C1 retries).
    zs = build_qg_prompt("q?", "<schema>", error_feedback="bad query\nErrors: x")
    assert "Previous attempt (rejected by the validator" in zs
    assert zs.index("Schema:") < zs.index("Previous attempt") < zs.index("Question:")


# ── Acceptance 2: per-row instance ────────────────────────────────────────────────
def test_instance_kept_for_parseable_cypher():
    gold = (
        "MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) "
        "RETURN l.address, l.suburb"
    )
    inst = build_qg_training_instance("Where does James live?", "Person, Location", gold)
    assert inst is not None
    assert set(inst.keys()) == {"prompt", "completion"}
    # completion is the gold Cypher verbatim (QG target is the full query, not the pattern).
    assert inst["completion"] == gold
    assert inst["prompt"] == build_qg_prompt(
        "Where does James live?",
        "Person, Location",
        committed_pattern="(p:Person)-[:LIVES_AT {active:true}]->(l:Location)",
    )


def test_instance_kept_for_node_only_cypher():
    # QG keeps node-only rows — only parse failure excludes.
    gold = "MATCH (p:Person {name:'James'}) RETURN p.name"
    inst = build_qg_training_instance("Find James.", "Person", gold)
    assert inst is not None
    assert inst["completion"] == gold


def test_instance_none_for_parse_failure():
    assert build_qg_training_instance("broken?", "schema", "RETURN 1") is None
    assert build_qg_training_instance("broken?", "schema", "") is None


# ── Acceptance 3: train↔inference format-consistency guard ─────────────────────────
def test_committed_pattern_format_matches_inference_producer():
    """A SchemaMapping.cypher_syntax produced by CandidateMapping.top1_mapping() (0.1) — the
    inference-side committed-pattern producer — slots into build_qg_prompt with the same
    `(var:Label)-[:TYPE]->(var:Label)` shape as extract_schema_pattern's output for the
    equivalent gold Cypher (the train-side producer)."""
    rel = SchemaElement(
        element_type="relationship_type",
        name="LIVES_AT",
        source_label="Person",
        target_label="Location",
    )
    candidate_mapping = CandidateMapping(
        question="Where does James live?",
        mentions={"lives at": [SchemaCandidate(element=rel, score=1.0, beam_rank=1)]},
    )
    inference_pattern = candidate_mapping.top1_mapping().cypher_syntax

    # The train-side pattern for the equivalent gold Cypher.
    train_pattern = extract_schema_pattern(
        "MATCH (p:Person)-[:LIVES_AT]->(l:Location) RETURN l.address"
    )

    # Same syntactic style from both producers — the load-bearing consistency claim.
    assert inference_pattern == "(p:Person)-[:LIVES_AT]->(l:Location)"
    assert inference_pattern == train_pattern

    # And it slots into the prompt with the POLE schema block without structural surprises.
    schema_block = build_pole_schema_repr().to_prompt_string(include_properties=False)
    prompt = build_qg_prompt("Where does James live?", schema_block, committed_pattern=inference_pattern)
    assert f"Committed pattern:\n{inference_pattern}\n" in prompt
    assert prompt.endswith("Cypher:")


# ── Dataset build over a small fixture ────────────────────────────────────────────
def _fixture_rows() -> list[dict]:
    """Dataset-shaped rows: 5 relationship-bearing + 3 node-only kept; 2 parse-fail excluded."""
    kept_cyphers = [
        "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address",
        "MATCH (c:Case)-[:CONTAINS]->(i:Incident) RETURN i",
        "MATCH (p:Person)-[:OWNS]->(v:Vehicle) RETURN v.plate",
        "MATCH (p:Person)-[:USES_PHONE]->(ph:Phone) RETURN ph.number",
        "MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN i.crime_type",
        "MATCH (p:Person {name:'James'}) RETURN p",          # node-only — KEPT by QG
        "MATCH (l:Location {suburb:'CBD'}) RETURN l.address",  # node-only — KEPT by QG
        "MATCH (v:Vehicle) RETURN v",                          # node-only — KEPT by QG
    ]
    parse_fail_cyphers = ["RETURN 1", ""]

    schema_formats = [
        "Node properties:\n- **Person** - `name`: STRING",
        'Graph schema: Person {name}, Location',
        '{"Person": {"properties": {"name": "STRING"}}}',
        "Person | name:STRING",
    ]
    rows: list[dict] = []
    for idx, cypher in enumerate(kept_cyphers + parse_fail_cyphers):
        rows.append(
            {
                "question": f"question {idx}?",
                "schema": schema_formats[idx % len(schema_formats)],
                "cypher": cypher,
            }
        )
    return rows


def test_build_qg_dataset(tmp_path):
    out_train = tmp_path / "train.jsonl"
    out_eval = tmp_path / "eval.jsonl"

    report = build_qg_dataset(_fixture_rows(), out_train, out_eval, eval_fraction=0.10, seed=13)

    assert report["total_rows"] == 10
    assert report["kept"] == 8                 # node-only rows are kept by QG
    assert report["excluded_parse_fail"] == 2
    assert report["train"] + report["eval"] == report["kept"]

    for path, count in ((out_train, report["train"]), (out_eval, report["eval"])):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == count
        for line in lines:
            record = json.loads(line)
            assert set(record.keys()) == {"prompt", "completion"}
            assert "Committed pattern:" in record["prompt"]
            assert record["prompt"].endswith("Cypher:")
            # completion is a full Cypher query (starts with MATCH), not just the pattern.
            assert record["completion"].startswith("MATCH")


def test_build_qg_dataset_split_is_deterministic(tmp_path):
    rows = _fixture_rows()
    r1 = build_qg_dataset(rows, tmp_path / "t1.jsonl", tmp_path / "e1.jsonl", seed=13)
    r2 = build_qg_dataset(rows, tmp_path / "t2.jsonl", tmp_path / "e2.jsonl", seed=13)
    assert (tmp_path / "t1.jsonl").read_text(encoding="utf-8") == (
        tmp_path / "t2.jsonl"
    ).read_text(encoding="utf-8")
    assert r1 == r2
