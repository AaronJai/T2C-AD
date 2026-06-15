"""Contract tests for the Ambiguity Detector serialisers + output parsing (step 3.4)."""
from __future__ import annotations

from pipeline.ambiguity.detector import _parse_ad_output
from pipeline.ambiguity.prompts import _format_candidate_block, _format_entity_block
from pipeline.types import (
    CandidateMapping,
    EntityCandidate,
    EntityLookupResult,
    SchemaCandidate,
    SchemaElement,
)


def _rel(name: str, score: float, rank: int) -> SchemaCandidate:
    return SchemaCandidate(
        element=SchemaElement(
            element_type="relationship_type", name=name,
            source_label="Person", target_label="Incident",
        ),
        score=score,
        beam_rank=rank,
    )


def _entity(node_id: str, name: str, match: float, posterior: float) -> EntityCandidate:
    return EntityCandidate(
        node_label="Person", node_id=node_id, display_name=name,
        match_score=match, posterior_score=posterior,
    )


# ── Acceptance criterion 1: _format_candidate_block ────────────────────────────
def test_candidate_block_four_way_relationship():
    cm = CandidateMapping(
        question="who is connected to the Riverside robbery",
        mentions={
            "rel_1": [
                _rel("SUSPECTED_OF", 0.34, 1),
                _rel("WITNESSED", 0.28, 2),
                _rel("VICTIM_OF", 0.22, 3),
                _rel("INVESTIGATES", 0.16, 4),
            ]
        },
    )
    block = _format_candidate_block(cm)
    assert block.splitlines()[0] == "rel_1 candidates:"
    assert "  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]" in block
    assert "  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]" in block
    # ranked order preserved (highest score first)
    assert block.index("SUSPECTED_OF") < block.index("WITNESSED") < block.index("INVESTIGATES")


def test_candidate_block_empty_mapping():
    cm = CandidateMapping(question="q", mentions={})
    assert _format_candidate_block(cm) == "No schema candidates."


def test_candidate_block_node_label_renders_bare_name():
    cm = CandidateMapping(
        question="q",
        mentions={
            "node_1": [
                SchemaCandidate(
                    element=SchemaElement(element_type="node_label", name="Person"),
                    score=0.6, beam_rank=1,
                ),
                SchemaCandidate(
                    element=SchemaElement(element_type="node_label", name="Organisation"),
                    score=0.4, beam_rank=2,
                ),
            ]
        },
    )
    block = _format_candidate_block(cm)
    assert "  Person   [score: 0.60]" in block
    assert "  Organisation   [score: 0.40]" in block


def test_candidate_block_temporal_variant_shows_active_filter():
    cm = CandidateMapping(
        question="who owns the vehicle",
        mentions={
            "rel_1_temporal": [
                SchemaCandidate(
                    element=SchemaElement(
                        element_type="relationship_type", name="OWNS",
                        source_label="Person", target_label="Vehicle", parent="active",
                    ),
                    score=0.55, beam_rank=1,
                ),
                SchemaCandidate(
                    element=SchemaElement(
                        element_type="relationship_type", name="OWNS",
                        source_label="Person", target_label="Vehicle",
                    ),
                    score=0.45, beam_rank=2,
                ),
            ]
        },
    )
    block = _format_candidate_block(cm)
    assert "  (Person)-[:OWNS {active:true}]->(Vehicle)   [score: 0.55]" in block
    assert "  (Person)-[:OWNS]->(Vehicle)   [score: 0.45]" in block


# ── Acceptance criterion 2: _format_entity_block ───────────────────────────────
def test_entity_block_two_james():
    el = EntityLookupResult(
        question="show incidents linked to James",
        entity_mentions={
            "James": [
                _entity("PER-007", "James Whitfield", 0.95, 0.51),
                _entity("PER-013", "James Holloway", 0.93, 0.49),
            ]
        },
    )
    block = _format_entity_block(el)
    assert block.splitlines()[0] == '"James" matches:'
    assert "  1. Person: James Whitfield (PER-007) [match: 0.95]" in block
    assert "  2. Person: James Holloway (PER-013) [match: 0.93]" in block


