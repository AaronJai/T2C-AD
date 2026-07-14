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


# ── API instruct-model variant (8.1) ─────────────────────────────────────────────
# The completion prompt above (SL_SYSTEM / build_sl_prompt) is the *training-data*
# contract and is NEVER forked — a capable instruct model, prompted with it, answers the
# task correctly but in its own house style ((Person) without the label colon, extra
# {crime_type: ...} detail, prose/markdown wrapping), which the pattern parser was tuned
# against the fine-tuned Mistral's tidy one-line output and mis-scored (Cov@5 0.067). This
# is a SEPARATE, additive instruct-model prompt that states the output contract explicitly
# (a deliberate, documented exception to 1.2's "do not fork it" rule — see decisions-log
# 2026-07-14). The tolerant parser (3.1/8.1) still absorbs any residual drift.
SL_SYSTEM_API = (
    "Task: Identify the relevant schema elements for the given question.\n"
    "Use only node labels, relationship types, and properties from the provided schema.\n"
    "Output a Cypher graph pattern showing which schema elements answer the question.\n"
    "\n"
    "Output format (follow exactly):\n"
    "- Output EXACTLY ONE LINE: a bare Cypher graph pattern and nothing else.\n"
    "- Every node label carries a leading colon: write (:Person), never (Person).\n"
    "- Every relationship type is bracketed with a leading colon and an arrow: "
    "-[:SUSPECTED_OF]->.\n"
    "- The ONLY property filter you may add is {active: true}, and only on a temporal "
    "relationship (LIVES_AT, OWNS, USES_PHONE, ASSOCIATED_WITH) when the question asks "
    "about the current/present state. Add no other property filter.\n"
    "- Do not include entity-specific property values (no names, dates, ids, crime types).\n"
    "- Do not write a full query: no WHERE, no RETURN, no prose, no explanation, no "
    "markdown code fences.\n"
    "- Do not add extra hops the question does not ask for; use the shortest pattern that "
    "answers it."
)


# Three authored few-shots grounded in the v3 seed data (build_pole_v3_schema_repr, 7.1),
# mirroring the 3.4/3.5 few-shot style. They demonstrate the exact contract and target the
# reverted-attempt residuals: (1) a clean single-hop role edge — no over-chaining;
# (2) a temporal {active: true} variant — the dropped-active-filter residual; (3) a 2-hop
# chain — showing when chaining IS correct so the model neither over- nor under-chains.
_SL_FEW_SHOT_API = (
    "Examples:\n"
    "Question: Who is suspected of the Northbridge robbery?\n"
    "Schema pattern: (:Person)-[:SUSPECTED_OF]->(:Incident)\n"
    "\n"
    "Question: Where does James Whitfield currently live?\n"
    "Schema pattern: (:Person)-[:LIVES_AT {active: true}]->(:Location)\n"
    "\n"
    "Question: Which cases cover incidents that happened in Northbridge?\n"
    "Schema pattern: (:Case)-[:CONTAINS]->(:Incident)-[:OCCURRED_AT]->(:Location)\n"
)


def build_sl_prompt_api(question: str, schema_block: str) -> str:
    """Instruct-model SL prompt: same schema block + question layout as ``build_sl_prompt``,
    with ``SL_SYSTEM_API`` (explicit output contract) and 2–3 authored v3 few-shot examples
    inserted before the live question. Used only when the backend is an instruct/API model
    (``prompt_style="instruct"``); the local fine-tuned path keeps ``build_sl_prompt``.
    """
    return (
        f"{SL_SYSTEM_API}\n\n"
        f"Schema:\n{schema_block}\n\n"
        f"{_SL_FEW_SHOT_API}\n"
        f"Question: {question}\n"
        f"Schema pattern:"
    )
