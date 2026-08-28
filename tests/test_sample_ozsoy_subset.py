"""Contract tests for 10.6's Ozsoy 4k-sample prep step.

The Stage-1 Qwen generic adapters train on a fixed-size sample of the Ozsoy splits, so the
sample must be reproducible (same seed -> same rows) and must copy rows verbatim so the
{"prompt","completion"} train-format contract survives.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.sample_ozsoy_subset import _size_tag, sample_jsonl


def _write(path: Path, n: int) -> Path:
    rows = [{"prompt": f"p{i}", "completion": f"c{i}"} for i in range(n)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_sample_is_deterministic_and_size_exact(tmp_path):
    src = _write(tmp_path / "src.jsonl", 100)
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

    report = sample_jsonl(src, a, size=10, seed=13)
    sample_jsonl(src, b, size=10, seed=13)

    assert report == {"source": str(src), "source_rows": 100, "output": str(a),
                      "sampled_rows": 10, "seed": 13}
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
    assert len(a.read_text(encoding="utf-8").strip().splitlines()) == 10


def test_sample_rows_are_verbatim_source_rows_without_replacement(tmp_path):
    src = _write(tmp_path / "src.jsonl", 50)
    dest = tmp_path / "out.jsonl"
    sample_jsonl(src, dest, size=20, seed=13)

    source_lines = set(src.read_text(encoding="utf-8").strip().splitlines())
    lines = dest.read_text(encoding="utf-8").strip().splitlines()
    assert len(set(lines)) == 20                      # no repeats — sampled without replacement
    assert set(lines) <= source_lines                 # verbatim, so two-key rows stay two-key
    assert all(set(json.loads(line)) == {"prompt", "completion"} for line in lines)


def test_a_different_seed_gives_a_different_sample(tmp_path):
    src = _write(tmp_path / "src.jsonl", 100)
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    sample_jsonl(src, a, size=10, seed=13)
    sample_jsonl(src, b, size=10, seed=99)
    assert a.read_text(encoding="utf-8") != b.read_text(encoding="utf-8")


def test_sample_larger_than_source_raises(tmp_path):
    src = _write(tmp_path / "src.jsonl", 5)
    with pytest.raises(ValueError, match="fewer than"):
        sample_jsonl(src, tmp_path / "out.jsonl", size=10)


def test_size_tag_matches_the_yaml_filenames():
    assert _size_tag(4000) == "4k"     # data/ozsoy_{sl,qg}_train_4k.jsonl
    assert _size_tag(500) == "500"
