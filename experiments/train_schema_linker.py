# experiments/train_schema_linker.py  --model_key mistral7b
"""Schema Linker LoRA training entry point.

Loads config/models.yaml (the base registry) + config/schema_linker_train.yaml (shared
hyperparameters), assembles the flat run_sft config for the chosen --model_key, and writes
the adapter to checkpoints/{model_key}/sl_adapter. Training a second base is just a different
--model_key (e.g. `python -m experiments.train_schema_linker --model_key llama31-8b`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from pipeline.sft import run_sft


def build_run_config(model_key: str, registry: dict, hp: dict) -> dict:
    """Merge the per-model registry entry with the shared hyperparameters into a run_sft config.

    Sets the namespaced output dir checkpoints/{model_key}/sl_adapter. Raises SystemExit with
    the list of known keys if model_key is not in the registry.
    """
    if model_key not in registry:
        raise SystemExit(f"Unknown model_key '{model_key}'. Known: {list(registry)}")
    m = registry[model_key]
    return {
        "model": {"base": m["base"], "dtype": m["dtype"],
                  "load_in_4bit": m.get("load_in_4bit", False)},
        "peft":  {**hp["peft"], "target_modules": m["target_modules"]},
        "training": {**hp["training"], "output_dir": f"checkpoints/{model_key}/sl_adapter"},
        "data":  hp["data"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", required=True)
    ap.add_argument("--models", default="config/models.yaml")
    ap.add_argument("--train", default="config/schema_linker_train.yaml")
    args = ap.parse_args()

    registry = yaml.safe_load(Path(args.models).read_text())
    hp = yaml.safe_load(Path(args.train).read_text())

    config = build_run_config(args.model_key, registry, hp)
    run_sft(config)


if __name__ == "__main__":
    main()
