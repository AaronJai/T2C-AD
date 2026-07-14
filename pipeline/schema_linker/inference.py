# pipeline/schema_linker/inference.py
"""Diverse-beam generation config and completion-text cleanup for the Schema Linker."""
from __future__ import annotations

import re

from pipeline.llm import GenerationConfig

# Markdown code-fence matcher — mirrors the QG `_FENCE_RE` (query_generator/generator.py):
# take the fenced content when an instruct model wraps its answer in ```...```.
_FENCE_RE = re.compile(r"```(?:cypher)?[ \t]*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def sl_generation_config(beam_k: int, diversity_penalty: float) -> GenerationConfig:
    """Fully-diverse beam search: one group per beam. The local (HuggingFace) strategy —
    yields k beams with comparable log-prob scores."""
    return GenerationConfig(
        max_new_tokens=128,
        do_sample=False,
        num_beams=beam_k,
        num_beam_groups=beam_k,
        diversity_penalty=diversity_penalty,
        num_return_sequences=beam_k,
    )


def sl_sampling_config(num_samples: int, temperature: float, top_p: float = 1.0) -> GenerationConfig:
    """Temperature sampling of ``num_samples`` completions: the API (OpenAI/Anthropic) strategy.

    Diverse beam search is a HuggingFace-only capability (beam groups + per-beam logprobs),
    so an API backend produces the SL candidate distribution by sampling instead. OpenAI maps
    ``num_return_sequences`` to its ``n`` and returns real summed-logprob scores; Anthropic
    issues that many independent calls with uniform (-1.0) scores → frequency weighting.
    Both feed the same `build_candidate_mapping`.
    """
    return GenerationConfig(
        max_new_tokens=128,
        do_sample=True,
        temperature=temperature,
        top_p=top_p,
        num_beams=1,
        num_beam_groups=1,
        diversity_penalty=0.0,
        num_return_sequences=num_samples,
    )


def _looks_like_pattern(line: str) -> bool:
    """A structural pattern line contains a parenthesised node group ``(`` … ``)``."""
    open_i = line.find("(")
    return open_i != -1 and line.find(")", open_i) != -1


def extract_pattern_from_completion(text: str) -> str:
    """Extract the bare Cypher graph pattern from an SL completion (0.2 already strips the
    prompt), tolerating instruct-model formatting drift while staying byte-identical to the
    fine-tuned model's tidy one-line output.

    1. If a markdown code fence is present, take its contents (mirrors the QG `_FENCE_RE`).
    2. Return the first line that structurally looks like a pattern — contains a parenthesised
       node group ``(`` … ``)`` — skipping prose/markdown lines.
    3. Fallback: the first non-empty stripped line, else the stripped text — so a bare-pattern
       completion (the local fine-tuned path) is byte-identical to the pre-8.1 behaviour.
    """
    fence = _FENCE_RE.search(text)
    body = fence.group(1) if fence else text

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and _looks_like_pattern(stripped):
            return stripped
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return body.strip()
