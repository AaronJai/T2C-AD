"""Contract tests for the Disambiguator (step 3.5): prompt assembly + output parsing."""
from __future__ import annotations

import pytest

from pipeline.disambiguator.disambiguator import _parse_disambiguator_output, disambiguator
from pipeline.disambiguator.prompts import _format_tried_block, build_disambiguator_prompt
from pipeline.types import (
    AmbiguityResult,
    CandidateMapping,
    EntityCandidate,
    EntityLookupResult,
    SchemaCandidate,
    SchemaElement,
    SchemaMapping,
)


# ── Builders ──────────────────────────────────────────────────────────────────
def _rel(name: str, score: float, rank: int) -> SchemaCandidate:
    return SchemaCandidate(
        element=SchemaElement(
            element_type="relationship_type", name=name,
            source_label="Person", target_label="Incident",
        ),
        score=score,
        beam_rank=rank,
    )


def _mapping() -> CandidateMapping:
    return CandidateMapping(
        question="who is connected to the Riverside robbery",
        mentions={
            "rel_1": [
                _rel("SUSPECTED_OF", 0.42, 1),
                _rel("WITNESSED", 0.31, 2),
                _rel("VICTIM_OF", 0.18, 3),
                _rel("INVESTIGATES", 0.09, 4),
            ]
        },
    )


def _ambiguity(types) -> AmbiguityResult:
    return AmbiguityResult(
        is_ambiguous=True, detected_types=types,
        schema_entropy=0.9, entity_entropy=0.0, llm_rationale="",
    )


def _entity_lookup() -> EntityLookupResult:
    return EntityLookupResult(question="q", entity_mentions={})


def _committed(name: str) -> SchemaMapping:
    el = SchemaElement(
        element_type="relationship_type", name=name,
        source_label="Person", target_label="Incident",
    )
    return SchemaMapping(
        question="q", committed={"rel_1": el},
        cypher_syntax=f"(p:Person)-[:{name}]->(i:Incident)",
        resolution_mode="automated",
    )


# ── Criterion 1: _format_tried_block ────────────────────────────────────────────
def test_tried_block_empty():
    assert _format_tried_block([]) == ""


def test_tried_block_lists_both_cypher_syntax():
    block = _format_tried_block([_committed("SUSPECTED_OF"), _committed("WITNESSED")])
    assert block.startswith("Previously tried interpretations (DO NOT repeat these):")
    assert "  - (p:Person)-[:SUSPECTED_OF]->(i:Incident)" in block
    assert "  - (p:Person)-[:WITNESSED]->(i:Incident)" in block
    assert block.endswith("\n\n")  # trailing blank line


# ── Criterion 2: build_disambiguator_prompt ─────────────────────────────────────
def test_build_prompt_includes_all_sections():
    prompt = build_disambiguator_prompt(
        "who is connected to the Riverside robbery", _ambiguity(["schema"]),
        _mapping(), _entity_lookup(), [_committed("SUSPECTED_OF")],
    )
    assert "Question: who is connected to the Riverside robbery" in prompt
    assert "Ambiguity type: schema" in prompt
    assert "rel_1 candidates:" in prompt                       # candidate block
    assert "(Person)-[:SUSPECTED_OF]->(Incident)" in prompt
    assert "No entity ambiguity detected." in prompt           # entity block
    assert "Previously tried interpretations (DO NOT repeat these):" in prompt
    assert "Select the single best interpretation" in prompt


def test_build_prompt_empty_types_renders_unknown():
    prompt = build_disambiguator_prompt(
        "q", _ambiguity([]), _mapping(), _entity_lookup(), [],
    )
    assert "Ambiguity type: unknown" in prompt
    # no tried block when previously_tried is empty
    assert "Previously tried" not in prompt


# ── Criterion 3: clean parse → SchemaMapping ────────────────────────────────────
def test_parse_clean_json_builds_schema_mapping():
    text = ('{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", '
            '"rationale": "x"}')
    sm = _parse_disambiguator_output(text, "q", _mapping(), [])
    assert isinstance(sm, SchemaMapping)
    assert sm.cypher_syntax == "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    assert sm.resolution_mode == "automated"


def test_parse_strips_code_fences():
    text = '```json\n{"committed_pattern": "(p:Person)-[r]->(i:Incident)", "rationale": "y"}\n```'
    sm = _parse_disambiguator_output(text, "q", _mapping(), [])
    assert sm is not None and sm.cypher_syntax == "(p:Person)-[r]->(i:Incident)"


def test_committed_metadata_from_known_candidate():
    text = '{"committed_pattern": "(p:Person)-[:WITNESSED]->(i:Incident)", "rationale": "z"}'
    sm = _parse_disambiguator_output(text, "q", _mapping(), [])
    assert sm is not None
    assert sm.committed["rel_1"].name == "WITNESSED"
    assert sm.committed["rel_1"].source_label == "Person"
    assert sm.committed["rel_1"].target_label == "Incident"


# ── Criterion 4: null → None; repeat → fallback ─────────────────────────────────
def test_null_committed_pattern_returns_none():
    text = '{"committed_pattern": null, "rationale": "exhausted"}'
    assert _parse_disambiguator_output(text, "q", _mapping(), []) is None


def test_repeat_falls_back_to_next_best_untried():
    tried = [_committed("SUSPECTED_OF")]  # top-1 already tried
    text = '{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", "rationale": "r"}'
    sm = _parse_disambiguator_output(text, "q", _mapping(), tried)
    assert sm is not None
    # next-highest untried candidate is WITNESSED (0.31)
    assert sm.cypher_syntax == "(p:Person)-[:WITNESSED]->(i:Incident)"


def test_malformed_json_falls_back_to_best_untried():
    sm = _parse_disambiguator_output("not json at all", "q", _mapping(), [])
    assert sm is not None
    # no prior tries → argmax SUSPECTED_OF
    assert sm.cypher_syntax == "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"


def test_fallback_returns_none_when_all_candidates_exhausted():
    tried = [
        _committed("SUSPECTED_OF"), _committed("WITNESSED"),
        _committed("VICTIM_OF"), _committed("INVESTIGATES"),
    ]
    assert _parse_disambiguator_output("garbage", "q", _mapping(), tried) is None


# ── Criterion 5: interactive mode ───────────────────────────────────────────────
def test_interactive_mode_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        disambiguator(
            "q", _ambiguity(["schema"]), _mapping(), _entity_lookup(),
            dis_llm=None, previously_tried=[], mode="interactive",
        )
