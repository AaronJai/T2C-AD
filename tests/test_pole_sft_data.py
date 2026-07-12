"""Contract tests for 7.4 POLE v3 SFT data generation (offline; no GPU/API key needed)."""
from __future__ import annotations

import json

import random

from pipeline.pole_sft_data import (
    _build_edges,
    _schema_ambiguous_pairs,
    _schema_ambiguous_rows,
    apply_disjointness_gate,
    build_pole_sft_dataset,
    enumerate_v3_patterns,
)
from pipeline.schema import build_pole_v3_schema_repr
from pipeline.schema_linker.pattern_extraction import extract_schema_pattern, has_relationship_type
from pipeline.schema_linker.postprocessing import parse_schema_pattern


# ── Acceptance 1: enumerate_v3_patterns ──────────────────────────────────────────
def test_every_pattern_is_in_schema():
    schema = build_pole_v3_schema_repr()
    patterns = enumerate_v3_patterns()
    assert patterns, "expected a non-empty pattern list"
    for pattern in patterns:
        parsed = parse_schema_pattern(pattern, schema, score=0.0)
        assert parsed.is_valid, f"pattern not schema-valid: {pattern}"


def test_every_pattern_has_a_relationship():
    for pattern in enumerate_v3_patterns():
        assert has_relationship_type(pattern)


def test_temporal_active_variants_present_for_every_temporal_type():
    patterns = enumerate_v3_patterns()
    for rel_type in ("LIVES_AT", "OWNS", "USES_PHONE", "ASSOCIATED_WITH"):
        assert any(f":{rel_type} {{active:true}}" in p for p in patterns), rel_type


def test_enumerate_v3_patterns_is_deterministic_and_exhaustive():
    first = enumerate_v3_patterns()
    second = enumerate_v3_patterns()
    assert first == second
    assert len(first) == len(set(first))
    # every one of the 11 v3 relationship types is exercised by at least one pattern
    schema = build_pole_v3_schema_repr()
    rel_types = {p["type"] for p in schema.relationship_paths}
    assert len(rel_types) == 11
    for rel_type in rel_types:
        assert any(f":{rel_type}" in p for p in patterns_containing(first, rel_type))


def patterns_containing(patterns: list[str], rel_type: str) -> list[str]:
    return [p for p in patterns if f":{rel_type}" in p]


# ── Two-key jsonl contract + SL/QG train==inference consistency ─────────────────
def test_build_pole_sft_dataset_two_key_contract(tmp_path):
    out = {
        "sl_train": str(tmp_path / "sl_train.jsonl"),
        "sl_eval": str(tmp_path / "sl_eval.jsonl"),
        "qg_train": str(tmp_path / "qg_train.jsonl"),
        "qg_eval": str(tmp_path / "qg_eval.jsonl"),
    }
    config = {
        "seed": 13,
        "entities_per_pattern": 1,
        "paraphrases_per_template": 0,   # no API key in this offline test
        "eval_fraction": 0.10,
        "max_rows": 60,
        "output": out,
    }
    report = build_pole_sft_dataset(config)
    assert report["paraphrase_used"] is False
    assert report["kept"] == 60

    for path in out.values():
        lines = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        assert lines, f"{path} is empty"
        for row in lines:
            assert set(row.keys()) == {"prompt", "completion"}
            assert isinstance(row["prompt"], str) and row["prompt"]
            assert isinstance(row["completion"], str) and row["completion"]

    # SL completion == extract_schema_pattern(QG completion) for every row (train==inference
    # format consistency, mirroring the 1.3 guard).
    sl_rows = [json.loads(line) for line in open(out["sl_train"], encoding="utf-8")]
    qg_rows = [json.loads(line) for line in open(out["qg_train"], encoding="utf-8")]
    assert len(sl_rows) == len(qg_rows)
    for sl_row, qg_row in zip(sl_rows, qg_rows):
        assert extract_schema_pattern(qg_row["completion"]) == sl_row["completion"]


# ── Schema-type ambiguity register (single-hop vague-connector rows) ─────────────
def test_schema_ambiguous_pairs_is_person_incident_only():
    edges = _build_edges(build_pole_v3_schema_repr())
    pairs = _schema_ambiguous_pairs(edges)
    assert set(pairs) == {("Person", "Incident")}
    assert {e.rel_type for e in pairs[("Person", "Incident")]} == {
        "SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES",
    }


def test_schema_ambiguous_rows_are_single_hop_and_cover_every_role_type():
    edges = _build_edges(build_pole_v3_schema_repr())
    rows = _schema_ambiguous_rows(edges, random.Random(13), samples_per_form=8)
    assert rows
    for row in rows:
        # single-hop only — exactly one relationship, never a `_chain_np` multi-hop chain
        assert row["pattern"].count("[") == 1
        assert extract_schema_pattern(row["cypher"]) == row["pattern"]
    # the vague register is paired with every Person→Incident role type across the corpus
    covered = {rt for row in rows for rt in row["rel_types"]}
    assert covered == {"SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES"}


def test_schema_connector_rows_reach_the_dataset(tmp_path):
    out = {k: str(tmp_path / f"{k}.jsonl") for k in ("sl_train", "sl_eval", "qg_train", "qg_eval")}
    report = build_pole_sft_dataset({
        "seed": 13, "entities_per_pattern": 1, "paraphrases_per_template": 0,
        "schema_connector_samples_per_form": 30, "output": out,
    })
    assert report["schema_connector_rows"] > 0


# ── Disjointness gate ─────────────────────────────────────────────────────────────
def test_disjointness_gate_drops_planted_near_duplicate():
    blocklist = ["Who is suspected of the homicide?"]
    candidates = [
        {"question": "Who is suspected of the homicide?", "pattern": "x", "cypher": "y", "rel_types": set()},
        {"question": "Who is suspected of the  homicide ?", "pattern": "x", "cypher": "y", "rel_types": set()},
        {"question": "What vehicle does James Whitfield own?", "pattern": "x", "cypher": "y", "rel_types": set()},
    ]
    kept, dropped = apply_disjointness_gate(candidates, blocklist, threshold=0.90)
    assert dropped == 2
    assert len(kept) == 1
    assert kept[0]["question"] == "What vehicle does James Whitfield own?"
