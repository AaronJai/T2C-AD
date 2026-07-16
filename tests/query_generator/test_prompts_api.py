"""Phase-8-follow-up — QG API instruct prompt variant + the byte-identical guard on the shared
prompt (mirrors tests/schema_linker/test_prompts_api.py).

Fixes the property-hallucination / output-shape-mismatch failure documented in decisions-log:
the API QG never saw the schema's property list (`include_properties=False` at every call
site) or a single worked example of the gold's tight projection style.
"""
from __future__ import annotations

from pipeline.query_generator.prompts import (
    QG_SYSTEM_API,
    SYSTEM_PROMPT_WITH_PATTERN,
    SYSTEM_PROMPT_ZERO_SHOT,
    build_qg_prompt,
    build_qg_prompt_api,
)


# ── The shared completion prompt is frozen (training-data contract, 1.3) ────────────
def test_build_qg_prompt_is_byte_identical_to_pre_fix():
    out = build_qg_prompt("Who is suspected?", "Nodes: Person, Incident",
                          committed_pattern="(p:Person)-[:SUSPECTED_OF]->(i:Incident)")
    assert out == (
        f"{SYSTEM_PROMPT_WITH_PATTERN}\n\n"
        "Schema:\nNodes: Person, Incident\n\n"
        "Committed pattern:\n(p:Person)-[:SUSPECTED_OF]->(i:Incident)\n\n"
        "Question: Who is suspected?\n"
        "Cypher:"
    )
    # The API variant must not have leaked into the shared prompt.
    assert "Examples:" not in out
    assert QG_SYSTEM_API not in out


def test_build_qg_prompt_zero_shot_is_byte_identical_to_pre_fix():
    out = build_qg_prompt("Who is suspected?", "Nodes: Person, Incident")
    assert out == (
        f"{SYSTEM_PROMPT_ZERO_SHOT}\n\n"
        "Schema:\nNodes: Person, Incident\n\n"
        "Question: Who is suspected?\n"
        "Cypher:"
    )
    assert "Examples:" not in out


# ── The additive instruct variant states the contract + carries few-shots ───────────
def test_qg_system_api_states_the_output_contract():
    text = QG_SYSTEM_API
    assert "RETURN p.name" in text                      # tight-projection example
    assert "RETURN p, r, i" in text                      # the forbidden whole-node shape, named
    assert "RETURN DISTINCT" in text
    assert "invent" in text.lower() or "guess" in text.lower()   # anti-hallucination instruction


def test_build_qg_prompt_api_committed_pattern_has_schema_pattern_question_layout_and_few_shots():
    schema_block = "Nodes: Person, Incident\nProperties:\n  Incident: crime_type\n"
    pattern = "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    out = build_qg_prompt_api("Who is suspected of the robbery?", schema_block,
                              committed_pattern=pattern)
    assert out.startswith(QG_SYSTEM_API)
    assert f"Schema:\n{schema_block}" in out
    assert f"Committed pattern:\n{pattern}" in out
    assert out.rstrip().endswith("Cypher:")
    assert "Question: Who is suspected of the robbery?" in out
    # Four examples reused verbatim from the Phase 7.4 QG training data.
    assert "Examples:" in out
    assert "RETURN p.name" in out
    assert "RETURN DISTINCT p.name" in out
    assert "{active:true}" in out
    assert "RETURN l.address" in out


def test_build_qg_prompt_api_zero_shot_has_no_committed_pattern_block():
    out = build_qg_prompt_api("Who is suspected?", "Nodes: Person, Incident")
    assert "Committed pattern:" not in out
    assert "Examples:" in out
    assert out.rstrip().endswith("Cypher:")


def test_build_qg_prompt_api_carries_error_feedback():
    out = build_qg_prompt_api("Who is suspected?", "Nodes: Person, Incident",
                              committed_pattern="(p:Person)-[:SUSPECTED_OF]->(i:Incident)",
                              error_feedback="Syntax error: unexpected token")
    assert "Previous attempt (rejected by the validator" in out
    assert "Syntax error: unexpected token" in out
