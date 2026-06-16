"""Criterion-6 probe for step 3.7 (CyVer validation).

Builds the three real CyVer validators against the live SyntheticPoliceKG (POLE) graph
exactly as 5.1 will, wraps them in a minimal duck-typed `components`, and confirms
`cyver_validator` routes a set of crafted queries (valid / bad-syntax / bad-label /
bad-property) to the spec's `route_to` targets.

Run inside a job with Neo4j up on bolt://localhost:7687 (see kaya/57_cyver_probe.slurm).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import neo4j
from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

from pipeline.validation import cyver_validator


@dataclass
class _Components:
    """Minimal stand-in for 5.1 PipelineComponents (duck-typed by cyver_validator)."""
    syntax_validator: object
    schema_validator: object
    properties_validator: object
    database_name: str | None = None


# (query, label, expected route_to). Labels/relationships are POLE (see project-overview §5).
CASES = [
    ("valid / accept",
     "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name",
     "accept"),
    ("valid no-props / accept",
     "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p",
     "accept"),
    ("bad syntax / query_generator",
     "MATCH (p:Person RETURN p",
     "query_generator"),
    ("unknown label / schema_linker",
     "MATCH (p:Persn)-[:SUSPECTED_OF]->(i:Incident) RETURN p",
     "schema_linker"),
    ("unknown property / schema_linker",
     "MATCH (p:Person) WHERE p.naem = 'x' RETURN p",
     "schema_linker"),
]


def main() -> int:
    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    driver.verify_connectivity()

    components = _Components(
        syntax_validator=SyntaxValidator(driver, check_multilabeled_nodes=True),
        schema_validator=SchemaValidator(driver),
        properties_validator=PropertiesValidator(driver),
        database_name=None,
    )

    print(f"{'case':<34} {'expected':<16} {'got':<16} {'ok':<4} detail")
    print("-" * 100)
    all_ok = True
    for label, query, expected in CASES:
        result = cyver_validator(query, components)
        ok = result.route_to == expected
        all_ok &= ok
        detail = (f"syntax_valid={result.syntax_valid} schema={result.schema_score} "
                  f"props={result.properties_score} error_type={result.error_type}")
        print(f"{label:<34} {expected:<16} {result.route_to:<16} {'YES' if ok else 'NO':<4} {detail}")

    driver.close()
    print("-" * 100)
    print("ALL ROUTES CORRECT" if all_ok else "MISMATCH — see rows above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
