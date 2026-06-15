"""Contract tests for the Bayesian entropy sub-scorer (step 3.3)."""
from __future__ import annotations

import math

from pipeline.ambiguity import compute_ambiguity_scores
from pipeline.ambiguity.bayesian_scorer import _shannon_entropy_normalised
from pipeline.types import (
    CandidateMapping,
    EntityCandidate,
    EntityLookupResult,
    SchemaCandidate,
    SchemaElement,
)


def _rel_candidate(name: str, score: float, beam_rank: int) -> SchemaCandidate:
    return SchemaCandidate(
        element=SchemaElement(element_type="relationship_type", name=name),
        score=score,
        beam_rank=beam_rank,
    )


def _node_candidate(name: str, score: float, beam_rank: int) -> SchemaCandidate:
    return SchemaCandidate(
        element=SchemaElement(element_type="node_label", name=name),
        score=score,
        beam_rank=beam_rank,
    )


def _entity_candidate(node_id: str, posterior: float) -> EntityCandidate:
    return EntityCandidate(
        node_label="Person",
        node_id=node_id,
        display_name=node_id,
        match_score=posterior,
        posterior_score=posterior,
    )


# ── Acceptance criterion 1: _shannon_entropy_normalised ────────────────────────
def test_uniform_four_way_is_one():
    assert math.isclose(_shannon_entropy_normalised([0.25, 0.25, 0.25, 0.25]), 1.0)


def test_single_candidate_is_zero():
    assert _shannon_entropy_normalised([1.0]) == 0.0


def test_peaked_distribution_is_small():
    assert _shannon_entropy_normalised([0.97, 0.02, 0.01]) < 0.2


def test_two_way_even_is_one():
    assert math.isclose(_shannon_entropy_normalised([0.5, 0.5]), 1.0)


def test_unnormalised_scores_are_renormalised():
    # Same shape as [0.5, 0.5] but summing to 4 → still H_norm ≈ 1.0.
    assert math.isclose(_shannon_entropy_normalised([2.0, 2.0]), 1.0)


def test_empty_and_zero_total_return_zero():
    assert _shannon_entropy_normalised([]) == 0.0
    assert _shannon_entropy_normalised([0.0, 0.0]) == 0.0


# ── Acceptance criterion 2: full scorer, high schema + high entity ─────────────
def test_high_schema_and_entity_entropy():
    mapping = CandidateMapping(
        question="who is connected to the incident",
        mentions={
            "connected to": [
                _rel_candidate("SUSPECTED_OF", 0.25, 1),
                _rel_candidate("WITNESSED", 0.25, 2),
                _rel_candidate("VICTIM_OF", 0.25, 3),
                _rel_candidate("INVESTIGATES", 0.25, 4),
            ]
        },
    )
    lookup = EntityLookupResult(
        question="who is connected to the incident",
        entity_mentions={
            "James": [_entity_candidate("PER-007", 0.5), _entity_candidate("PER-013", 0.5)]
        },
    )
    schema_entropy, entity_entropy = compute_ambiguity_scores(mapping, lookup)
    assert math.isclose(schema_entropy, 1.0)
    assert math.isclose(entity_entropy, 1.0)


# ── Acceptance criterion 3: empty mappings → (0.0, 0.0) ────────────────────────
def test_empty_mappings_return_zeros():
    mapping = CandidateMapping(question="q", mentions={})
    lookup = EntityLookupResult(question="q", entity_mentions={})
    assert compute_ambiguity_scores(mapping, lookup) == (0.0, 0.0)


# ── Acceptance criterion 4: node-label-only slot contributes nothing ───────────
def test_node_label_only_slot_does_not_count():
    mapping = CandidateMapping(
        question="q",
        mentions={
            "the person": [
                _node_candidate("Person", 0.6, 1),
                _node_candidate("Organisation", 0.4, 2),
            ]
        },
    )
    lookup = EntityLookupResult(question="q", entity_mentions={})
    schema_entropy, entity_entropy = compute_ambiguity_scores(mapping, lookup)
    assert schema_entropy == 0.0
    assert entity_entropy == 0.0


# ── Worked examples: max across slots / single entity candidate → 0 ────────────
def test_schema_entropy_takes_max_across_slots():
    mapping = CandidateMapping(
        question="q",
        mentions={
            "low": [
                _rel_candidate("SUSPECTED_OF", 0.97, 1),
                _rel_candidate("WITNESSED", 0.02, 2),
                _rel_candidate("VICTIM_OF", 0.01, 3),
            ],
            "high": [
                _rel_candidate("OWNS", 0.5, 1),
                _rel_candidate("USES_PHONE", 0.5, 2),
            ],
        },
    )
    lookup = EntityLookupResult(question="q", entity_mentions={})
    schema_entropy, _ = compute_ambiguity_scores(mapping, lookup)
    assert math.isclose(schema_entropy, 1.0)


def test_single_entity_candidate_is_zero_entropy():
    mapping = CandidateMapping(question="q", mentions={})
    lookup = EntityLookupResult(
        question="q",
        entity_mentions={"Danny Kovac": [_entity_candidate("PER-001", 1.0)]},
    )
    _, entity_entropy = compute_ambiguity_scores(mapping, lookup)
    assert entity_entropy == 0.0


def test_temporal_two_way_slot_counts_as_schema():
    # rel_n_temporal: same rel type with/without {active:true} → 2-way schema slot.
    mapping = CandidateMapping(
        question="where does James live",
        mentions={
            "lives": [
                SchemaCandidate(
                    element=SchemaElement(
                        element_type="relationship_type", name="LIVES_AT", parent="active:true"
                    ),
                    score=0.5,
                    beam_rank=1,
                ),
                SchemaCandidate(
                    element=SchemaElement(element_type="relationship_type", name="LIVES_AT"),
                    score=0.5,
                    beam_rank=2,
                ),
            ]
        },
    )
    lookup = EntityLookupResult(question="q", entity_mentions={})
    schema_entropy, _ = compute_ambiguity_scores(mapping, lookup)
    assert math.isclose(schema_entropy, 1.0)
