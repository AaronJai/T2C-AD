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

_REGISTRIES: dict[str, list[dict]] = {"v2": ENTITY_REGISTRY, "v3": ENTITY_REGISTRY_V3}


def registry_for_version(version: str = "v2") -> list[dict]:
    """The entity-searchable registry for a dataset version. 'v2' (default) → the frozen 3.2
    registry; 'v3' → the concise registry (no Organisation). Fails loudly on an unknown version.
    """
    try:
        return _REGISTRIES[version]
    except KeyError:
        raise ValueError(f"Unknown dataset_version '{version}'. Known: {list(_REGISTRIES)}")
