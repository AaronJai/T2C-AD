# pipeline/ambiguity/bayesian_scorer.py
"""Secondary ambiguity signal: normalised Shannon entropy over SL and entity distributions."""
from __future__ import annotations

import math

from pipeline.types import CandidateMapping, EntityLookupResult


def _shannon_entropy_normalised(scores: list[float]) -> float:
    """H_norm ∈ [0,1] over a (possibly un-normalised) score list. k≤1 → 0.0; total≤0 → 0.0."""
    k = len(scores)
    if k <= 1:
        return 0.0
    total = sum(scores)
    if total <= 0.0:
        return 0.0
    probs = [s / total for s in scores]
    h = 0.0
    for p in probs:
        if p > 0.0:
            h -= p * math.log2(p)
    return h / math.log2(k)


def compute_ambiguity_scores(
    candidate_mapping: CandidateMapping,
    entity_lookup: EntityLookupResult,
) -> tuple[float, float]:
    """Return (schema_entropy, entity_entropy), both ∈ [0,1].

    schema_entropy: for each mention slot whose candidates are relationship_type (this
      INCLUDES temporal variants — same rel type, with/without {active:true}), compute H_norm
      over the candidate scores; take the max across slots (0.0 if none).
    entity_entropy: for each entity mention with ≥2 candidates, compute H_norm over the
      posterior_scores; take the max across mentions (0.0 if none).
    """
    schema_hs: list[float] = []
    for candidates in candidate_mapping.mentions.values():
        rel = [c for c in candidates if c.element.element_type == "relationship_type"]
        if not rel:
            continue
        schema_hs.append(_shannon_entropy_normalised([c.score for c in rel]))
    schema_entropy = max(schema_hs) if schema_hs else 0.0

    entity_hs: list[float] = []
    for candidates in entity_lookup.entity_mentions.values():
        if len(candidates) < 2:
            continue
        entity_hs.append(_shannon_entropy_normalised([c.posterior_score for c in candidates]))
    entity_entropy = max(entity_hs) if entity_hs else 0.0

    return schema_entropy, entity_entropy
