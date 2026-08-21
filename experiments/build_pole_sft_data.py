# experiments/build_pole_sft_data.py  --config config/pole_sft_data.yaml
"""CLI: generate the in-domain POLE SFT data.

With config/pole_sft_data.yaml (7.4) → the v3 schema; with
config/pole_sft_data_pole_external.yaml (10.2, `dataset_version: pole_external`) → the real
external POLE schema. Writes data/pole{,_ext}_{sl,qg}_{train,eval}.jsonl (the SL/QG two-key jsonl
contract), then the two Ozsoy-replay-mixed training files the matching continue-SFT train YAMLs
point at, plus a generation report (pattern coverage, paraphrase yield, disjointness drops) at
config["report_path"].
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from pipeline.pole_sft_data import (
    build_mixed_training_file,
    build_pole_external_sft_dataset,
    build_pole_sft_dataset,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/pole_sft_data.yaml")
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    # The external config carries `dataset_version: pole_external`; v3 omits it (default builder).
    if config.get("dataset_version") == "pole_external":
        report = build_pole_external_sft_dataset(config)
    else:
        report = build_pole_sft_dataset(config)
    print("POLE SFT data generation report:")
    print(json.dumps(report, indent=2))

    replay = config.get("ozsoy_replay")
    if replay:
        seed = config.get("seed", 13)
        sl_mix = build_mixed_training_file(
            config["output"]["sl_train"], replay["sl_source"], replay["sl_out"],
            replay["replay_size"], seed,
        )
        qg_mix = build_mixed_training_file(
            config["output"]["qg_train"], replay["qg_source"], replay["qg_out"],
            replay["replay_size"], seed,
        )
        print("Ozsoy-replay mix (SL):", sl_mix)
        print("Ozsoy-replay mix (QG):", qg_mix)


if __name__ == "__main__":
    main()
