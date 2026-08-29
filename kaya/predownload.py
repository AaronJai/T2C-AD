# kaya/predownload.py
"""Pre-fetch the HF dataset + base model on the LOGIN node (which has internet).

Kaya compute nodes have no outbound internet, so everything the GPU/CPU jobs read must be
cached first. Run this once on the login node, AFTER `huggingface-cli login` (the base model
is gated). It writes into $HF_HOME (point that at /group, never /home — see README).

    module load Anaconda3/2024.06
    conda activate /group/pmc084/$USER/envs/t2c
    export HF_HOME=/group/pmc084/$USER/hf_cache
    huggingface-cli login        # accept the Mistral-7B-v0.3 licence on its HF page first
    python kaya/predownload.py

`--model_key` (11.1) selects which `config/models.yaml` base to snapshot; it defaults to
`mistral7b`, so a bare `python kaya/predownload.py` is unchanged. The dataset + embedding-model
snapshots are unconditional. Re-running for an already-cached model re-verifies the snapshot
without re-downloading, so this is also the way to check a cache is complete:

    python kaya/predownload.py --model_key qwen2.5-32b
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml
from datasets import load_dataset
from huggingface_hub import snapshot_download

DEFAULT_MODEL_KEY = "mistral7b"
DATASET = "neo4j/text2cypher-2025v1"
# Semantic Evaluator (4.1) AREA cosine fallback when config/pipeline.yaml use_embedding_model: true.
# SentenceTransformer("all-MiniLM-L6-v2") resolves to this repo; cache it so the offline 5.4 run finds it.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model_key",
        default=DEFAULT_MODEL_KEY,
        help=f"config/models.yaml key whose `base` repo to snapshot (default: {DEFAULT_MODEL_KEY})",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    registry = yaml.safe_load(Path("config/models.yaml").read_text(encoding="utf-8"))
    if args.model_key not in registry:
        local = [k for k, v in registry.items() if (v or {}).get("kind") != "api"]
        raise SystemExit(
            f"--model_key '{args.model_key}' is not in config/models.yaml. "
            f"Local (downloadable) keys: {', '.join(sorted(local))}"
        )
    base = registry[args.model_key]["base"]

    print(f"HF_HOME = {os.environ.get('HF_HOME', '(unset!)')}")
    print(f"Downloading dataset: {DATASET} (train split) …")
    ds = load_dataset(DATASET, split="train")
    print(f"  cached {len(ds)} rows")

    print(f"Downloading base model snapshot: {base}  (model_key={args.model_key}) …")
    snapshot_download(repo_id=base)

    print(f"Downloading embedding model snapshot: {EMBEDDING_MODEL} …")
    snapshot_download(repo_id=EMBEDDING_MODEL)
    print("Done. Compute-node jobs can now run with *_OFFLINE=1.")


if __name__ == "__main__":
    main()
