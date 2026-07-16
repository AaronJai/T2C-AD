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


def test_user_only_prompt_omits_system_not_null():
    """No system turn (SL / zero-shot-QG paths) → `system` is OMITTED, never sent as null.

    The live API rejects `"system": null` with a 400 ("system: Input should be a valid
    array") — caught at 8.3 G0.5. Regression guard for that fix.
    """
    llm = _llm()
    llm.generate("user-only", GenerationConfig(num_return_sequences=1))
    call = llm.client.messages.calls[0]
    assert "system" not in call


# ── 8.2 decoding correctness ─────────────────────────────────────────────────────────
def test_greedy_config_sends_temperature_zero():
    """do_sample=False (QG/AD/Dis) decodes deterministically → temperature 0.0, not config's 1.0."""
    llm = _llm()
    llm.generate("greedy", GenerationConfig(do_sample=False, temperature=1.0))
    assert llm.client.messages.calls[0]["temperature"] == 0.0


def test_sampling_config_sends_configured_temperature():
    """do_sample=True (the SL sampling path) sends the configured temperature."""
    llm = _llm()
    llm.generate("sample", GenerationConfig(do_sample=True, temperature=0.3,
                                            num_return_sequences=3))
    calls = llm.client.messages.calls
    assert len(calls) == 3 and all(c["temperature"] == 0.3 for c in calls)


def test_never_sends_top_p():
    """Claude 4.x rejects temperature+top_p together — top_p is never forwarded, even when set."""
    llm = _llm()
    cfg = GenerationConfig(do_sample=True, temperature=0.7, top_p=0.95,
                           num_return_sequences=4)
    llm.generate("no top_p", cfg)
    calls = llm.client.messages.calls
    assert len(calls) == 4
    assert all("top_p" not in c for c in calls)


def test_client_constructed_with_max_retries_5(monkeypatch):
    """The Anthropic client is built with max_retries=5 (SDK-native backoff for a long run)."""
    import pipeline.llm.anthropic as amod

    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(amod, "Anthropic", _FakeAnthropic)
    amod.AnthropicLLM(model="claude-sonnet-4-6", api_key="k")
    assert captured["max_retries"] == 5
    assert captured["api_key"] == "k"
