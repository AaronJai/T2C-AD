# pipeline/entity_lookup/lookup.py
"""The Entity Lookup stage: question + candidate labels + cache → EntityLookupResult."""
from __future__ import annotations

import logging

from pipeline.entity_lookup.cache import EntityCache
from pipeline.entity_lookup.matcher import compute_posterior_scores
from pipeline.entity_lookup.span_extractor import extract_entity_spans
from pipeline.types import CandidateMapping, EntityCandidate, EntityLookupResult

logger = logging.getLogger(__name__)


def _candidate_labels(cm: CandidateMapping) -> list[str]:
    """Labels appearing in any beam candidate (node labels + relationship source/target),
    always including Person and Organisation (primary entity-ambiguity sources)."""
    labels: set[str] = {"Person", "Organisation"}
    for candidates in cm.mentions.values():
        for candidate in candidates:
            element = candidate.element
            if element.element_type == "node_label":
                labels.add(element.name)
            elif element.element_type == "relationship_type":
                if element.source_label:
                    labels.add(element.source_label)
                if element.target_label:
                    labels.add(element.target_label)
    return sorted(labels)


def entity_lookup(
    question: str, candidate_mapping: CandidateMapping, cache: EntityCache,
    fuzzy_threshold: float = 0.75, max_candidates_per_mention: int = 10,
) -> EntityLookupResult:
    """Spans → posterior-scored EntityCandidates, scoped to candidate_mapping labels.

    Per span: zero matches → omit. One match → posterior 1.0 (entity_entropy 0). Multiple →
    full distribution. >max_candidates_per_mention → keep top-N + log a warning (likely an
    over-generic span). Returns EntityLookupResult(question, entity_mentions).
    """
    labels = _candidate_labels(candidate_mapping)
    pool = cache.for_labels(labels)
    spans = extract_entity_spans(question)

    entity_mentions: dict[str, list[EntityCandidate]] = {}
    for span in spans:
        scored = compute_posterior_scores(span, pool, fuzzy_threshold)
        if not scored:
            continue  # zero matches → omit from entity_mentions (contributes 0 entropy)

        if len(scored) > max_candidates_per_mention:
            logger.warning(
                "Span %r matched %d candidates (> max_candidates_per_mention=%d); "
                "keeping top-%d — likely an over-generic span.",
                span, len(scored), max_candidates_per_mention, max_candidates_per_mention,
            )
            scored = scored[:max_candidates_per_mention]
            # Re-normalise the retained posteriors so EntityCandidate.posterior_score stays a
            # valid distribution (sum ~1.0) for the entity-entropy scorer (3.3).
            total = sum(posterior for _, _, posterior in scored)
            if total > 0:
                scored = [(node, ms, posterior / total) for node, ms, posterior in scored]

        entity_mentions[span] = [
            EntityCandidate(
                node_label=node.label,
                node_id=node.node_id,
                display_name=node.display_name,
                match_score=match_score,
                posterior_score=posterior,
            )
            for node, match_score, posterior in scored
        ]

    return EntityLookupResult(question=question, entity_mentions=entity_mentions)
