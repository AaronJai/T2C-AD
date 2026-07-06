"""Tests for AnthropicLLM multi-sample support (the SL candidate-distribution path).

No API key / network: the Anthropic client is replaced with a fake recording calls.
"""
from __future__ import annotations

from pipeline.llm import GenerationConfig
from pipeline.llm.anthropic import AnthropicLLM


# ── Fake Anthropic client ──────────────────────────────────────────────────────────
class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _Messages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp(f"sample-{len(self.calls)}")


class _Client:
    def __init__(self) -> None:
        self.messages = _Messages()


def _llm() -> AnthropicLLM:
    """Construct without touching the real Anthropic() constructor."""
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm.model = "claude-sonnet-4-6"
    llm.client = _Client()
    return llm


# ── Single output (AD / Dis path) ──────────────────────────────────────────────────
def test_single_completion_one_call():
    llm = _llm()
    out = llm.generate("hello", GenerationConfig(num_return_sequences=1))
    assert len(out) == 1
    assert out[0].text == "sample-1" and out[0].score == -1.0 and out[0].rank == 1
    assert len(llm.client.messages.calls) == 1


# ── Multi-sample (SL candidate distribution) ───────────────────────────────────────
def test_multi_sample_issues_n_calls_uniform_scores():
    llm = _llm()
    cfg = GenerationConfig(do_sample=True, temperature=0.7, num_return_sequences=5)
    out = llm.generate("link this", cfg)
    assert len(out) == 5
    assert [c.text for c in out] == [f"sample-{i}" for i in range(1, 6)]
    assert all(c.score == -1.0 for c in out)             # uniform → frequency weighting
    assert [c.rank for c in out] == [1, 2, 3, 4, 5]
    # N independent calls, each at the requested temperature.
    calls = llm.client.messages.calls
    assert len(calls) == 5
    assert all(c["temperature"] == 0.7 for c in calls)


def test_generate_chat_splits_system_and_passes_messages():
    llm = _llm()
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "U"}]
    llm.generate_chat(msgs, GenerationConfig(num_return_sequences=1))
    call = llm.client.messages.calls[0]
    assert call["system"] == "SYS"
    assert call["messages"] == [{"role": "user", "content": "U"}]
