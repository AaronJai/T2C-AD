# experiments/entropy_probe.py
"""Re-run the entropy probe on the POLE-SFT Schema Linker; report AUC + scoring-fn ablations.

Standalone validation checkpoint (NOT a build blocker). Reuses the shared 2.2 probe helpers
(`probe_utils`) and the `diversity_penalty` locked by the 2.2 sweep. For each benchmark item it
generates k=5 diverse beams once, caches them (`results/beams_pole.jsonl`), then scores three
ways and reports the entropy->ambiguity AUC of each against the ~0.62 general-model baseline.

The three scoring functions vary along two axes (entropy vs dominance; normalised candidates vs
raw beams) — the prior probe found this choice flat (<=0.01 delta), and 2.3 re-confirms it so 3.3
may use the simplest scorer (normalised entropy) without loss.

Outputs:
  - results/beams_pole.jsonl       (one record per item: question_id, is_ambiguous, beams)
  - results/entropy_probe_pole.json (AUC table + ablations + written finding)

Running the probe needs a GPU + the trained SL adapter (2.1) and the locked penalty (2.2). The
scoring functions themselves are pure and unit-tested offline (tests/test_entropy_probe.py).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

from experiments.probe_utils import (
    _normalise_pattern,
    generate_beams,
    normalised_entropy,
    roc_auc,
)
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.llm import BaseLLM, HuggingFaceLLM, build_llm
from pipeline.schema import adapter_suffix_for_version, build_schema_repr
from pipeline.types import BenchmarkItem

BEAM_K = 5
BASELINE_AUC = 0.62          # prior general-model headline (project-overview §7)
ABLATION_FLAT_DELTA = 0.01   # prior probe found the three scorers within this spread

# Prior (general llama3.1-8b-text2cypher) AUCs per signal — the figures 2.3 compares against.
PRIOR_AUC = {
    "h_norm_candidates": 0.622,
    "h_norm_beams": 0.624,
    "top_beam_dominance": 0.625,
}
HEADLINE_SIGNAL = "h_norm_candidates"


# ── Scoring functions (pure; each maps a beam list to an ambiguity score in [0,1]) ──────
# Higher score = more ambiguous (beams spread across distinct schema patterns), so each feeds
# `roc_auc(scores, is_ambiguous)` directly.

def h_norm_candidates(beams: list[str]) -> float:
    """H_norm over distinct *candidate* patterns (variable names normalised away).

    Beams that differ only in arbitrary variable names collapse to the same candidate, so this
    is entropy over distinct schema structures. The headline signal; compares to 0.622.
    """
    return normalised_entropy([_normalise_pattern(b) for b in beams])


def h_norm_beams(beams: list[str]) -> float:
    """H_norm over raw beam slots (no candidate canonicalisation) — the normalisation ablation."""
    return normalised_entropy(beams)


def top_beam_dominance(beams: list[str]) -> float:
    """1 - max candidate probability: low (->0) when one pattern dominates, high when spread.

    The dominance-vs-entropy ablation, computed over the same normalised candidate distribution
    as `h_norm_candidates`. Returns 0.0 for an empty beam list.
    """
    if not beams:
        return 0.0
    counts = Counter(_normalise_pattern(b) for b in beams)
    return 1.0 - max(counts.values()) / len(beams)


SCORERS = {
    "h_norm_candidates": h_norm_candidates,
    "h_norm_beams": h_norm_beams,
    "top_beam_dominance": top_beam_dominance,
}


# ── AUC table + written finding (pure) ──────────────────────────────────────────────────

def compute_auc_table(beams_per_item: list[list[str]], labels: list[bool]) -> list[dict]:
    """Per-signal AUC of the scoring function vs `is_ambiguous`, with the prior baseline."""
    rows = []
    for name, fn in SCORERS.items():
        scores = [fn(beams) for beams in beams_per_item]
        rows.append({
            "signal": name,
            "pole_sft_auc": roc_auc(scores, labels),
            "prior_general_auc": PRIOR_AUC[name],
        })
    return rows


def build_finding(rows: list[dict]) -> str:
    """One-paragraph written finding: headline vs 0.62 + whether the ablations stayed flat."""
    headline = next(r for r in rows if r["signal"] == HEADLINE_SIGNAL)
    aucs = [r["pole_sft_auc"] for r in rows]
    spread = max(aucs) - min(aucs)
    auc = headline["pole_sft_auc"]

    if auc > BASELINE_AUC + 1e-9:
        lead = (
            f"POLE-SFT entropy AUC ({auc:.3f}) improves over the ~{BASELINE_AUC} general-model "
            f"baseline: POLE-specific fine-tuning sharpens the schema-entropy->ambiguity signal, "
            f"so the Bayesian scorer (3.3) is a usable secondary input to the Ambiguity Detector."
        )
    else:
        lead = (
            f"POLE-SFT entropy AUC ({auc:.3f}) is flat/at the ~{BASELINE_AUC} general-model "
            f"baseline. This is still acceptable: the design treats the entropy signal as "
            f"secondary and the LLM self-assessment as primary — note it, do not change the "
            f"architecture."
        )

    if spread <= ABLATION_FLAT_DELTA:
        tail = (
            f" Ablations remain flat (spread {spread:.3f} <= {ABLATION_FLAT_DELTA}): the scoring "
            f"function is not the bottleneck (beam diversity is), so 3.3 may use the simplest "
            f"scorer (normalised entropy) without loss."
        )
    else:
        tail = (
            f" Ablations are NOT flat (spread {spread:.3f} > {ABLATION_FLAT_DELTA}): unlike the "
            f"prior probe, the scoring function matters here — record this in decisions-log.md."
        )
    return lead + tail


def write_results(rows: list[dict], decoding, finding: str, path: Path) -> None:
    """Write the AUC table, ablation summary, and finding to the results JSON.

    `decoding` is the locked SL decoding block; a bare `diversity_penalty` float is accepted
    for back-compat (coerced to a beam block). The flat `diversity_penalty` key is kept in the
    payload as a mirror (None for an API/sampling run)."""
    if isinstance(decoding, (int, float)):
        decoding = {"strategy": "beam", "diversity_penalty": float(decoding), "k": BEAM_K}
    path.parent.mkdir(parents=True, exist_ok=True)
    aucs = [r["pole_sft_auc"] for r in rows]
    spread = max(aucs) - min(aucs)
    headline = next(r for r in rows if r["signal"] == HEADLINE_SIGNAL)
    payload = {
        "beam_k": BEAM_K,
        "decoding": decoding,
        "diversity_penalty": decoding.get("diversity_penalty"),
        "baseline_auc": BASELINE_AUC,
        "headline_signal": HEADLINE_SIGNAL,
        "auc_table": rows,
        "ablation_spread": spread,
        "ablations_flat": spread <= ABLATION_FLAT_DELTA,
        "headline_improves_over_baseline": headline["pole_sft_auc"] > BASELINE_AUC + 1e-9,
        "finding": finding,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── Locked penalty + beam cache (I/O) ───────────────────────────────────────────────────

def read_diversity_penalty(path: str | Path) -> float:
    """Read the diversity_penalty locked by the 2.2 sweep; fail loudly if it is absent."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"{p} not found. The diversity_penalty is locked by the 2.2 sweep "
            f"(experiments/diversity_penalty_sweep.py writes it here). Run 2.2 first — "
            f"do not pick a default."
        )
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if "diversity_penalty" not in cfg:
        raise SystemExit(
            f"'diversity_penalty' absent from {p}. It is produced by the 2.2 sweep "
            f"(write_inference_config). Re-run 2.2 — do not pick a default."
        )
    return float(cfg["diversity_penalty"])


