"""8.1 — SL API instruct prompt variant + the byte-identical guard on the shared prompt.

Acceptance criterion 1 (partial): `build_sl_prompt` output is byte-identical to pre-8.1;
`build_sl_prompt_api` contains the format contract + the three few-shots.
"""
from __future__ import annotations

from pipeline.schema import build_pole_v3_schema_repr
from pipeline.schema_linker.prompts import (
    SL_SYSTEM,
    SL_SYSTEM_API,
    build_sl_prompt,
    build_sl_prompt_api,
)


# ── The shared completion prompt is frozen (training-data contract, 1.2) ────────────
def test_sl_system_is_byte_identical_to_pre_8_1():
    assert SL_SYSTEM == (
        "Task: Identify the relevant schema elements for the given question.\n"
        "Use only node labels, relationship types, and properties from the provided schema.\n"
        "Output a Cypher graph pattern showing which schema elements answer the question.\n"
        "Do not write a full Cypher query. Do not include WHERE clauses or RETURN clauses.\n"
        "Do not include entity-specific property values."
    )


def test_build_sl_prompt_is_byte_identical_to_pre_8_1():
    out = build_sl_prompt("Who is suspected?", "Nodes: Person, Incident")
    assert out == (
        f"{SL_SYSTEM}\n\n"
        "Schema:\nNodes: Person, Incident\n\n"
        "Question: Who is suspected?\n"
        "Schema pattern:"
    )
    # The API variant must not have leaked into the shared prompt.
    assert "Examples:" not in out
    assert SL_SYSTEM_API not in out


# ── The additive instruct variant states the contract + carries few-shots ───────────
def test_sl_system_api_states_the_output_contract():
    text = SL_SYSTEM_API
    assert "(:Person)" in text and "(Person)" in text          # colon rule, spelled both ways
    assert "{active: true}" in text                            # the only permitted property filter
    assert "-[:SUSPECTED_OF]->" in text                        # bracketed rel-type example
    for forbidden in ("RETURN", "WHERE", "fence"):
        assert forbidden in text
    assert "one line" in text.lower()


def test_build_sl_prompt_api_has_schema_question_layout_and_few_shots():
    schema_block = build_pole_v3_schema_repr().to_prompt_string(include_properties=True)
    out = build_sl_prompt_api("Where does James Whitfield currently live?", schema_block)
    # Same schema-block + trailing question/Schema-pattern layout as build_sl_prompt.
    assert out.startswith(SL_SYSTEM_API)
    assert f"Schema:\n{schema_block}" in out
    assert out.rstrip().endswith("Schema pattern:")
    assert "Question: Where does James Whitfield currently live?" in out
    # Three authored few-shots: single-hop role edge, temporal {active:true}, 2-hop chain.
    assert "Examples:" in out
    assert "(:Person)-[:SUSPECTED_OF]->(:Incident)" in out
    assert "(:Person)-[:LIVES_AT {active: true}]->(:Location)" in out
    assert "(:Case)-[:CONTAINS]->(:Incident)-[:OCCURRED_AT]->(:Location)" in out
