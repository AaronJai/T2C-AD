"""Contract tests for 3.1 Schema Linker postprocessing (spec acceptance criteria 1-5)."""
from __future__ import annotations

import math

import pytest

from pipeline.llm import Completion
from pipeline.schema import build_pole_schema_repr
from pipeline.schema_linker.inference import extract_pattern_from_completion
from pipeline.schema_linker.linker import SchemaLinkerError
from pipeline.schema_linker.postprocessing import (
    align_beam_candidates,
    build_candidate_mapping,
    normalise_candidate_scores,
    parse_schema_pattern,
)

POLE = build_pole_schema_repr()


def _parse(text: str, score: float):
    return parse_schema_pattern(text, POLE, score)


# ── Acceptance 1: parse + schema validation ──────────────────────────────────────
def test_parse_valid_relationship():
    p = _parse("(p:Person)-[:SUSPECTED_OF]->(i:Incident)", -1.2)
    assert p.is_valid is True
    assert len(p.relationships) == 1
    src, rtype, tgt, direction, props = p.relationships[0]
    assert rtype == "SUSPECTED_OF"
    assert direction == "->"
    # Endpoints resolve to Person → Incident via the node aliases.
    alias_to_label = dict(p.nodes)
    assert alias_to_label[src] == "Person"
    assert alias_to_label[tgt] == "Incident"


def test_parse_out_of_schema_rel_is_invalid():
    p = _parse("(p:Person)-[:OWNED_BY]->(i:Incident)", -1.2)
    assert p.is_valid is False


def test_parse_out_of_schema_label_is_invalid():
    p = _parse("(p:Person)-[:SUSPECTED_OF]->(x:Spaceship)", -1.2)
    assert p.is_valid is False


def test_parse_ignores_trailing_double_dash_suffix():
    # The committed-pattern filter-suffix marker (decisions-log 2026-06-15): bare trailing `--`.
    p = _parse("(p:Person)-[:SUSPECTED_OF]->(i:Incident)--", -1.2)
    assert p.is_valid is True
    assert len(p.relationships) == 1
    p2 = _parse("(i:Incident)-[:OCCURRED_AT]->(l:Location)--, --", -1.2)
    assert p2.is_valid is True
    assert len(p2.relationships) == 1


# ── Acceptance 2: align varying relationships into one slot, dup merged in log-space ──
def test_align_four_person_incident_beams_one_slot_with_dup_merged():
    rels = ["SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES", "SUSPECTED_OF"]
    parsed = [
        _parse(f"(p:Person)-[:{r}]->(i:Incident)", -1.0)
        for r in rels
    ]
    raw = align_beam_candidates(parsed)
    assert set(raw) == {"rel_1"}
    elements = raw["rel_1"]
    names = {el.name for el, _ in elements}
    assert names == {"SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES"}
    # Four distinct elements (the duplicate SUSPECTED_OF beam merged, not a 5th entry).
    assert len(elements) == 4
    # The merged element has the higher log-score (two beams logsumexp'd).
    susp = next(s for el, s in elements if el.name == "SUSPECTED_OF")
    other = next(s for el, s in elements if el.name == "WITNESSED")
    assert susp == pytest.approx(-1.0 + math.log(2))
    assert other == pytest.approx(-1.0)
    # All resolve to the Person → Incident triple.
    assert all(el.source_label == "Person" and el.target_label == "Incident" for el, _ in elements)


# ── Acceptance 3: normalisation sums to ~1, ordered desc, beam_rank 1..n ──────────
def test_normalise_sums_to_one_ordered_with_rank():
    rels = ["SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES", "SUSPECTED_OF"]
    parsed = [_parse(f"(p:Person)-[:{r}]->(i:Incident)", -1.0) for r in rels]
    mentions = normalise_candidate_scores(align_beam_candidates(parsed))
    cands = mentions["rel_1"]
    assert sum(c.score for c in cands) == pytest.approx(1.0)
    assert [c.beam_rank for c in cands] == [1, 2, 3, 4]
    assert all(cands[i].score >= cands[i + 1].score for i in range(len(cands) - 1))
    assert cands[0].element.name == "SUSPECTED_OF"
    assert cands[0].score == pytest.approx(0.4)


# ── Acceptance 4: single-candidate vs multi-candidate mapping ─────────────────────
def test_build_single_candidate_when_all_beams_identical():
    comps = [
        Completion(text="(p:Person)-[:SUSPECTED_OF]->(i:Incident)--", score=-1.0, rank=r)
        for r in range(1, 6)
    ]
    mapping = build_candidate_mapping("who is suspected?", comps, POLE)
    # One candidate per element, all score 1.0 → ~0 entropy downstream.
    assert "rel_1" in mapping.mentions
    for cands in mapping.mentions.values():
        assert len(cands) == 1
        assert cands[0].score == pytest.approx(1.0)
    assert mapping.mentions["rel_1"][0].element.name == "SUSPECTED_OF"
    assert mapping.beam_k == 5


