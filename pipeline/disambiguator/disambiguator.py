# pipeline/disambiguator/disambiguator.py
"""Disambiguator stage: commit one interpretation as a SchemaMapping for the Query Generator."""
from __future__ import annotations

import json
import logging
from typing import Iterator, Optional

from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT, build_disambiguator_prompt
from pipeline.llm import BaseLLM, GenerationConfig
from pipeline.schema import build_pole_schema_repr
from pipeline.schema_linker.postprocessing import parse_schema_pattern
from pipeline.types import (AmbiguityResult, CandidateMapping, EntityLookupResult,
                            ResolutionMode, SchemaElement, SchemaMapping, _build_cypher_pattern)

logger = logging.getLogger(__name__)


def disambiguator(
    question: str,
    ambiguity_result: AmbiguityResult,
    candidate_mapping: CandidateMapping,
    entity_lookup: EntityLookupResult,
    dis_llm: BaseLLM,
    previously_tried: list[SchemaMapping],
    mode: ResolutionMode = "automated",
    *,
    system_prompt: str = DIS_SYSTEM_PROMPT,
) -> Optional[SchemaMapping]:
    """Commit one interpretation. Returns None if all candidates have been tried.

    automated: prompt dis_llm, parse {committed_pattern, rationale}; null pattern → None.
    interactive: raise NotImplementedError — the interactive contract (pose a clarification
      question, await a reply) is implemented by the Gradio demo (6.2); the evaluation harness
      uses automated only.
    `system_prompt` selects the teaching prompt (defaults to the v2 `DIS_SYSTEM_PROMPT`; 7.3
    passes `DIS_SYSTEM_PROMPT_V3` for v3 runs — chosen in the condition builders, not here).
    """
    if mode == "interactive":
        raise NotImplementedError(
            "Interactive disambiguation is a documented extension; see the Gradio demo (6.2). "
            "The evaluation harness uses automated mode."
        )
    prompt = build_disambiguator_prompt(
        question, ambiguity_result, candidate_mapping, entity_lookup, previously_tried,
    )
    completions = dis_llm.generate_chat(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": prompt}],
        GenerationConfig(max_new_tokens=256, do_sample=False),
    )
    text = completions[0].text if completions else ""
    return _parse_disambiguator_output(
        text, question, candidate_mapping, previously_tried,
    )


def _parse_disambiguator_output(
    text: str,
    question: str,
    candidate_mapping: CandidateMapping,
    previously_tried: list[SchemaMapping],
) -> Optional[SchemaMapping]:
    """Extract JSON; if committed_pattern is null → None. Else build a SchemaMapping with
    cypher_syntax = committed_pattern (verbatim — the QG-facing string) and committed = a
    best-effort dict from _pattern_to_committed(). resolution_mode='automated'.

    Robustness:
      - Strip ``` fences / prose around the JSON.
      - If the returned pattern equals a previously_tried cypher_syntax, treat as a repeat:
        fall back to the highest-scoring candidate not in previously_tried; if none remain,
        return None.
      - On parse failure: deterministic fallback — pick the highest-scoring candidate pattern
        (built via _build_cypher_pattern over the top-1 element per slot) not previously tried;
        None if exhausted. Log a warning.
    """
    obj = _extract_json_object(text)
    if obj is None or "committed_pattern" not in obj:
        logger.warning(
            "Disambiguator LLM output unparseable; falling back to best untried candidate."
        )
        return _best_untried_candidate(question, candidate_mapping, previously_tried)

    pattern = obj.get("committed_pattern")
    if pattern is None:
        # The LLM signals every candidate interpretation has been exhausted.
        return None
    if not isinstance(pattern, str) or not pattern.strip():
        logger.warning(
            "Disambiguator emitted a non-string/empty committed_pattern; falling back."
        )
        return _best_untried_candidate(question, candidate_mapping, previously_tried)

    pattern = pattern.strip()
    tried = {sm.cypher_syntax for sm in previously_tried}
    if pattern in tried:
        logger.warning(
            "Disambiguator repeated a previously-tried pattern; falling back to next candidate."
        )
        return _best_untried_candidate(question, candidate_mapping, previously_tried)

    return SchemaMapping(
        question=question,
        committed=_pattern_to_committed(pattern, candidate_mapping),
        cypher_syntax=pattern,
        resolution_mode="automated",
    )


