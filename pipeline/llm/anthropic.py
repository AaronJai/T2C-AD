# pipeline/llm/anthropic.py
from __future__ import annotations

import warnings
from typing import Optional

from anthropic import Anthropic

from pipeline.llm.base import BaseLLM, Completion, GenerationConfig


class AnthropicLLM(BaseLLM):
    """Anthropic API. No token logprobs: Completion.score is the sentinel -1.0.

    Beam candidate distributions are UNDEFINED for this backend — use only for the
    Ambiguity Detector and Disambiguator (single few-shot output).
    """

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: Optional[str] = None):
        self.model = model
        self.client = Anthropic(api_key=api_key)

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return self.generate_chat([{"role": "user", "content": prompt}], config)

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        if config.num_return_sequences > 1:
            warnings.warn("AnthropicLLM ignores num_return_sequences>1; returning 1 completion.")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        resp = self.client.messages.create(
            model=self.model, max_tokens=config.max_new_tokens,
            temperature=config.temperature,
            system=system or None, messages=convo or [{"role": "user", "content": ""}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return [Completion(text=text, score=-1.0, rank=1)]
