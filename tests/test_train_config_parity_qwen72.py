"""11.3 acceptance 1 — the Qwen2.5-72B train YAMLs are the 10.6 32B recipe, proven mechanically.

Phase 11 adds a third scale point (7B -> 32B -> 72B) to a comparison whose validity rests on the
recipe being *identical* across columns: if any hyperparameter or data path drifted between the
32B and 72B runs, the measured difference would confound model scale with a training change.
The spec calls this "checkable, so check it mechanically rather than by eye" — that is this file.

The parity is total: `output_name`/`init_adapter_path_name` carry the SAME strings in both
families because the model key namespaces the output path (checkpoints/<model_key>/<name>), not
the YAML. So the two parsed documents must be equal outright — only the header comments differ.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

# (10.6 32B YAML, 11.3 72B YAML) for Stage 1 and both Stage-2 continues, SL and QG.
_PAIRS = [
    ("schema_linker_train_qwen_generic.yaml", "schema_linker_train_qwen72_generic.yaml"),
    ("schema_linker_train_qwen_v3.yaml", "schema_linker_train_qwen72_v3.yaml"),
    ("schema_linker_train_qwen_pole_external.yaml",
     "schema_linker_train_qwen72_pole_external.yaml"),
    ("query_generator_train_qwen_generic.yaml", "query_generator_train_qwen72_generic.yaml"),
    ("query_generator_train_qwen_v3.yaml", "query_generator_train_qwen72_v3.yaml"),
    ("query_generator_train_qwen_pole_external.yaml",
     "query_generator_train_qwen72_pole_external.yaml"),
]

# Every key the 11.3 spec names as load-bearing for the scale comparison.
_PEFT_KEYS = ["method", "r", "lora_alpha", "lora_dropout", "bias", "task_type"]
_TRAINING_KEYS = [
    "output_name", "num_train_epochs", "per_device_train_batch_size",
    "per_device_eval_batch_size", "gradient_accumulation_steps", "gradient_checkpointing",
    "learning_rate", "lr_scheduler_type", "warmup_ratio", "max_seq_length", "weight_decay",
    "bf16", "fp16", "logging_steps", "save_strategy", "evaluation_strategy",
]
_DATA_KEYS = ["train_path", "eval_path", "format"]


def _load(name: str) -> dict:
    return yaml.safe_load((_CONFIG_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("thirty_two_b,seventy_two_b", _PAIRS)
def test_named_keys_are_identical_to_the_10_6_counterpart(thirty_two_b, seventy_two_b):
    """Key-by-key diff over the spec's list — a readable failure naming the drifted key."""
    ref, new = _load(thirty_two_b), _load(seventy_two_b)
    for section, keys in (("peft", _PEFT_KEYS), ("training", _TRAINING_KEYS), ("data", _DATA_KEYS)):
        for key in keys:
            assert key in ref[section], f"{thirty_two_b}: missing {section}.{key}"
            assert new[section].get(key) == ref[section][key], (
                f"recipe drift at {section}.{key}: {seventy_two_b} has "
                f"{new[section].get(key)!r}, {thirty_two_b} has {ref[section][key]!r}"
            )
    # The continue-SFT link is part of the recipe: same section, same adapter name.
    assert new.get("model") == ref.get("model")


@pytest.mark.parametrize("thirty_two_b,seventy_two_b", _PAIRS)
def test_parsed_documents_are_equal_outright(thirty_two_b, seventy_two_b):
    """Stronger than the key list: nothing at all may differ, including keys added later."""
    assert _load(seventy_two_b) == _load(thirty_two_b)


@pytest.mark.parametrize("_ref,seventy_two_b", _PAIRS)
def test_72b_yamls_pin_the_locked_recipe_absolutely(_ref, seventy_two_b):
    """Belt-and-braces: the locked values stated as literals, so a *joint* edit still fails."""
    training = _load(seventy_two_b)["training"]
    # 11.2 (job 1144935) measured batch 2 fitting one H100 NVL at 88.3 GiB / 12.77 s per step.
    # Batch 1 is kept anyway — a parity CHOICE, not a hardware limit.
    assert training["per_device_train_batch_size"] == 1
    assert training["gradient_accumulation_steps"] == 32       # effective batch stays 32
    assert training["gradient_checkpointing"] is True
    assert training["fp16"] is True and training["bf16"] is False   # fp16 kept on sm90 (11.1)
    assert training["max_seq_length"] == 3584


@pytest.mark.parametrize("_ref,seventy_two_b", _PAIRS)
def test_continues_use_the_pole_only_splits_not_the_replay_mixes(_ref, seventy_two_b):
    """The `_mixed` Ozsoy-replay files are explicitly NOT the Stage-2 data (10.6 / 11.3)."""
    data = _load(seventy_two_b)["data"]
    assert "_mixed" not in data["train_path"]
    assert "_mixed" not in data["eval_path"]


@pytest.mark.parametrize("_ref,seventy_two_b", _PAIRS)
def test_yamls_assemble_72b_run_configs_with_the_expected_adapter_paths(_ref, seventy_two_b):
    """The six YAMLs + the registry build exactly the paths `_resolve_model_specs` expects."""
    from experiments.train_query_generator import build_run_config as build_qg
    from experiments.train_schema_linker import build_run_config as build_sl

    registry = yaml.safe_load((_CONFIG_DIR / "models.yaml").read_text(encoding="utf-8"))
    hp = _load(seventy_two_b)
    is_sl = seventy_two_b.startswith("schema_linker")
    config = (build_sl if is_sl else build_qg)("qwen2.5-72b", registry, hp)

    role = "sl" if is_sl else "qg"
    suffix = {"generic": "", "v3": "_v3", "pole_external": "_pole_external"}[
        seventy_two_b.removesuffix(".yaml").split("_qwen72_", 1)[1]
    ]
    assert config["training"]["output_dir"] == f"checkpoints/qwen2.5-72b/{role}_adapter{suffix}"
    assert config["model"]["base"] == registry["qwen2.5-72b"]["base"]
    assert config["model"]["load_in_4bit"] is True      # inherited lock (11.2 parity clause)
    assert config["peft"]["target_modules"] == registry["qwen2.5-72b"]["target_modules"]
    # Stage 1 inits a fresh LoRA; both continues start from the 72B generic — never the 32B one.
    if suffix:
        assert config["model"]["init_adapter_path"] == f"checkpoints/qwen2.5-72b/{role}_adapter"
    else:
        assert "init_adapter_path" not in config["model"]
