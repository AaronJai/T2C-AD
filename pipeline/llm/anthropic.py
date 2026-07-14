# pipeline/llm/anthropic.py
from __future__ import annotations

from typing import Optional

from anthropic import Anthropic

from pipeline.llm.base import BaseLLM, Completion, GenerationConfig


class AnthropicLLM(BaseLLM):
    """Anthropic API. No token logprobs: every Completion.score is the sentinel -1.0.

    Used for the single-output stages (Ambiguity Detector, Disambiguator) and — when the
    pipeline runs end-to-end on an API model — for the Schema Linker. The SL needs a
    *candidate distribution*, which this backend cannot get from beam search/logprobs;
    instead it samples ``num_return_sequences`` completions at ``temperature`` via that many
    independent calls (Anthropic's Messages API has no `n`). Because all scores are uniform
    (-1.0), the downstream aggregation (`build_candidate_mapping`) reduces to FREQUENCY
    weighting: a pattern sampled m times gets logsumexp(m × −1.0) = −1.0 + log m, so more
    frequent samples score higher — a coherent distribution.

    Decoding correctness (8.2). The default registry model is ``claude-sonnet-4-6`` (the
    ``claude-sonnet`` entry), chosen over Sonnet 5 because 4.6 still accepts a ``temperature``
    parameter. Two rules keep this backend faithful to the pipeline's decoding contract:

    - **Greedy stages send ``temperature=0.0``.** The QG/AD/Dis stages call with
      ``do_sample=False`` and rely on deterministic decoding (the retry/`error_feedback`
      design assumes it). ``do_sample=True`` (the SL sampling path) sends the configured
      ``config.temperature`` instead.
    - **``top_p`` is never sent.** Claude 4.x rejects ``temperature`` + ``top_p`` together with
      a 400; sampling diversity here is controlled by temperature alone. ``GenerationConfig.top_p``
      is simply ignored on this backend (OpenAI's backend keeps its own behaviour).

    The SDK's native exponential backoff handles 429/529/5xx (honouring ``retry-after``); the
    client is constructed with ``max_retries=5`` for a multi-hour unattended run.
    """

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: Optional[str] = None):
        self.model = model
        self.client = Anthropic(api_key=api_key, max_retries=5)

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return self.generate_chat([{"role": "user", "content": prompt}], config)

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        n = max(1, config.num_return_sequences)
        # Greedy stages (do_sample=False) decode deterministically → temperature 0.0; the SL
        # sampling path (do_sample=True) uses the configured temperature. `top_p` is never sent.
        temperature = config.temperature if config.do_sample else 0.0
        completions: list[Completion] = []
        for i in range(n):
            resp = self.client.messages.create(
                model=self.model, max_tokens=config.max_new_tokens,
                temperature=temperature,
                system=system or None, messages=convo or [{"role": "user", "content": ""}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            completions.append(Completion(text=text, score=-1.0, rank=i + 1))
        return completions