def test_build_multi_candidate_when_beams_differ():
    rels = ["SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES", "SUSPECTED_OF"]
    comps = [
        Completion(text=f"(p:Person)-[:{r}]->(i:Incident)--", score=-1.0, rank=i)
        for i, r in enumerate(rels, 1)
    ]
    mapping = build_candidate_mapping("connected to an incident?", comps, POLE)
    assert len(mapping.mentions["rel_1"]) == 4


def test_build_raises_when_no_valid_beams():
    comps = [Completion(text="(p:Person)-[:OWNED_BY]->(x:Spaceship)", score=-1.0, rank=1)]
    with pytest.raises(SchemaLinkerError):
        build_candidate_mapping("nonsense", comps, POLE)


# ── Acceptance 5: temporal active-filter variant → rel_n_temporal slot ────────────
def test_temporal_active_filter_produces_temporal_slot():
    parsed = [
        _parse("(p:Person)-[:LIVES_AT {active:true}]->(l:Location)", -1.0),
        _parse("(p:Person)-[:LIVES_AT {active:true}]->(l:Location)", -1.0),
        _parse("(p:Person)-[:LIVES_AT]->(l:Location)", -1.0),
        _parse("(p:Person)-[:LIVES_AT]->(l:Location)", -1.0),
    ]
    raw = align_beam_candidates(parsed)
    assert "rel_1_temporal" in raw
    # Same rel type, two variants distinguished by the active marker on `parent`.
    elements = [el for el, _ in raw["rel_1_temporal"]]
    assert {el.name for el in elements} == {"LIVES_AT"}
    assert {el.parent for el in elements} == {"active", None}
    # No type-level slot, since the type itself does not vary.
    assert "rel_1" not in raw


def test_extract_pattern_from_completion_takes_first_nonempty_line():
    assert extract_pattern_from_completion(
        "\n  (p:Person)-[:SUSPECTED_OF]->(i:Incident)  \nextra"
    ) == "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"


# ── 8.1: tolerant extraction (fenced + prose-wrapped) — bare pattern stays identical ──
def test_extract_strips_markdown_fence():
    text = "```cypher\n(:Person)-[:SUSPECTED_OF]->(:Incident)\n```"
    assert extract_pattern_from_completion(text) == "(:Person)-[:SUSPECTED_OF]->(:Incident)"


def test_extract_skips_prose_line_and_returns_pattern():
    text = "Here is the schema pattern for your question:\n(:Person)-[:VICTIM_OF]->(:Incident)"
    assert extract_pattern_from_completion(text) == "(:Person)-[:VICTIM_OF]->(:Incident)"


def test_extract_bare_pattern_is_byte_identical():
    # The local fine-tuned path (a tidy one-line pattern, no fence/prose) is unchanged.
    assert extract_pattern_from_completion(
        "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    ) == "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"


# ── 8.1: colon-less label repair (instruct-model `(Person)` house style) ──────────────
def test_colonless_labels_repaired_both_endpoints():
    p = _parse("(Person)-[:SUSPECTED_OF]->(Incident)", -1.2)
    assert p.is_valid is True
    assert len(p.relationships) == 1
    src, rtype, tgt, direction, _props = p.relationships[0]
    alias_to_label = dict(p.nodes)
    assert alias_to_label[src] == "Person"      # bare (Person) treated as the label
    assert alias_to_label[tgt] == "Incident"
    # The repaired nodes are anonymous (no real alias survives).
    assert all(alias.startswith("_n") for alias, _label in p.nodes)


def test_real_aliases_are_not_treated_as_labels():
    # (p) and (x) are NOT schema labels, so they stay label-less real aliases (unchanged).
    p = _parse("(p:Person)-[:SUSPECTED_OF]->(x)", -1.2)
    assert dict(p.nodes)["p"] == "Person"
    assert ("x", None) in p.nodes                # (x) → alias 'x', no label; not repaired


def test_colonless_repair_leaves_labelled_nodes_identical():
    # (p:Person) behaves exactly as before the repair path existed.
    p = _parse("(p:Person)-[:SUSPECTED_OF]->(i:Incident)", -1.2)
    assert p.is_valid is True
    assert dict(p.nodes) == {"p": "Person", "i": "Incident"}


# ── 8.1: extra property maps must not invalidate a beam (only `active` is load-bearing) ─
def test_extra_rel_property_map_does_not_invalidate():
    p = _parse("(p:Person)-[:SUSPECTED_OF {crime_type: 'homicide'}]->(i:Incident)", -1.2)
    assert p.is_valid is True                    # schema-correct rel + label; extra prop ignored
    _src, rtype, _tgt, _dir, props = p.relationships[0]
    assert rtype == "SUSPECTED_OF"
    assert "crime_type" in props                 # captured, but non-invalidating


def test_extra_node_property_map_does_not_invalidate():
    p = _parse("(p:Person {name: 'Alice'})-[:VICTIM_OF]->(i:Incident)", -1.2)
    assert p.is_valid is True
