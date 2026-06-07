"""Contract tests for 2.4 — Query Generator training entry point.

Covers the now-set (no-GPU) acceptance criteria:
  1. The entry point assembles a run_sft config whose output_dir is
     checkpoints/{model_key}/qg_adapter and whose target_modules comes from the registry.
  2. A {"prompt","completion"} QG row passes through build_model_inputs with labels masked
     over the prompt span and real ids over the Cypher completion.

The harness itself (build_model_inputs masking shapes, run_sft contract) is tested in 2.1
(tests/test_sft.py); 2.4 reuses it verbatim, so here we only verify the QG-specific wiring.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch
import yaml

from experiments.train_query_generator import build_run_config
from pipeline.query_generator.prompts import build_qg_prompt
from pipeline.sft import build_model_inputs

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS_YAML = _REPO_ROOT / "config" / "models.yaml"
_TRAIN_YAML = _REPO_ROOT / "config" / "query_generator_train.yaml"


class _CharTokenizer:
    """Minimal stand-in: one id per character, single-char eos so prompt is a clean prefix."""

    eos_token = "§"
    pad_token_id = 256
    eos_token_id = 257

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [ord(c) for c in text]


# ── Acceptance 1: entry point assembles a valid run_sft config from the YAMLs ──────
def test_build_run_config_for_known_key():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))

    config = build_run_config("mistral7b", registry, hp)

    assert config["model"]["base"] == registry["mistral7b"]["base"]
    # target_modules comes from the registry (architecture-specific), not the shared YAML.
    assert config["peft"]["target_modules"] == registry["mistral7b"]["target_modules"]
    assert "target_modules" not in hp["peft"]
    assert config["training"]["output_dir"] == "checkpoints/mistral7b/qg_adapter"
    # Shared hyperparameters carried through.
    assert config["peft"]["r"] == hp["peft"]["r"]
    assert config["training"]["max_seq_length"] == hp["training"]["max_seq_length"]
    # QG trains on the 1.3 jsonl, not the SL one.
    assert config["data"]["train_path"] == "data/ozsoy_qg_train.jsonl"
    assert config["data"]["eval_path"] == "data/ozsoy_qg_eval.jsonl"


def test_build_run_config_namespaces_second_base():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    config = build_run_config("llama31-8b", registry, hp)
    assert config["training"]["output_dir"] == "checkpoints/llama31-8b/qg_adapter"


def test_build_run_config_unknown_key_exits_with_known_keys():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit) as exc:
        build_run_config("does-not-exist", registry, hp)
    message = str(exc.value)
    assert "mistral7b" in message and "llama31-8b" in message


# ── Acceptance 2: a QG row masks the prompt and keeps the Cypher as the loss target ──
def test_qg_row_masks_prompt_keeps_cypher():
    tok = _CharTokenizer()
    # A realistic QG row: with-pattern prompt (Conditions 2&3) + a full Cypher completion.
    prompt = build_qg_prompt(
        question="Who is suspected of incident I1?",
        schema_block="(:Person)-[:SUSPECTED_OF]->(:Incident)",
        committed_pattern="(:Person)-[:SUSPECTED_OF]->(:Incident)",
    )
    completion = (
        " MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {id: 'I1'}) RETURN p.name"
    )

    out = build_model_inputs(prompt, completion, tok, max_seq_length=512)

    prompt_len = len(prompt)                                  # one id per char
    completion_ids = [ord(c) for c in completion + tok.eos_token]
    real_len = prompt_len + len(completion_ids)

    # Prompt span fully masked; the Cypher (incl. eos) carries the real token ids.
    assert out["labels"][:prompt_len].tolist() == [-100] * prompt_len
    assert out["labels"][prompt_len:real_len].tolist() == completion_ids
    # Sanity: the loss target is non-empty and the shapes match the window.
    assert any(label != -100 for label in out["labels"].tolist())
    for tensor in out.values():
        assert tensor.shape == (512,)
        assert tensor.dtype == torch.long
