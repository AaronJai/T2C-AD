# pipeline/schema.py
"""Canonical SchemaRepr for the SyntheticPoliceKG (POLE) graph.

Two versions coexist (7.3): `build_pole_schema_repr` is the frozen v2 schema (9 labels /
28 relationship types) and `build_pole_v3_schema_repr` is the concise v3 schema (6 labels /
11 relationship types — see `data/SyntheticPoliceKG-v3.cypher` and spec 7.1). Both return a
`SchemaRepr` so every consumer is version-agnostic; `build_schema_repr(version)` selects.
"""
from __future__ import annotations

from pipeline.types import SchemaRepr


def build_pole_schema_repr() -> SchemaRepr:
    return SchemaRepr(
        node_labels=[
            "Person", "Incident", "Case", "Location",
            "Vehicle", "Phone", "Evidence", "Organisation", "Communication",
        ],
        relationship_paths=[
            {"type": "SUSPECTED_OF",    "source": "Person",        "target": "Incident"},
            {"type": "WITNESSED",       "source": "Person",        "target": "Incident"},
            {"type": "VICTIM_OF",       "source": "Person",        "target": "Incident"},
            {"type": "INVESTIGATES",    "source": "Person",        "target": "Incident"},
            {"type": "LIVES_AT",        "source": "Person",        "target": "Location"},
            {"type": "OWNS",            "source": "Person",        "target": "Vehicle"},
            {"type": "USES_PHONE",      "source": "Person",        "target": "Phone"},
            {"type": "WORKS_FOR",       "source": "Person",        "target": "Organisation"},
            {"type": "ASSOCIATED_WITH", "source": "Person",        "target": "Person"},
            {"type": "KNOWS",           "source": "Person",        "target": "Person"},
            {"type": "ASSIGNED_TO",     "source": "Person",        "target": "Case"},
            {"type": "COLLECTED",       "source": "Person",        "target": "Evidence"},
            {"type": "PARTICIPATED_IN", "source": "Person",        "target": "Communication"},
            {"type": "OCCURRED_AT",     "source": "Incident",      "target": "Location"},
            {"type": "CONTAINS",        "source": "Case",          "target": "Incident"},
            {"type": "HAS_EVIDENCE",    "source": "Case",          "target": "Evidence"},
            {"type": "RELATED_TO",      "source": "Evidence",      "target": "Incident"},
            {"type": "LINKED_TO",       "source": "Evidence",      "target": "Person"},
            {"type": "COLLECTED_AT",    "source": "Evidence",      "target": "Location"},
            {"type": "INVOLVED_IN",     "source": "Organisation",  "target": "Incident"},
            {"type": "SEEN_AT",         "source": "Vehicle",       "target": "Location"},
            {"type": "REGISTERED_AT",   "source": "Vehicle",       "target": "Location"},
            {"type": "USED_IN",         "source": "Vehicle",       "target": "Incident"},
            {"type": "CALLED",          "source": "Phone",         "target": "Phone"},
            {"type": "MESSAGED",        "source": "Phone",         "target": "Phone"},
            {"type": "LOCATED_AT",      "source": "Phone",         "target": "Location"},
            {"type": "RELATES_TO",      "source": "Communication", "target": "Case"},
            {"type": "TOOK_PLACE_AT",   "source": "Communication", "target": "Location"},
        ],
        properties={
            "Person":        ["person_id", "name", "alias", "role", "status",
                              "date_of_birth", "gender", "nationality"],
            "Incident":      ["incident_id", "crime_type", "description", "date",
                              "time", "status", "severity"],
            "Case":          ["case_id", "case_name", "opened_date", "closed_date",
                              "status", "priority"],
            "Location":      ["location_id", "address", "suburb", "city", "district",
                              "latitude", "longitude", "location_type"],
            "Vehicle":       ["vehicle_id", "license_plate", "make", "model",
                              "year", "colour", "vehicle_type"],
            "Phone":         ["device_id", "phone_number", "imei", "device_type",
                              "carrier"],
            "Evidence":      ["evidence_id", "type", "description",
                              "collected_date", "chain_of_custody"],
            "Organisation":  ["org_id", "name", "type", "status",
                              "established_date", "jurisdiction"],
            "Communication": ["comm_id", "type", "date", "time", "summary",
                              "classification"],
            # Temporal / labelled edge properties
            "LIVES_AT":      ["from_date", "to_date", "active"],
            "OWNS":          ["from_date", "to_date", "active"],
            "USES_PHONE":    ["active"],
            "WORKS_FOR":     ["active"],
            "ASSOCIATED_WITH": ["from_date", "to_date", "active", "association_type"],
            "LOCATED_AT":    ["date"],
            "SEEN_AT":       [],
        },
        format="nodes_and_paths",
    )


