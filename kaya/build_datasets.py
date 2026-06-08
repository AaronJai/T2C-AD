# kaya/build_datasets.py
"""Materialise the 1.2/1.3 SFT jsonl files and report token-length distributions.

This is the deferred data-prep that Phase-2 GPU training needs. It is CPU-only: CyVer/Neo4j
syntax filtering stays deferred (no driver configured -> _syntax_ok returns True), so only the
parse-fail / node-only filters run. Submit via kaya/00_build_data.slurm (work partition).

Outputs (repo-relative, read by the train scripts):
    data/ozsoy_schema_linker_train.jsonl  + _eval.jsonl   (1.2)
    data/ozsoy_qg_train.jsonl             + _eval.jsonl   (1.3)

Then it tokenises both train splits and prints the length percentiles so you can confirm /
raise max_seq_length in the two train YAMLs (currently 1024) if p99 exceeds it.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from datasets import load_dataset
from transformers import AutoTokenizer

from pipeline.query_generator.training_data import build_qg_dataset
from pipeline.schema_linker.training_data import build_sl_dataset
from pipeline.sft import measure_token_lengths

MODEL_KEY = "mistral7b"
DATASET = "neo4j/text2cypher-2025v1"


def main() -> None:
    base = yaml.safe_load(Path("config/models.yaml").read_text(encoding="utf-8"))[MODEL_KEY]["base"]

    # A HF Dataset is re-iterable, so the same handle feeds both builders (same seed=13 ->
    # consistent SL/QG train/eval partition, per the 1.3 spec).
    ds = load_dataset(DATASET, split="train")

    sl_report = build_sl_dataset(
        ds,
        "data/ozsoy_schema_linker_train.jsonl",
        "data/ozsoy_schema_linker_eval.jsonl",
    )
    qg_report = build_qg_dataset(
        ds,
        "data/ozsoy_qg_train.jsonl",
        "data/ozsoy_qg_eval.jsonl",
    )
    print("SL dataset report:", sl_report)
    print("QG dataset report:", qg_report)

    tok = AutoTokenizer.from_pretrained(base)
    for name, path in [
        ("SL", "data/ozsoy_schema_linker_train.jsonl"),
        ("QG", "data/ozsoy_qg_train.jsonl"),
    ]:
        print(f"{name} token lengths:", measure_token_lengths(path, tok))
    print("\nIf either p99 > 1024, raise max_seq_length in the matching train YAML before "
          "training (see decisions-log 2.1/2.4).")


if __name__ == "__main__":
    main()
