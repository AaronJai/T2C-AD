"""Contract tests for pipeline.llm (spec 0.2 acceptance criteria — the 'now' set)."""
from __future__ import annotations

import pytest

from pipeline.llm import BaseLLM, Completion, GenerationConfig, build_llm
from pipeline.llm import anthropic as anthropic_mod
from pipeline.llm import huggingface as huggingface_mod
from pipeline.llm import openai as openai_mod


class FakeLLM(BaseLLM):
    """Minimal concrete backend: returns two completions out of score order."""

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        raw = [Completion(text="low", score=-2.0, rank=0),
               Completion(text="high", score=-0.5, rank=0)]
        ranked = sorted(raw, key=lambda c: c.score, reverse=True)
        for i, c in enumerate(ranked):
            c.rank = i + 1
        return ranked

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        return self.generate(messages[-1]["content"], config)


def test_clean_import() -> None:
    """Criterion 1: the public surface imports cleanly with no GPU/API."""
    assert BaseLLM is not None
    assert GenerationConfig().num_beams == 1
    assert Completion(text="x", score=0.0, rank=1).rank == 1
    assert callable(build_llm)


def test_basellm_is_abstract() -> None:
    """Criterion 2a: BaseLLM cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseLLM()  # type: ignore[abstract]


def test_fake_backend_ranks_descending() -> None:
    """Criterion 2b: a minimal concrete backend instantiates; outputs are rank=1 first."""
    llm = FakeLLM()
    out = llm.generate("anything", GenerationConfig())
    assert out[0].rank == 1
    assert out[0].text == "high"
    assert [c.rank for c in out] == [1, 2]
    scores = [c.score for c in out]
    assert scores == sorted(scores, reverse=True)


def test_build_llm_unknown_backend() -> None:
    """Criterion 3a: an unknown backend name raises ValueError."""
    with pytest.raises(ValueError):
        build_llm({"backend": "nope"})


def test_build_llm_dispatches_known_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Criterion 3b: build_llm routes each backend name to the right class.

    Constructors are monkeypatched so no model download / API client is needed.
    """
    seen: dict[str, dict] = {}

    def make_stub(name: str):
        def _stub(self, **kwargs):  # noqa: ANN001
            seen[name] = kwargs
        return _stub

    monkeypatch.setattr(huggingface_mod.HuggingFaceLLM, "__init__", make_stub("huggingface"))
    monkeypatch.setattr(openai_mod.OpenAILLM, "__init__", make_stub("openai"))
    monkeypatch.setattr(anthropic_mod.AnthropicLLM, "__init__", make_stub("anthropic"))

    hf = build_llm({"backend": "huggingface", "model_name_or_path": "x"})
    oa = build_llm({"backend": "openai", "model": "gpt-4o"})
    an = build_llm({"backend": "anthropic", "model": "claude-sonnet-4-6"})

    assert isinstance(hf, huggingface_mod.HuggingFaceLLM)
    assert isinstance(oa, openai_mod.OpenAILLM)
    assert isinstance(an, anthropic_mod.AnthropicLLM)
    assert seen["huggingface"] == {"model_name_or_path": "x"}
    assert seen["openai"] == {"model": "gpt-4o"}
    assert seen["anthropic"] == {"model": "claude-sonnet-4-6"}


def test_build_llm_does_not_mutate_spec() -> None:
    """build_llm pops 'backend' off a copy, never the caller's dict."""
    spec = {"backend": "nope", "model": "x"}
    with pytest.raises(ValueError):
        build_llm(spec)
    assert spec == {"backend": "nope", "model": "x"}