def read_sl_decoding(path: str | Path, model_key: str, kind: str = "local") -> dict:
    """Read the SL decoding block locked by the 2.2 sweep for `model_key`; fail loudly if absent.

    Prefers `decoding[<model_key>]` (the generalized per-model block); for a local model a legacy
    flat `diversity_penalty` is honoured as a beam block."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"{p} not found. The SL decoding is locked by the 2.2 sweep "
            f"(experiments/diversity_penalty_sweep.py writes it here). Run 2.2 first."
        )
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    dmap = cfg.get("decoding")
    if isinstance(dmap, dict) and model_key in dmap:
        return dict(dmap[model_key])
    if kind == "local" and "diversity_penalty" in cfg:
        return {"strategy": "beam", "diversity_penalty": float(cfg["diversity_penalty"]), "k": BEAM_K}
    raise SystemExit(
        f"No SL decoding for model '{model_key}' in {p}. It is produced by the 2.2 sweep "
        f"(write_inference_config). Re-run 2.2 for this model — do not pick a default."
    )


def generate_all_beams(llm: BaseLLM, items: list[BenchmarkItem], schema_block: str,
                       decoding: dict) -> list[dict]:
    """One k=5 generation pass over every item (records ready for caching), decoding as the live SL."""
    records = []
    for item in items:
        beams = generate_beams(llm, item.question, schema_block, decoding)
        records.append({
            "question_id": item.question_id,
            "is_ambiguous": item.is_ambiguous,
            "beams": beams,
        })
    return records


def cache_beams(records: list[dict], path: Path) -> None:
    """Write one JSON record per line to results/beams_pole.jsonl (so ablations rescore offline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def load_cached_beams(path: Path) -> list[dict]:
    """Load cached beam records; lets the three ablations rescore without re-generating."""
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--models", default="config/models.yaml")
    ap.add_argument("--benchmark", default="data/benchmark-updated.json")
    ap.add_argument("--dataset_version", default="v2", choices=["v2", "v3"],
                    help="Which schema repr to render for the SL prompt (v3 → concise schema).")
    ap.add_argument("--results_tag", default="",
                    help="Dataset tag suffixed into artefact names (e.g. v3); empty → today's names.")
    ap.add_argument("--inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--results", default=None,
                    help="default results/entropy_probe_{model_key}{_tag}.json")
    ap.add_argument("--beam_cache", default=None,
                    help="default results/beams_{model_key}{_tag}.jsonl (model+version-keyed so caches don't collide)")
    ap.add_argument("--regenerate", action="store_true",
                    help="Force beam regeneration even if the cache exists (needs GPU/API).")
    args = ap.parse_args()

    registry = yaml.safe_load(Path(args.models).read_text(encoding="utf-8"))
    if args.model_key not in registry:
        raise SystemExit(f"Unknown model_key '{args.model_key}'. Known: {list(registry)}")
    entry = registry[args.model_key]
    kind = entry.get("kind", "local")

    items = load_benchmark(args.benchmark)
    decoding = read_sl_decoding(args.inference_config, args.model_key, kind)
    tag = f"_{args.results_tag}" if args.results_tag else ""
    cache_path = Path(args.beam_cache or f"results/beams_{args.model_key}{tag}.jsonl")
    results_path = Path(args.results or f"results/entropy_probe_{args.model_key}{tag}.json")

    # Reuse cached beams when present (ablation rescore is GPU/API-free); else generate once.
    if cache_path.exists() and not args.regenerate:
        records = load_cached_beams(cache_path)
        print(f"Loaded {len(records)} cached beam records from {cache_path}.")
    else:
        schema = build_schema_repr(args.dataset_version)
        schema_block = schema.to_prompt_string(include_properties=True)
        if kind == "api":
            llm: BaseLLM = build_llm({"backend": entry["backend"], "model": entry["model"]})
        else:
            llm = HuggingFaceLLM(
                entry["base"],
                peft_adapter_path=f"checkpoints/{args.model_key}/sl_adapter"
                                  f"{adapter_suffix_for_version(args.dataset_version)}",
                load_in_4bit=entry.get("load_in_4bit", False),
                torch_dtype=entry["dtype"],
            )
        records = generate_all_beams(llm, items, schema_block, decoding)
        cache_beams(records, cache_path)
        print(f"Generated + cached {len(records)} beam records to {cache_path}.")

    labels = [bool(r["is_ambiguous"]) for r in records]
    beams_per_item = [r["beams"] for r in records]
    rows = compute_auc_table(beams_per_item, labels)
    finding = build_finding(rows)
    write_results(rows, decoding, finding, results_path)

    print(f"\ndecoding = {decoding}   (k={BEAM_K})")
    print(f"{'signal':>18} | {'POLE-SFT AUC':>12} | {'prior':>6}")
    for r in rows:
        print(f"{r['signal']:>18} | {r['pole_sft_auc']:>12.3f} | {r['prior_general_auc']:>6.3f}")
    print(f"\n{finding}")


if __name__ == "__main__":
    main()
