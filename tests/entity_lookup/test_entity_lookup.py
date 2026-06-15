# tests/entity_lookup/test_entity_lookup.py
"""Contract tests for 3.2 Entity Lookup (no DB; hand-built CachedNodes)."""
from __future__ import annotations

import pytest

from pipeline.entity_lookup.cache import CachedNode, EntityCache
from pipeline.entity_lookup.lookup import _candidate_labels, entity_lookup
from pipeline.entity_lookup.matcher import compute_posterior_scores, fuzzy_match_score
from pipeline.entity_lookup.span_extractor import extract_entity_spans
from pipeline.types import (
    CandidateMapping,
    EntityLookupResult,
    SchemaCandidate,
    SchemaElement,
)


def _person(node_id: str, *names: str) -> CachedNode:
    return CachedNode(
        node_id=node_id,
        label="Person",
        name_values=list(names),
        display_name=names[0],
        extra={"role": "suspect"},
    )


# ── Criterion 1: span extraction ────────────────────────────────────────────────
def test_extract_spans_longest_first_excludes_question_word():
    spans = extract_entity_spans("Show incidents linked to James Whitfield in Northbridge")
    assert spans == ["James Whitfield", "Northbridge"]


def test_extract_spans_dedup_and_no_subspans():
    spans = extract_entity_spans("List cases involving James Whitfield and James Cole")
    # both full names kept; bare "James" dropped as a subspan of a longer retained span
    assert "James Whitfield" in spans
    assert "James Cole" in spans
    assert "James" not in spans


def test_extract_spans_operation_and_quoted():
    spans = extract_entity_spans('Find evidence for Operation Ironside tagged "red folder"')
    assert "Operation Ironside" in spans
    assert "red folder" in spans


# ── Criterion 2: fuzzy match + posterior ─────────────────────────────────────────
def test_fuzzy_match_score_partial_name_high():
    assert fuzzy_match_score("James", "James Whitfield") >= 0.75


def test_posterior_two_james_sum_to_one_ordered_desc():
    nodes = [_person("PER-007", "James Whitfield"), _person("PER-013", "James Cole")]
    scored = compute_posterior_scores("James", nodes)
    assert len(scored) == 2
    posteriors = [p for _, _, p in scored]
    assert posteriors == sorted(posteriors, reverse=True)
    assert sum(posteriors) == pytest.approx(1.0)


def test_posterior_empty_when_below_threshold():
    nodes = [_person("PER-007", "James Whitfield")]
    assert compute_posterior_scores("Zzyzx Nonexistent", nodes) == []


# ── Criterion 3: entity_lookup with a hand-built cache ───────────────────────────
def _mapping(question: str) -> CandidateMapping:
    el = SchemaElement(element_type="node_label", name="Person")
    return CandidateMapping(
        question=question,
        mentions={"who": [SchemaCandidate(element=el, score=1.0, beam_rank=1)]},
    )


def test_entity_lookup_one_match_posterior_one():
    cache = EntityCache([_person("PER-001", "Danny Kovac"), _person("PER-002", "Maria Lopez")])
    q = "What incidents involve Danny Kovac?"
    result = entity_lookup(q, _mapping(q), cache)
    assert isinstance(result, EntityLookupResult)
    assert "Danny Kovac" in result.entity_mentions
    cands = result.entity_mentions["Danny Kovac"]
    assert len(cands) == 1
    assert cands[0].posterior_score == pytest.approx(1.0)
    assert cands[0].node_id == "PER-001"


def test_entity_lookup_two_matches_and_no_match_omitted():
    cache = EntityCache([_person("PER-007", "James Whitfield"), _person("PER-013", "James Cole")])
    q = "Cases for James in Zzyzx"
    result = entity_lookup(q, _mapping(q), cache)
    assert len(result.entity_mentions["James"]) == 2
    assert sum(c.posterior_score for c in result.entity_mentions["James"]) == pytest.approx(1.0)
    # "Zzyzx" matches nothing ≥ threshold → absent
    assert "Zzyzx" not in result.entity_mentions


def test_entity_lookup_over_max_keeps_top_n_and_renormalises():
    nodes = [_person(f"PER-{i:03d}", "James Smith") for i in range(15)]
    cache = EntityCache(nodes)
    q = "records for James Smith please"
    result = entity_lookup(q, _mapping(q), cache, max_candidates_per_mention=10)
    cands = result.entity_mentions["James Smith"]
    assert len(cands) == 10
    assert sum(c.posterior_score for c in cands) == pytest.approx(1.0)


# ── Criterion 4: _candidate_labels always includes Person + Organisation ─────────
def test_candidate_labels_always_includes_person_and_org():
    rel = SchemaElement(
        element_type="relationship_type", name="LOCATED_AT",
        source_label="Incident", target_label="Location",
    )
    cm = CandidateMapping(
        question="q",
        mentions={"at": [SchemaCandidate(element=rel, score=1.0, beam_rank=1)]},
    )
    labels = _candidate_labels(cm)
    assert "Person" in labels
    assert "Organisation" in labels
    assert "Incident" in labels and "Location" in labels


def test_candidate_labels_includes_person_org_when_mapping_empty():
    cm = CandidateMapping(question="q", mentions={})
    assert set(_candidate_labels(cm)) == {"Person", "Organisation"}
