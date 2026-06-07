# pipeline/schema.py
"""Canonical SchemaRepr for the SyntheticPoliceKG (POLE) graph."""
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
