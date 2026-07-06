# pipeline/ambiguity/detector.py
"""Ambiguity Detector stage: LLM self-assessment (primary) + entropy evidence (secondary)."""
from __future__ import annotations

import json
import logging
from typing import Optional

from pipeline.ambiguity.bayesian_scorer import compute_ambiguity_scores
from pipeline.ambiguity.prompts import (AD_SYSTEM_PROMPT, build_ad_user_turn,
                                        _format_candidate_block, _format_entity_block)
from pipeline.llm import BaseLLM, GenerationConfig
from pipeline.types import AmbiguityResult, AmbiguityType, CandidateMapping, EntityLookupResult

logger = logging.getLogger(__name__)

_VALID_TYPES = {"schema", "entity", "intent", "temporal"}


def ambiguity_detector(
    question: str,
    candidate_mapping: CandidateMapping,
    entity_lookup: EntityLookupResult,
    ad_llm: BaseLLM,
    threshold_schema: float = 0.6,
    threshold_entity: float = 0.8,
    *,
    system_prompt: str = AD_SYSTEM_PROMPT,
) -> AmbiguityResult:
    """Classify a question as ambiguous (schema/entity/intent/temporal) via a few-shot LLM.

    The entropy scores (3.3) are injected into the prompt as evidence; the LLM makes the call.
    The thresholds only gate the deterministic fallback when the LLM output can't be parsed.
    `system_prompt` selects the teaching prompt (defaults to the v2 `AD_SYSTEM_PROMPT`; 7.3
    passes `AD_SYSTEM_PROMPT_V3` for v3 runs — chosen in the condition builders, not here).
    Never raises — always returns an AmbiguityResult.
    """
    schema_entropy, entity_entropy = compute_ambiguity_scores(candidate_mapping, entity_lookup)
    user = build_ad_user_turn(
        question, _format_candidate_block(candidate_mapping),
        _format_entity_block(entity_lookup), schema_entropy, entity_entropy,
    )
    completions = ad_llm.generate_chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user}],
        GenerationConfig(max_new_tokens=256, do_sample=False),
    )
    text = completions[0].text if completions else ""
    return _parse_ad_output(
        text, schema_entropy, entity_entropy, threshold_schema, threshold_entity,
    )


def _parse_ad_output(
    text: str,
    schema_entropy: float,
    entity_entropy: float,
    t_schema: float,
    t_entity: float,
) -> AmbiguityResult:
    """Extract the JSON object from the LLM text, validate it, build an AmbiguityResult.

    - detected_types filtered to _VALID_TYPES; if is_ambiguous is False, force [].
    - if is_ambiguous is True but detected_types empty, keep is_ambiguous True with [] (the
      Disambiguator handles type 'unknown').
    On parse failure (no/malformed JSON): FALLBACK to the deterministic rule —
    is_ambiguous = (schema_entropy >= t_schema or entity_entropy >= t_entity); detected_types
    inferred from whichever entropy cleared its threshold; rationale notes the fallback.
    """
    obj = _extract_json_object(text)
    if obj is None or "is_ambiguous" not in obj:
        return _fallback_result(schema_entropy, entity_entropy, t_schema, t_entity)

    is_ambiguous = bool(obj.get("is_ambiguous"))
    raw_types = obj.get("detected_types", [])
    if not isinstance(raw_types, list):
        raw_types = []
    detected_types: list[AmbiguityType] = [t for t in raw_types if t in _VALID_TYPES]
    if not is_ambiguous:
        detected_types = []
    rationale = obj.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = str(rationale)

    return AmbiguityResult(
        is_ambiguous=is_ambiguous,
        detected_types=detected_types,
        schema_entropy=schema_entropy,
        entity_entropy=entity_entropy,
        llm_rationale=rationale,
        threshold_schema=t_schema,
        threshold_entity=t_entity,
    )


def _fallback_result(
    schema_entropy: float,
    entity_entropy: float,
    t_schema: float,
    t_entity: float,
) -> AmbiguityResult:
    """Deterministic entropy-threshold fallback when the LLM output can't be parsed."""
    schema_hit = schema_entropy >= t_schema
    entity_hit = entity_entropy >= t_entity
    detected_types: list[AmbiguityType] = []
    if schema_hit:
        detected_types.append("schema")
    if entity_hit:
        detected_types.append("entity")
    is_ambiguous = schema_hit or entity_hit
    logger.warning(
        "AD LLM output unparseable; falling back to entropy thresholds "
        "(schema=%.2f>=%.2f? %s, entity=%.2f>=%.2f? %s) -> is_ambiguous=%s",
        schema_entropy, t_schema, schema_hit, entity_entropy, t_entity, entity_hit, is_ambiguous,
    )
    return AmbiguityResult(
        is_ambiguous=is_ambiguous,
        detected_types=detected_types,
        schema_entropy=schema_entropy,
        entity_entropy=entity_entropy,
        llm_rationale="FALLBACK: LLM output unparseable; decided by entropy thresholds.",
        threshold_schema=t_schema,
        threshold_entity=t_entity,
    )


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort: strip ``` fences/prose and parse the first balanced {...} object.

    Returns the parsed dict, or None if no parseable JSON object is found.
    """
    if not text:
        return None
    # Drop code fences (```json ... ``` or ``` ... ```); braces below do the real work.
    cleaned = text.replace("```json", "").replace("```", "")
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start:i + 1]
                try:
                    obj = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None
