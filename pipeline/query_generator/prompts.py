# pipeline/query_generator/prompts.py
"""Query Generator prompt. Shared by training (1.3), inference (3.6), and the C1 builder (5.3)."""
from __future__ import annotations

from typing import Optional

SYSTEM_PROMPT_WITH_PATTERN = (
    "Task: Generate a Cypher query for the given question using the provided "
    "schema and committed pattern."
)
SYSTEM_PROMPT_ZERO_SHOT = (
    "Task: Generate a Cypher query for the given question using the provided schema."
)


def build_qg_prompt(
    question: str,
    schema_block: str,
    committed_pattern: Optional[str] = None,
    error_feedback: Optional[str] = None,
) -> str:
    """With committed_pattern → Conditions 2 & 3 format. Without → Condition 1 zero-shot.

    schema_block: pre-rendered schema text (a string), mirroring build_sl_prompt.
      - training (1.3): the dataset row's raw `schema` string.
      - inference (3.6) / Condition 1 (5.3): build_pole_schema_repr().to_prompt_string(
            include_properties=False).
    The zero-shot format matches the dataset's instruction format so Condition 1 is comparable
    to the published neo4j/text2cypher checkpoint results.

    error_feedback: INFERENCE-ONLY retry path. The orchestrator
    (5.2) composes it (failed query + CyVer diagnostics) on validation rejections; training rows
    NEVER set it, so prompts without it are byte-identical to the training format. Without this
    block, deterministic decoding would regenerate the identical invalid query on every retry.
    """
    feedback_block = (
        f"Previous attempt (rejected by the validator — do not repeat its mistakes):\n"
        f"{error_feedback}\n\n"
    ) if error_feedback else ""
    if committed_pattern:
        return (
            f"{SYSTEM_PROMPT_WITH_PATTERN}\n\n"
            f"Schema:\n{schema_block}\n\n"
            f"Committed pattern:\n{committed_pattern}\n\n"
            f"{feedback_block}"
            f"Question: {question}\n"
            f"Cypher:"
        )
    return (
        f"{SYSTEM_PROMPT_ZERO_SHOT}\n\n"
        f"Schema:\n{schema_block}\n\n"
        f"{feedback_block}"
        f"Question: {question}\n"
        f"Cypher:"
    )