def build_pole_v3_schema_repr() -> SchemaRepr:
    """The concise v3 POLE schema: 6 node labels, 11 relationship types (spec 7.1).

    Built once from fixed definitions (not read from Neo4j), mirroring the v2 builder above so
    that 7.4's SFT prompts, 3.1/3.4/3.6/5.1 prompt-building, and the sweep/probe all render the
    same block. The only surviving complexity is *designed* ambiguity: the four Person->Incident
    role edges (schema), and the dated LIVES_AT/OWNS/USES_PHONE/ASSOCIATED_WITH edges (temporal).
    """
    return SchemaRepr(
        node_labels=[
            "Person", "Incident", "Case", "Location", "Vehicle", "Phone",
        ],
        relationship_paths=[
            {"type": "SUSPECTED_OF",    "source": "Person",   "target": "Incident"},
            {"type": "WITNESSED",       "source": "Person",   "target": "Incident"},
            {"type": "VICTIM_OF",       "source": "Person",   "target": "Incident"},
            {"type": "INVESTIGATES",    "source": "Person",   "target": "Incident"},
            {"type": "CONTAINS",        "source": "Case",     "target": "Incident"},
            {"type": "OCCURRED_AT",     "source": "Incident", "target": "Location"},
            {"type": "LIVES_AT",        "source": "Person",   "target": "Location"},
            {"type": "OWNS",            "source": "Person",   "target": "Vehicle"},
            {"type": "USES_PHONE",      "source": "Person",   "target": "Phone"},
            {"type": "CALLED",          "source": "Phone",    "target": "Phone"},
            {"type": "ASSOCIATED_WITH", "source": "Person",   "target": "Person"},
        ],
        properties={
            "Person":   ["person_id", "name", "alias", "date_of_birth", "gender"],
            "Incident": ["incident_id", "crime_type", "date", "status"],
            "Case":     ["case_id", "case_name", "descriptor", "status", "opened_date"],
            "Location": ["location_id", "address", "suburb", "postcode"],
            "Vehicle":  ["vehicle_id", "plate", "make", "model", "colour"],
            "Phone":    ["device_id", "phone_number"],
            # Temporal / labelled edge properties
            "LIVES_AT":        ["from_date", "to_date", "active"],
            "OWNS":            ["from_date", "to_date", "active"],
            "USES_PHONE":      ["from_date", "to_date", "active"],
            "ASSOCIATED_WITH": ["from_date", "to_date", "active"],
            "CALLED":          ["timestamp"],
        },
        format="nodes_and_paths",
    )


