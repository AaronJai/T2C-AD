"""Contract tests for the 8.2 backend-aware sweep decodings.

No GPU/network: only the pure `candidate_decodings` selection and the `write_inference_config`
serialisation are exercised (Claude 4.x rejects temperature+top_p, so an anthropic sweep carries
no top_p key; openai keeps it; the merged config block written for anthropic likewise omits it).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from experiments.diversity_penalty_sweep import (BEAM_K, TEMPERATURES, TOP_P,
                                                 candidate_decodings, write_inference_config)


def test_candidate_decodings_anthropic_omits_top_p():
    blocks = candidate_decodings("api", backend="anthropic")
    assert [b["temperature"] for b in blocks] == TEMPERATURES
    assert all(b["strategy"] == "sample" and b["k"] == BEAM_K for b in blocks)
    assert all("top_p" not in b for b in blocks)          # 400 guard: no temperature+top_p


def test_candidate_decodings_openai_keeps_top_p():
    blocks = candidate_decodings("api", backend="openai")
    assert all(b.get("top_p") == TOP_P for b in blocks)


def test_candidate_decodings_local_is_beam():
    blocks = candidate_decodings("local")
    assert all(b["strategy"] == "beam" and "diversity_penalty" in b for b in blocks)


def test_written_anthropic_block_carries_no_top_p(tmp_path):
    """The merged decoding[claude-sonnet] block the sweep writes carries no top_p key."""
    chosen = {"strategy": "sample", "temperature": 0.7, "k": BEAM_K}   # as anthropic sweep picks
    path = tmp_path / "sli.yaml"
    write_inference_config("claude-sonnet", chosen, path)
    loaded = yaml.safe_load(path.read_text())
    block = loaded["decoding"]["claude-sonnet"]
    assert block == chosen
    assert "top_p" not in block
    # A sampling block is not a beam block → no legacy flat diversity_penalty mirror is written.
    assert "diversity_penalty" not in loaded
