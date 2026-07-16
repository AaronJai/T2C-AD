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


# ── API instruct-model variant (Phase 8 follow-up) ───────────────────────────────
# build_qg_prompt above is the *training-data* contract (1.3) and is NEVER forked. A capable
# instruct model, prompted with it, answers the question correctly but (a) invents plausible
# generic property names (`type`, `id`, `description`, ...) because this bare prompt never
# includes the schema's actual property list (`include_properties=False` at every call site —
# the local fine-tuned QG only knows the real names because Phase 7.4's POLE-specific SFT
# baked them into its weights) and (b) returns whole nodes/relationships (`RETURN p, r, i`)
# instead of the gold's tight single-column projection, because — unlike the SL/AD/Dis prompts
# — this is the one LLM-stage prompt with no worked example of the expected output shape.
# This is a SEPARATE, additive instruct-model prompt, mirroring the SL 8.1 pattern: the caller
# passes `include_properties=True` schema text and gets an explicit output contract + few-shots
# reused directly from the Phase 7.4 QG training data (`data/pole_qg_train.jsonl`), so both
# backends learn from the same curriculum. See decisions-log for the date this was added.
QG_SYSTEM_API = (
    "Task: Generate a Cypher query that answers the given question, using only the node "
    "labels, relationship types, and properties listed in the provided schema and the "
    "committed pattern.\n"
    "\n"
    "Output format (follow exactly):\n"
    "- Output ONLY the Cypher query: no markdown code fences, no explanation, no prose.\n"
    "- RETURN only the specific property values the question asks for (e.g. `RETURN p.name`). "
    "Never return whole nodes or relationships (never `RETURN p`, never `RETURN p, r, i`).\n"
    "- Use `RETURN DISTINCT` when the question could otherwise return duplicate rows.\n"
    "- Every property you reference, in MATCH/WHERE filters or in RETURN, MUST be spelled "
    "exactly as given in the schema's Properties list. Do not invent or guess a property name "
    "(e.g. `type`, `id`, `description`) that is not in that list.\n"
    "- Add a property filter only for a value the question actually mentions (a name, date, "
    "crime type, suburb, ...), matched to the correct property name from the schema."
)


# Four examples reused verbatim from the Phase 7.4 POLE QG training data (data/pole_qg_train.jsonl,
# rows 44, 51, 31, 46) so the API model is shown the same curriculum the fine-tuned local model
# learned from, not hand-authored new material. They cover: a single-hop property filter + tight
# projection; RETURN DISTINCT with a property filter (the shape closest to the Q-041 failure case
# documented in decisions-log); a temporal {active: true} filter inside a 2-hop chain; a 2-hop
# chain through a Case node.
_QG_FEW_SHOT_API = (
    "Examples:\n"
    "Question: What is the name of the officer investigating the robbery?\n"
    "Cypher: MATCH (i:Incident {crime_type:'robbery'})<-[:INVESTIGATES]-(p:Person) "
    "RETURN p.name\n"
    "\n"
    "Question: People associated with the drug offence in Fremantle.\n"
    "Cypher: MATCH (i:Incident {crime_type:'drug_offence'})<-[:SUSPECTED_OF]-(p:Person) "
    "RETURN DISTINCT p.name\n"
    "\n"
    "Question: What suburb is the location where the person currently associated with Anton "
    "Maric lives in?\n"
    "Cypher: MATCH (p:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-"
    "(p2:Person)-[:LIVES_AT]->(l:Location) RETURN l.suburb\n"
    "\n"
    "Question: What is the address of the place an incident that is part of Operation "
    "Cerberus took place?\n"
    "Cypher: MATCH (c:Case {case_name:'Operation Cerberus'})-[:CONTAINS]->(i:Incident)-"
    "[:OCCURRED_AT]->(l:Location) RETURN l.address\n"
)


def build_qg_prompt_api(
    question: str,
    schema_block: str,
    committed_pattern: Optional[str] = None,
    error_feedback: Optional[str] = None,
) -> str:
    """Instruct-model QG prompt: same schema/committed-pattern/question layout as
    ``build_qg_prompt``, with ``QG_SYSTEM_API`` (explicit output contract) and four Phase-7.4
    few-shot examples inserted before the live question. Used only when the backend is an
    instruct/API model (``prompt_style="instruct"``); the local fine-tuned path keeps
    ``build_qg_prompt`` untouched (train/inference match, 3.6).

    Caller contract: pass ``schema_block`` rendered with ``include_properties=True`` — the
    whole point of this variant is that the API model gets shown the properties list the local
    fine-tuned model never needs (7.4 SFT already baked it in).
    """
    feedback_block = (
        f"Previous attempt (rejected by the validator — do not repeat its mistakes):\n"
        f"{error_feedback}\n\n"
    ) if error_feedback else ""
    if committed_pattern:
        return (
            f"{QG_SYSTEM_API}\n\n"
            f"Schema:\n{schema_block}\n\n"
            f"{_QG_FEW_SHOT_API}\n"
            f"Committed pattern:\n{committed_pattern}\n\n"
            f"{feedback_block}"
            f"Question: {question}\n"
            f"Cypher:"
        )
    return (
        f"{QG_SYSTEM_API}\n\n"
        f"Schema:\n{schema_block}\n\n"
        f"{_QG_FEW_SHOT_API}\n"
        f"{feedback_block}"
        f"Question: {question}\n"
        f"Cypher:"
    )