def test_entity_block_empty():
    el = EntityLookupResult(question="q", entity_mentions={})
    assert _format_entity_block(el) == "No entity ambiguity detected."


def test_entity_block_all_mentions_without_matches():
    el = EntityLookupResult(question="q", entity_mentions={"Nobody": []})
    assert _format_entity_block(el) == "No entity ambiguity detected."


# ── Acceptance criterion 3: _parse_ad_output happy paths ───────────────────────
def test_parse_plain_json():
    res = _parse_ad_output(
        '{"is_ambiguous": true, "detected_types": ["schema"], "rationale": "x"}',
        0.5, 0.0, 0.6, 0.8,
    )
    assert res.is_ambiguous is True
    assert res.detected_types == ["schema"]
    assert res.llm_rationale == "x"
    assert res.schema_entropy == 0.5
    assert res.threshold_schema == 0.6


def test_parse_fenced_json():
    text = '```json\n{"is_ambiguous": true, "detected_types": ["entity"], "rationale": "y"}\n```'
    res = _parse_ad_output(text, 0.1, 0.9, 0.6, 0.8)
    assert res.is_ambiguous is True
    assert res.detected_types == ["entity"]


def test_parse_false_with_types_forces_empty():
    res = _parse_ad_output(
        '{"is_ambiguous": false, "detected_types": ["schema"], "rationale": "z"}',
        0.9, 0.0, 0.6, 0.8,
    )
    assert res.is_ambiguous is False
    assert res.detected_types == []


def test_parse_filters_invalid_types():
    res = _parse_ad_output(
        '{"is_ambiguous": true, "detected_types": ["schema", "bogus"], "rationale": ""}',
        0.5, 0.0, 0.6, 0.8,
    )
    assert res.detected_types == ["schema"]


def test_parse_true_empty_types_kept():
    res = _parse_ad_output(
        '{"is_ambiguous": true, "detected_types": [], "rationale": "unsure"}',
        0.5, 0.0, 0.6, 0.8,
    )
    assert res.is_ambiguous is True
    assert res.detected_types == []


def test_parse_json_with_prose_preamble():
    text = 'Here is my answer:\n{"is_ambiguous": true, "detected_types": ["intent"], "rationale": "p"}'
    res = _parse_ad_output(text, 0.1, 0.1, 0.6, 0.8)
    assert res.detected_types == ["intent"]


# ── Acceptance criterion 4: _parse_ad_output fallback ──────────────────────────
def test_parse_fallback_schema_threshold():
    res = _parse_ad_output("not json", schema_entropy=0.9, entity_entropy=0.0,
                           t_schema=0.6, t_entity=0.8)
    assert res.is_ambiguous is True
    assert res.detected_types == ["schema"]
    assert res.llm_rationale.startswith("FALLBACK")


def test_parse_fallback_below_thresholds_is_unambiguous():
    res = _parse_ad_output("", schema_entropy=0.1, entity_entropy=0.1,
                           t_schema=0.6, t_entity=0.8)
    assert res.is_ambiguous is False
    assert res.detected_types == []


def test_parse_fallback_both_thresholds_cleared():
    res = _parse_ad_output("garbage{not valid", schema_entropy=0.95, entity_entropy=0.95,
                           t_schema=0.6, t_entity=0.8)
    assert res.is_ambiguous is True
    assert res.detected_types == ["schema", "entity"]


def test_parse_missing_is_ambiguous_key_falls_back():
    res = _parse_ad_output('{"detected_types": ["schema"]}', schema_entropy=0.9,
                           entity_entropy=0.0, t_schema=0.6, t_entity=0.8)
    assert res.llm_rationale.startswith("FALLBACK")
    assert res.is_ambiguous is True