def _best_untried_candidate(
    question: str,
    candidate_mapping: CandidateMapping,
    previously_tried: list[SchemaMapping],
) -> Optional[SchemaMapping]:
    """Highest-scoring deterministic candidate mapping whose cypher_syntax is not previously
    tried; None if every candidate is exhausted."""
    tried = {sm.cypher_syntax for sm in previously_tried}
    for committed in _ranked_committed(candidate_mapping):
        syntax = _build_cypher_pattern(committed)
        if syntax and syntax not in tried:
            return SchemaMapping(
                question=question,
                committed=committed,
                cypher_syntax=syntax,
                resolution_mode="automated",
            )
    return None


def _ranked_committed(
    candidate_mapping: CandidateMapping,
) -> Iterator[dict[str, SchemaElement]]:
    """Yield committed mention→element dicts in descending score order.

    The argmax (top-1 element per slot) is yielded first; then each single-slot substitution
    of a lower-ranked candidate, ordered by that candidate's score. This walks the candidate
    distribution one varying slot at a time — the schema/temporal retry path the orchestrator
    drives via previously_tried.
    """
    if not candidate_mapping.mentions:
        return
    base = {slot: cands[0].element for slot, cands in candidate_mapping.mentions.items()}
    yield base
    subs: list[tuple[float, dict[str, SchemaElement]]] = []
    for slot, candidates in candidate_mapping.mentions.items():
        for cand in candidates[1:]:
            committed = dict(base)
            committed[slot] = cand.element
            subs.append((cand.score, committed))
    subs.sort(key=lambda t: t[0], reverse=True)
    for _score, committed in subs:
        yield committed


def _pattern_to_committed(pattern: str, candidate_mapping: CandidateMapping) -> dict:
    """Best-effort map a committed_pattern string back to {slot: SchemaElement}.

    Match the pattern's relationship types / labels against the SchemaElements already in
    candidate_mapping.mentions; for novel patterns the LLM may emit (e.g. untyped '[r]' for a
    'return all roles' reading), use parse_schema_pattern (3.1) and fall back to a partial/empty
    dict. `committed` is secondary metadata — cypher_syntax is authoritative for the QG.
    """
    parsed = parse_schema_pattern(pattern, build_pole_schema_repr(), 0.0)

    # Index the relationship SchemaElements already present in the candidate distribution.
    rel_index: dict[tuple, SchemaElement] = {}
    for candidates in candidate_mapping.mentions.values():
        for cand in candidates:
            el = cand.element
            if el.element_type == "relationship_type":
                rel_index[(el.name, el.source_label, el.target_label, el.parent)] = el

    alias_to_label = {alias: label for alias, label in parsed.nodes}
    committed: dict[str, SchemaElement] = {}
    referenced: set[str] = set()
    for i, (src, rtype, tgt, direction, props) in enumerate(parsed.relationships, 1):
        if rtype is None:
            # Untyped edge (e.g. the 'return all roles' reading) — no element to commit.
            continue
        left = alias_to_label.get(src)
        right = alias_to_label.get(tgt)
        if direction == "<-":
            source_label, target_label = right, left
        else:
            source_label, target_label = left, right
        parent = "active" if any(name.lower() == "active" for name in props) else None
        element = (
            rel_index.get((rtype, source_label, target_label, parent))
            or rel_index.get((rtype, source_label, target_label, None))
            or SchemaElement(
                element_type="relationship_type", name=rtype,
                source_label=source_label, target_label=target_label, parent=parent,
            )
        )
        committed[f"rel_{i}"] = element
        referenced.update(label for label in (source_label, target_label) if label)

    n = 1
    for _alias, label in parsed.nodes:
        if label and label not in referenced:
            committed[f"node_{n}"] = SchemaElement(element_type="node_label", name=label)
            n += 1
    return committed


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort: strip ``` fences / prose and parse the first balanced {...} object.

    Returns the parsed dict, or None if no parseable JSON object is found.
    """
    if not text:
        return None
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
                try:
                    obj = json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None
