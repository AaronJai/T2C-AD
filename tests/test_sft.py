"""Contract tests for 2.1 — shared SFT harness + Schema Linker training entry point.

Covers the now-set (no-GPU) acceptance criteria: completion-only masking, run_sft
importability + documented config contract, and the entry-point config assembly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
import yaml

from experiments.train_schema_linker import build_run_config
from pipeline.sft import build_model_inputs, measure_token_lengths, run_sft

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS_YAML = _REPO_ROOT / "config" / "models.yaml"
_TRAIN_YAML = _REPO_ROOT / "config" / "schema_linker_train.yaml"


class _CharTokenizer:
    """Minimal stand-in: one id per character, single-char eos so prompt is a clean prefix."""

    eos_token = "§"      # '§' — one character, distinct from the PROMPT/COMPL letters
    pad_token_id = 256   # > any ASCII ord used here, and non-zero so it isn't skipped
    eos_token_id = 257

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [ord(c) for c in text]


# ── Acceptance 1: completion-only masking, correct shapes ─────────────────────────
def test_build_model_inputs_masking_and_shapes():
    tok = _CharTokenizer()
    out = build_model_inputs("PROMPT", "COMPL", tok, max_seq_length=32)

    assert set(out) == {"input_ids", "attention_mask", "labels"}
    for tensor in out.values():
        assert tensor.shape == (32,)
        assert tensor.dtype == torch.long

    prompt_len = len("PROMPT")                       # 6 (one id per char)
    completion_ids = [ord(c) for c in "COMPL" + tok.eos_token]
    real_len = prompt_len + len(completion_ids)      # 12

    # Prompt span masked with -100; completion (incl. eos) carries the real ids.
    assert out["labels"][:prompt_len].tolist() == [-100] * prompt_len
    assert out["labels"][prompt_len:real_len].tolist() == completion_ids
    # Padding masked in both labels and attention_mask.
    assert out["labels"][real_len:].tolist() == [-100] * (32 - real_len)
    assert out["attention_mask"].tolist() == [1] * real_len + [0] * (32 - real_len)
    # input_ids: real tokens then pad_id.
    assert out["input_ids"][:real_len].tolist() == [ord(c) for c in "PROMPT"] + completion_ids
    assert out["input_ids"][real_len:].tolist() == [tok.pad_token_id] * (32 - real_len)


def test_build_model_inputs_truncates_to_max_seq_length():
    tok = _CharTokenizer()
    out = build_model_inputs("PROMPT", "COMPLETION", tok, max_seq_length=8)
    for tensor in out.values():
        assert tensor.shape == (8,)
    # No padding when content already fills the window.
    assert out["attention_mask"].tolist() == [1] * 8


# ── Acceptance 2: run_sft importable with a documented config-key contract ────────
def test_run_sft_importable_and_documented():
    assert callable(run_sft)
    doc = run_sft.__doc__ or ""
    for key in ('config["model"]', 'config["peft"]', 'config["training"]', 'config["data"]'):
        assert key in doc


# ── Acceptance 3: entry point assembles a valid run_sft config from the YAMLs ──────
def test_build_run_config_for_known_key():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))

    config = build_run_config("mistral7b", registry, hp)

    assert config["model"]["base"] == registry["mistral7b"]["base"]
    # target_modules comes from the registry (architecture-specific), not the shared YAML.
    assert config["peft"]["target_modules"] == registry["mistral7b"]["target_modules"]
    assert "target_modules" not in hp["peft"]
    assert config["training"]["output_dir"] == "checkpoints/mistral7b/sl_adapter"
    # Shared hyperparameters carried through; max_seq_length is not the rejected 512.
    assert config["peft"]["r"] == hp["peft"]["r"]
    assert config["training"]["max_seq_length"] == hp["training"]["max_seq_length"] != 512
    assert config["data"] == hp["data"]


def test_build_run_config_namespaces_second_base():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    config = build_run_config("llama31-8b", registry, hp)
    assert config["training"]["output_dir"] == "checkpoints/llama31-8b/sl_adapter"


def test_build_run_config_unknown_key_exits_with_known_keys():
    registry = yaml.safe_load(_MODELS_YAML.read_text(encoding="utf-8"))
    hp = yaml.safe_load(_TRAIN_YAML.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit) as exc:
        build_run_config("does-not-exist", registry, hp)
    message = str(exc.value)
    assert "mistral7b" in message and "llama31-8b" in message


# ── max_seq_length sub-task helper (runs offline once the 1.2 jsonl exists) ────────
def test_measure_token_lengths(tmp_path):
    rows = [
        {"prompt": "ab", "completion": "c"},        # 2 + 1 + 1(eos) = 4
        {"prompt": "abcd", "completion": "ef"},      # 4 + 2 + 1     = 7
        {"prompt": "a", "completion": "bcdefg"},     # 1 + 6 + 1     = 8
    ]
    jsonl = tmp_path / "train.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    report = measure_token_lengths(jsonl, _CharTokenizer(), percentiles=(50, 99))
    assert report["count"] == 3
    assert report["max"] == 8
    assert report["p99"] == 8
