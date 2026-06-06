# pipeline/llm/openai.py
from __future__ import annotations

from typing import Optional

from openai import OpenAI

from pipeline.llm.base import BaseLLM, Completion, GenerationConfig


class OpenAILLM(BaseLLM):
    """OpenAI API. No beam search: uses n + temperature. score = sum token logprobs (proxy)."""

    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None, max_retries: int = 3):
        self.model = model
        self.client = OpenAI(api_key=api_key, max_retries=max_retries)

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return self.generate_chat([{"role": "user", "content": prompt}], config)

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        n = config.num_return_sequences
        temp = config.temperature if (config.do_sample or n > 1) else 0.0
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, n=n,
            max_tokens=config.max_new_tokens, temperature=temp,
            top_p=config.top_p, logprobs=True,
        )
        comps = []
        for choice in resp.choices:
            lps = choice.logprobs.content if choice.logprobs else []
            score = sum(t.logprob for t in lps) if lps else 0.0
            comps.append(Completion(text=choice.message.content or "", score=score, rank=0))
        comps.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(comps):
            c.rank = i + 1
        return comps