def build_pole_external_schema_repr() -> SchemaRepr:
    """The external `neo4j-graph-examples/pole` schema (9.1 audit): 11 node labels, 17
    relationship types. Real graph, not designed — no dated/state-change edge properties
    anywhere (`FAMILY_REL.rel_type` is the only relationship property); temporal ambiguity
    lives on node properties (`Crime.date`, `PhoneCall.call_date`/`call_time`) instead.

    `INVOLVED_IN`'s true source is `Vehicle` **or** `Object` (9.1: 978 Vehicle->Crime, 7
    Object->Crime) — `SchemaRepr.relationship_paths` carries one {type,source,target} triple
    per entry (the v2/v3 convention), so only the dominant Vehicle->Crime pattern is listed
    here, mirroring how v2's SEEN_AT/REGISTERED_AT already handle single-sourced entries.
    """
    return SchemaRepr(
        node_labels=[
            "Person", "Location", "Phone", "Email", "Officer", "PostCode",
            "Area", "PhoneCall", "Crime", "Object", "Vehicle",
        ],
        relationship_paths=[
            {"type": "CURRENT_ADDRESS",   "source": "Person",    "target": "Location"},
            {"type": "HAS_PHONE",         "source": "Person",    "target": "Phone"},
            {"type": "HAS_EMAIL",         "source": "Person",    "target": "Email"},
            {"type": "HAS_POSTCODE",      "source": "Location",  "target": "PostCode"},
            {"type": "POSTCODE_IN_AREA",  "source": "PostCode",  "target": "Area"},
            {"type": "LOCATION_IN_AREA",  "source": "Location",  "target": "Area"},
            {"type": "KNOWS_SN",          "source": "Person",    "target": "Person"},
            {"type": "KNOWS",             "source": "Person",    "target": "Person"},
            {"type": "CALLER",            "source": "PhoneCall", "target": "Phone"},
            {"type": "CALLED",            "source": "PhoneCall", "target": "Phone"},
            {"type": "KNOWS_PHONE",       "source": "Person",    "target": "Person"},
            {"type": "OCCURRED_AT",       "source": "Crime",     "target": "Location"},
            {"type": "INVESTIGATED_BY",   "source": "Crime",     "target": "Officer"},
            {"type": "INVOLVED_IN",       "source": "Vehicle",   "target": "Crime"},   # + Object->Crime (9.1)
            {"type": "PARTY_TO",          "source": "Person",    "target": "Crime"},
            {"type": "FAMILY_REL",        "source": "Person",    "target": "Person"},
            {"type": "KNOWS_LW",          "source": "Person",    "target": "Person"},
        ],
        properties={
            "Person":    ["nhs_no", "name", "surname"],
            "Location":  ["address", "postcode", "latitude", "longitude"],
            "Phone":     ["phoneNo"],
            "Email":     ["email_address"],
            "Officer":   ["badge_no", "name", "surname", "rank"],
            "PostCode":  ["code"],
            "Area":      ["areaCode"],
            "PhoneCall": ["call_date", "call_time", "call_type", "call_duration"],
            "Crime":     ["id", "date", "type", "last_outcome"],
            "Object":    ["id", "description", "type"],
            "Vehicle":   ["reg", "make", "model", "year"],
            "FAMILY_REL": ["rel_type"],   # the one relationship type carrying a property (9.1)
        },
        format="nodes_and_paths",
    )


def build_schema_repr(version: str = "v2") -> SchemaRepr:
    """Select the schema repr by dataset version. 'v2' (default) → frozen 9/28 POLE schema;
    'v3' → concise 6/11 schema; 'pole_external' → the real external 11/17 schema (9.3).
    Consumers keep receiving a `SchemaRepr` — no consumer change.
    """
    if version == "v3":
        return build_pole_v3_schema_repr()
    if version == "v2":
        return build_pole_schema_repr()
    if version == "pole_external":
        return build_pole_external_schema_repr()
    raise ValueError(f"Unknown dataset_version '{version}'. Known: 'v2', 'v3', 'pole_external'.")


def adapter_suffix_for_version(version: str = "v2") -> str:
    """The trained-adapter checkpoint suffix for a dataset version — the single source of truth
    that pairs a run's substrate with the adapters trained for it (7.4/7.5).

    'v2' (default) → '' → the frozen `checkpoints/{key}/{sl,qg}_adapter`; 'v3' → '_v3' → the
    POLE-refreshed `checkpoints/{key}/{sl,qg}_adapter_v3`; 'pole_external' → '_pole_external'
    (9.3) — a distinct suffix, not '', so a future locally-fine-tuned model pointed at this
    dataset version can't silently collide with v2's checkpoint path. The API model this step
    actually runs carries no adapter and never reads this value, so it is inert for this run.
    Keeps v2/v3 byte-identical.
    """
    if version == "v3":
        return "_v3"
    if version == "v2":
        return ""
    if version == "pole_external":
        return "_pole_external"
    raise ValueError(f"Unknown dataset_version '{version}'. Known: 'v2', 'v3', 'pole_external'.")
