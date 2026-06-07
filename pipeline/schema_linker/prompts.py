# pipeline/schema_linker/prompts.py
"""Schema Linker prompt. Shared by training (1.2) and inference (3.1) — do not fork it."""
from __future__ import annotations

SL_SYSTEM = (
    "Task: Identify the relevant schema elements for the given question.\n"
    "Use only node labels, relationship types, and properties from the provided schema.\n"
    "Output a Cypher graph pattern showing which schema elements answer the question.\n"
    "Do not write a full Cypher query. Do not include WHERE clauses or RETURN clauses.\n"
    "Do not include entity-specific property values."
)


def build_sl_prompt(question: str, schema_block: str) -> str:
    """Full SL prompt up to (but not including) the target pattern.

    schema_block: pre-rendered schema text.
      - training (1.2): the Ozsoy instance's schema string.
      - inference (3.1): build_pole_schema_repr().to_prompt_string(include_properties=True).
    """
    return (
        f"{SL_SYSTEM}\n\n"
        f"Schema:\n{schema_block}\n\n"
        f"Question: {question}\n"
        f"Schema pattern:"
    )
