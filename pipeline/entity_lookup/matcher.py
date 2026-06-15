# pipeline/entity_lookup/matcher.py
"""Fuzzy match a mention span against cached node names + Bayesian posterior over matches."""
from __future__ import annotations

from rapidfuzz import fuzz

from pipeline.entity_lookup.cache import CachedNode


def fuzzy_match_score(span: str, candidate_name: str) -> float:
    """token_set_ratio / 100 ∈ [0,1] — robust to word order and partial (first-name) matches."""
    return fuzz.token_set_ratio(span.lower(), candidate_name.lower()) / 100.0


def compute_posterior_scores(
    span: str, candidates: list[CachedNode], fuzzy_threshold: float = 0.75,
) -> list[tuple[CachedNode, float, float]]:
    """Posterior distribution over the cached nodes a span fuzzy-matches.

    Per candidate: match_score = max over its name_values. Keep those ≥ threshold.
    Uniform prior 1/n over the kept candidates; posterior ∝ prior × match_score, normalised
    to sum 1. Returns (node, match_score, posterior) ordered by posterior desc; empty if none
    clear the threshold.
    """
    kept: list[tuple[CachedNode, float]] = []
    for node in candidates:
        if not node.name_values:
            continue
        match_score = max(fuzzy_match_score(span, name) for name in node.name_values)
        if match_score >= fuzzy_threshold:
            kept.append((node, match_score))

    if not kept:
        return []

    prior = 1.0 / len(kept)
    weights = [(node, ms, prior * ms) for node, ms in kept]
    total = sum(w for _, _, w in weights)
    scored = [
        (node, ms, (w / total) if total > 0 else prior)
        for node, ms, w in weights
    ]
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored
