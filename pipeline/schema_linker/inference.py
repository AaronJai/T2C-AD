# pipeline/schema_linker/inference.py
"""Diverse-beam generation config and completion-text cleanup for the Schema Linker."""
from __future__ import annotations

from pipeline.llm import GenerationConfig


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


def extract_pattern_from_completion(text: str) -> str:
    """The completion text is already the generated continuation (0.2 strips the prompt).
    Take the first non-empty line and strip — the model is trained to emit the pattern then stop.
    """
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return text.strip()
