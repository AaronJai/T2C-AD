# experiments/sample_ozsoy_subset.py  --split sl --size 4000 --seed 13
"""CLI: deterministically sample a fixed-size subset of an Ozsoy SFT training split.

Stage 1 of 10.6 trains the generic Qwen adapters on a reduced-scale Ozsoy sample rather than
the full splits (15,262 SL / 32,339 QG rows), because Qwen2.5-32B trains at 14.9 s/step at
batch 1 on Kaya's v100-32gb nodes — the full SL split alone would be ~190 h, over the 72 h
per-job cap. 4,000 rows x 3 epochs is ~50 h, one job (10.5 fit-test + 10.6 spec).

The sample is `random.Random(seed).sample(rows, size)` over the jsonl rows in file order —
the same idiom `pipeline.pole_sft_data.build_mixed_training_file` uses for its Ozsoy replay
slice, and reproducible from the committed source splits with the same seed.

  python -m experiments.sample_ozsoy_subset            # both splits, 4000 rows, seed 13
  python -m experiments.sample_ozsoy_subset --split qg --size 2000
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Source -> destination per split. Kept here (not in a YAML) because the two paths are the
# 1.2-generated Ozsoy files and the 10.6 train YAMLs' `data.train_path`, nothing configurable.
_SPLITS: dict[str, tuple[str, str]] = {
    "sl": ("data/ozsoy_schema_linker_train.jsonl", "data/ozsoy_sl_train_{size}.jsonl"),
    "qg": ("data/ozsoy_qg_train.jsonl", "data/ozsoy_qg_train_{size}.jsonl"),
}


def sample_jsonl(src: str | Path, dest: str | Path, size: int, seed: int = 13) -> dict:
    """Write `size` rows sampled without replacement from the jsonl at `src` into `dest`.

    Deterministic for a given (src content, size, seed). Rows are copied verbatim, so the
    two-key {"prompt","completion"} train-format contract is preserved by construction.
    Returns a counts report. Raises ValueError if `src` holds fewer than `size` rows.
    """
    rows = [
        line for line in Path(src).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len(rows) < size:
        raise ValueError(f"{src} has {len(rows)} rows, fewer than the requested {size}")
    sample = random.Random(seed).sample(rows, size)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text("\n".join(sample) + "\n", encoding="utf-8")
    return {"source": str(src), "source_rows": len(rows), "output": str(dest),
            "sampled_rows": len(sample), "seed": seed}


def _size_tag(size: int) -> str:
    """4000 -> '4k' (the filename tag the 10.6 train YAMLs point at); other sizes verbatim."""
    return f"{size // 1000}k" if size >= 1000 and size % 1000 == 0 else str(size)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=[*_SPLITS, "both"], default="both")
    ap.add_argument("--size", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    splits = list(_SPLITS) if args.split == "both" else [args.split]
    for split in splits:
        src, dest_tmpl = _SPLITS[split]
        report = sample_jsonl(src, dest_tmpl.format(size=_size_tag(args.size)), args.size, args.seed)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
