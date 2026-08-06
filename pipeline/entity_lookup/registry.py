# pipeline/entity_lookup/registry.py
"""Which node labels are entity-searchable, and the props to read for each."""
from __future__ import annotations

# Vehicle / Phone / Incident are excluded: they are referenced by exact identifiers
# (license plate, phone number, incident_id) that appear verbatim in questions and are
# captured by the Schema Linker's property filter — no fuzzy matching needed.
ENTITY_REGISTRY: list[dict] = [
    {"label": "Person",       "id_prop": "person_id",   "name_props": ["name", "alias"], "extra_props": ["role"]},
    {"label": "Organisation", "id_prop": "org_id",      "name_props": ["name"],          "extra_props": ["type", "status"]},
    {"label": "Case",         "id_prop": "case_id",     "name_props": ["case_name"],     "extra_props": ["status"]},
    {"label": "Location",     "id_prop": "location_id", "name_props": ["suburb", "address"], "extra_props": ["district"]},
]

# v3 registry (7.3): Organisation no longer exists in the schema; Person keeps name+alias
# (the entity-ambiguity source), Case and Location remain searchable. v3 Person has no `role`
# property and Location no `district`, so the extra_props are trimmed to what v3 actually stores.
ENTITY_REGISTRY_V3: list[dict] = [
    {"label": "Person",   "id_prop": "person_id",   "name_props": ["name", "alias"],     "extra_props": ["gender"]},
    {"label": "Case",     "id_prop": "case_id",     "name_props": ["case_name", "descriptor"], "extra_props": ["status"]},
    {"label": "Location", "id_prop": "location_id", "name_props": ["suburb", "address"], "extra_props": ["postcode"]},
]

# External POLE registry (9.3): Vehicle (reg plate), Phone/Email (exact strings), PostCode/Area
# (exact codes), Crime/PhoneCall/Object (not named entities) are excluded — same exclusion rule
# as v2/v3, applied to this real schema's audited labels (9.1). Location has no single identifier
# property in this schema (unlike v2/v3's location_id) — keyed by `address` instead (user-decided
# 2026-08-05, the spec's own documented fallback: zero changes to EntityCache.load's Cypher
# builder, which assumes a non-null id_prop).
ENTITY_REGISTRY_POLE_EXTERNAL: list[dict] = [
    {"label": "Person",   "id_prop": "nhs_no",    "name_props": ["name", "surname"], "extra_props": []},
    {"label": "Officer",  "id_prop": "badge_no",  "name_props": ["name", "surname"], "extra_props": ["rank"]},
    {"label": "Location", "id_prop": "address",   "name_props": ["address", "postcode"], "extra_props": []},
]

_REGISTRIES: dict[str, list[dict]] = {
    "v2": ENTITY_REGISTRY,
    "v3": ENTITY_REGISTRY_V3,
    "pole_external": ENTITY_REGISTRY_POLE_EXTERNAL,
}


def registry_for_version(version: str = "v2") -> list[dict]:
    """The entity-searchable registry for a dataset version. 'v2' (default) → the frozen 3.2
    registry; 'v3' → the concise registry (no Organisation); 'pole_external' → the real
    external-graph registry (9.3). Fails loudly on an unknown version.
    """
    try:
        return _REGISTRIES[version]
    except KeyError:
        raise ValueError(f"Unknown dataset_version '{version}'. Known: {list(_REGISTRIES)}")
