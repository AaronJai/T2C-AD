"""Tests for the Schema Linker's backend-aware decoding strategy (API-model support).

Beam search is the default (local HF) strategy; an API backend gets its candidate
distribution from temperature sampling instead. No GPU/API: a FakeLLM records the
GenerationConfig it was handed and returns canned completions.
"""
from __future__ import annotations

from pipeline.llm import Completion, GenerationConfig
from pipeline.schema import build_pole_schema_repr
from pipeline.schema_linker.inference import sl_generation_config, sl_sampling_config
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import CandidateMapping


class _FakeLLM:
    """Returns `text` repeated num_return_sequences times; records the config seen."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.last_config: GenerationConfig | None = None

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        self.last_config = config
        n = config.num_return_sequences
        return [Completion(text=self.text, score=-1.0, rank=i + 1) for i in range(n)]


# ── sl_sampling_config shape ───────────────────────────────────────────────────────
def test_sl_sampling_config_is_sampling_not_beam():
    cfg = sl_sampling_config(num_samples=5, temperature=0.7, top_p=0.95)
    assert cfg.do_sample is True
    assert cfg.temperature == 0.7 and cfg.top_p == 0.95
    assert cfg.num_return_sequences == 5
    assert cfg.num_beams == 1 and cfg.num_beam_groups == 1   # no beam search


def test_sl_generation_config_still_beam():
    cfg = sl_generation_config(beam_k=5, diversity_penalty=0.2)
    assert cfg.do_sample is False
    assert cfg.num_beams == 5 and cfg.num_beam_groups == 5
    assert cfg.diversity_penalty == 0.2


# ── SchemaLinker decoding selection ────────────────────────────────────────────────
def test_default_decoding_is_beam():
    fake = _FakeLLM("(p:Person)")
    sl = SchemaLinker(fake, beam_k=5, diversity_penalty=0.2)
    assert sl._config.do_sample is False and sl._config.num_beam_groups == 5


def test_sample_decoding_builds_sampling_config():
    fake = _FakeLLM("(p:Person)")
    sl = SchemaLinker(fake, beam_k=4,
                      decoding={"strategy": "sample", "temperature": 0.5, "top_p": 0.9})
    assert sl._config.do_sample is True
    assert sl._config.temperature == 0.5 and sl._config.top_p == 0.9
    assert sl._config.num_return_sequences == 4               # beam_k = number of samples


def test_link_under_sampling_returns_candidate_mapping():
    schema = build_pole_schema_repr()
    fake = _FakeLLM("(p:Person)-[:SUSPECTED_OF]->(i:Incident)")
    sl = SchemaLinker(fake, beam_k=3, decoding={"strategy": "sample", "temperature": 0.7})
    mapping = sl.link("who is suspected?", schema)
    assert isinstance(mapping, CandidateMapping)
    assert mapping.beam_k == 3
    assert fake.last_config.do_sample is True                 # link used the sampling config
