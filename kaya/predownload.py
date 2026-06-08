# kaya/predownload.py
"""Pre-fetch the HF dataset + base model on the LOGIN node (which has internet).

Kaya compute nodes have no outbound internet, so everything the GPU/CPU jobs read must be
cached first. Run this once on the login node, AFTER `huggingface-cli login` (the base model
is gated). It writes into $HF_HOME (point that at /group, never /home — see README).

    module load Anaconda3/2024.06
    conda activate /group/pmc084/$USER/envs/t2c
    export HF_HOME=/group/pmc084/$USER/hf_cache
    huggingface-cli login        # accept the Mistral-7B-v0.1 licence on its HF page first
    python kaya/predownload.py
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from datasets import load_dataset
from huggingface_hub import snapshot_download

MODEL_KEY = "mistral7b"
DATASET = "neo4j/text2cypher-2025v1"


def main() -> None:
    registry = yaml.safe_load(Path("config/models.yaml").read_text(encoding="utf-8"))
    base = registry[MODEL_KEY]["base"]

    print(f"HF_HOME = {os.environ.get('HF_HOME', '(unset!)')}")
    print(f"Downloading dataset: {DATASET} (train split) …")
    ds = load_dataset(DATASET, split="train")
    print(f"  cached {len(ds)} rows")

    print(f"Downloading base model snapshot: {base} …")
    snapshot_download(repo_id=base)
    print("Done. Compute-node jobs can now run with *_OFFLINE=1.")


if __name__ == "__main__":
    main()
