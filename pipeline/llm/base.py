# pipeline/llm/base.py
"""Model-agnostic LLM interface. Every pipeline LLM stage types against BaseLLM."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class GenerationConfig:
    """Unified generation parameters across all backends."""
    max_new_tokens: int = 256
    temperature: float = 1.0
    do_sample: bool = False          # False = beam/greedy; True = sampling
    num_beams: int = 1               # >1 enables beam search
    num_beam_groups: int = 1         # >1 enables diverse beam search
    diversity_penalty: float = 0.0   # used only when num_beam_groups > 1
    num_return_sequences: int = 1    # must be <= num_beams when beam searching
    top_p: float = 1.0
    repetition_penalty: float = 1.0


@dataclass
class Completion:
    """One generated completion with a comparable score.

    score is a log-probability sum (higher = more probable) for backends that expose it;
    a proxy for OpenAI; and the sentinel -1.0 for Anthropic (no logprobs).
    """
    text: str
    score: float
    rank: int                        # 1 = highest-scored completion


class BaseLLM(ABC):
    """Abstract LLM backend.

    generate()      — raw text completion (Schema Linker, Query Generator)
    generate_chat() — chat-formatted prompt (Ambiguity Detector, Disambiguator)

    Both must be implemented. A backend that cannot support a mode raises
    NotImplementedError for that mode. Both return num_return_sequences Completion
    objects ordered by score descending (rank=1 first).
    """

    @abstractmethod
    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]: ...

    @abstractmethod
    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]: ...
