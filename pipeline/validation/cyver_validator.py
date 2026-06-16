# pipeline/validation/cyver_validator.py
"""Deterministic CyVer 3-stage validation with typed upstream error routing (step 3.7)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pipeline.types import ValidationResult

if TYPE_CHECKING:                       # avoid a runtime import cycle with 5.1
    from pipeline.components import PipelineComponents


def cyver_validator(cypher: str, components: "PipelineComponents") -> ValidationResult:
    """Run Syntax → Schema → Properties against the live graph; return on first failure.

    Uses the pre-built validators and database_name held on `components` (duck-typed:
    components.syntax_validator / schema_validator / properties_validator / database_name).

    Routing CONTRACT (see pipeline.types.ValidationResult):
      - syntax invalid                         → error_type="syntax",     route_to="query_generator"
      - schema score < 1.0                      → error_type="schema",     route_to="schema_linker"
      - properties score not None and < 1.0     → error_type="properties", route_to="schema_linker"
      - properties score is None (no props)     → accept (NOT a failure)
      - all pass                                → error_type=None,         route_to="accept"

    Stages short-circuit: a syntactically invalid query is never schema/property-checked.
    `metadata` carries CyVer's structured diagnostic dicts for error analysis (4.2).
    """
    db = components.database_name

    syntax_valid, syntax_meta = components.syntax_validator.validate(cypher, db)
    if not syntax_valid:
        return ValidationResult(syntax_valid=False, schema_score=0.0, properties_score=None,
                                error_type="syntax", route_to="query_generator", metadata=syntax_meta)

    schema_score, schema_meta = components.schema_validator.validate(cypher, db)
    if schema_score < 1.0:
        return ValidationResult(syntax_valid=True, schema_score=schema_score, properties_score=None,
                                error_type="schema", route_to="schema_linker", metadata=schema_meta)

    props_score, props_meta = components.properties_validator.validate(cypher, db)
    if props_score is not None and props_score < 1.0:
        return ValidationResult(syntax_valid=True, schema_score=schema_score, properties_score=props_score,
                                error_type="properties", route_to="schema_linker", metadata=props_meta)

    return ValidationResult(syntax_valid=True, schema_score=schema_score, properties_score=props_score,
                            error_type=None, route_to="accept", metadata=[])
