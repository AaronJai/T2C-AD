# pipeline/schema_linker/inference.py
"""Diverse-beam generation config and completion-text cleanup for the Schema Linker."""
from __future__ import annotations

from pipeline.llm import GenerationConfig


def sl_generation_config(beam_k: int, diversity_penalty: float) -> GenerationConfig:
    """Fully-diverse beam search: one group per beam."""
    return GenerationConfig(
        max_new_tokens=128,
        do_sample=False,
        num_beams=beam_k,
        num_beam_groups=beam_k,
        diversity_penalty=diversity_penalty,
        num_return_sequences=beam_k,
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
