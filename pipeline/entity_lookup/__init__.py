# pipeline/entity_lookup/__init__.py
"""Entity Lookup: resolve NL entity mentions to real KG node instances (live Neo4j)."""
from __future__ import annotations

from pipeline.entity_lookup.cache import CachedNode, EntityCache
from pipeline.entity_lookup.lookup import entity_lookup
from pipeline.entity_lookup.matcher import compute_posterior_scores, fuzzy_match_score
from pipeline.entity_lookup.registry import (ENTITY_REGISTRY, ENTITY_REGISTRY_POLE_EXTERNAL,
                                             ENTITY_REGISTRY_V3, registry_for_version)
from pipeline.entity_lookup.span_extractor import extract_entity_spans

__all__ = [
    "CachedNode",
    "EntityCache",
    "ENTITY_REGISTRY",
    "ENTITY_REGISTRY_V3",
    "ENTITY_REGISTRY_POLE_EXTERNAL",
    "registry_for_version",
    "compute_posterior_scores",
    "entity_lookup",
    "extract_entity_spans",
    "fuzzy_match_score",
]
