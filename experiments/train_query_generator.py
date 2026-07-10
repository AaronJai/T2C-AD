# experiments/train_query_generator.py  --model_key mistral7b
"""Query Generator LoRA training entry point.

Mirrors experiments/train_schema_linker.py (2.1) verbatim except it defaults to
config/query_generator_train.yaml and writes the adapter to checkpoints/{model_key}/qg_adapter.
The harness, masking, registry and --model_key mechanism are identical to 2.1 — the QG is
trained per base too (e.g. `python -m experiments.train_query_generator --model_key llama31-8b`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from pipeline.sft import run_sft


def build_run_config(model_key: str, registry: dict, hp: dict) -> dict:
    """Merge the per-model registry entry with the shared hyperparameters into a run_sft config.

    Sets the namespaced output dir checkpoints/{model_key}/{output_name} (output_name defaults
    to "qg_adapter"; the 7.4 continue-SFT YAML overrides it to "qg_adapter_v3" via
    hp["training"]["output_name"]). If hp["model"]["init_adapter_path_name"] is set (7.4), the
    run continues from checkpoints/{model_key}/{that name} instead of a fresh LoRA init — see
    pipeline.sft.run_sft's init_adapter_path hook. Both are additive/optional: an hp dict
    without them (2.4's config/query_generator_train.yaml) produces byte-identical output to
    before. Raises SystemExit with the list of known keys if model_key is not in the registry.
    """
    if model_key not in registry:
        raise SystemExit(f"Unknown model_key '{model_key}'. Known: {list(registry)}")
    m = registry[model_key]
    output_name = hp["training"].get("output_name", "qg_adapter")
    training_cfg = {k: v for k, v in hp["training"].items() if k != "output_name"}
    training_cfg["output_dir"] = f"checkpoints/{model_key}/{output_name}"

    model_cfg = {"base": m["base"], "dtype": m["dtype"], "load_in_4bit": m.get("load_in_4bit", False)}
    init_adapter_name = hp.get("model", {}).get("init_adapter_path_name")
    if init_adapter_name:
        model_cfg["init_adapter_path"] = f"checkpoints/{model_key}/{init_adapter_name}"

    return {
        "model": model_cfg,
        "peft":  {**hp["peft"], "target_modules": m["target_modules"]},
        "training": training_cfg,
        "data":  hp["data"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", required=True)
    ap.add_argument("--models", default="config/models.yaml")
    ap.add_argument("--train", default="config/query_generator_train.yaml")
    args = ap.parse_args()

    registry = yaml.safe_load(Path(args.models).read_text())
    hp = yaml.safe_load(Path(args.train).read_text())

    config = build_run_config(args.model_key, registry, hp)
    run_sft(config)


if __name__ == "__main__":
    main()
