# experiments/probe_utils.py
"""Lightweight beam + entropy helpers for the diversity sweep (2.2) and probe re-run (2.3)."""
from __future__ import annotations

import math
import re
from collections import Counter

from pipeline.llm import BaseLLM
from pipeline.schema_linker.inference import sl_generation_config, sl_sampling_config
from pipeline.schema_linker.pattern_extraction import extract_schema_pattern
from pipeline.schema_linker.prompts import build_sl_prompt
from pipeline.types import BenchmarkItem


def generate_beams(llm: BaseLLM, question: str, schema_block: str, decoding: dict) -> list[str]:
    """k SL completion pattern strings for one question (ordered by score desc).

    Backend-agnostic: `decoding` selects the strategy so the sweep/probe decode EXACTLY as the
    live SL (3.1) — diverse beam search for a local model (`strategy="beam"`, `diversity_penalty`)
    or temperature sampling for an API model (`strategy="sample"`, `temperature`/`top_p`). `k` is
    the number of completions. Reuses the SL inference configs so beam-mode output is byte-identical
    to the prior local sweeps.
    """
    k = decoding.get("k", 5)
    if decoding.get("strategy") == "sample":
        cfg = sl_sampling_config(k, decoding.get("temperature", 1.0), decoding.get("top_p", 1.0))
    else:
        cfg = sl_generation_config(k, decoding.get("diversity_penalty", 1.0))
    return [c.text.strip() for c in llm.generate(build_sl_prompt(question, schema_block), cfg)]


def normalised_entropy(beams: list[str]) -> float:
    """Shannon entropy over the distribution of DISTINCT beam patterns, normalised to [0,1].

    Counts identical pattern strings as the same outcome; H_norm = H / log(k). Low when beams
    collapse to one pattern (confident/unambiguous), high when spread (ambiguous).
    """
    counts = Counter(beams)
    total = sum(counts.values())
    probs = [c / total for c in counts.values()]
    h = -sum(p * math.log(p) for p in probs if p > 0)
    return h / math.log(len(beams)) if len(beams) > 1 else 0.0


def roc_auc(scores: list[float], labels: list[bool]) -> float:
    """AUC of score vs binary label (rank-based; no sklearn dependency required).

    Computed as the Mann-Whitney U statistic — the probability that a random positive
    (label True) outranks a random negative — with average ranks for tied scores. Returns
    0.5 when either class is empty (degenerate / constant scores included).
    """
    n_pos = sum(1 for lab in labels if lab)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Average ranks (1-based), ties sharing the mean of their rank span.
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0          # mean of ranks (i+1)..j inclusive
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j

    sum_ranks_pos = sum(ranks[i] for i, lab in enumerate(labels) if lab)
    return (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def covered(beams: list[str], gold_patterns: list[str]) -> bool:
    """Cov@k guardrail: does any beam match any gold pattern (normalised comparison)?"""
    golds = {_normalise_pattern(g) for g in gold_patterns if g}
    return any(_normalise_pattern(b) in golds for b in beams if b)


def hallucinated(beams: list[str], valid_labels: set[str], valid_rels: set[str]) -> float:
    """Fraction of beams referencing a label/relationship not in the POLE schema."""
    if not beams:
        return 0.0
    bad = 0
    for beam in beams:
        labels, rels = _referenced(beam)
        if any(label not in valid_labels for label in labels) or \
           any(rel not in valid_rels for rel in rels):
            bad += 1
    return bad / len(beams)


def gold_patterns(item: BenchmarkItem) -> list[str]:
    """Gold schema patterns for a benchmark item (Cov@5 reference set).

    `extract_schema_pattern(cypher_default)` plus, for ambiguous items, the extracted
    pattern of every interpretation's cypher. Parse failures (None) are dropped.
    """
    cyphers = [item.cypher_default]
    if item.is_ambiguous:
        cyphers += [interp["cypher"] for interp in item.interpretations if interp.get("cypher")]
    patterns = [extract_schema_pattern(c) for c in cyphers]
    return [p for p in patterns if p]


# ── Normalisation / reference extraction ─────────────────────────────────────────
# A node spec is ``(var:Label ...)`` and a relationship spec ``[var:TYPE ...]``; strip the
# variable name so comparison is over schema structure, not arbitrary beam variable names.
_VAR_BEFORE_LABEL = re.compile(r"([(\[])[A-Za-z_][A-Za-z0-9_]*:")
_NODE_LABEL = re.compile(r"\([^:()]*:\s*([A-Za-z_][A-Za-z0-9_]*)")
_REL_TYPE = re.compile(r"\[[^:\]]*:\s*([A-Za-z_][A-Za-z0-9_]*)")


def _normalise_pattern(pattern: str) -> str:
    """Strip whitespace and variable names so two patterns compare on structure alone."""
    collapsed = re.sub(r"\s+", "", pattern)
    return _VAR_BEFORE_LABEL.sub(r"\1:", collapsed)


def _referenced(beam: str) -> tuple[list[str], list[str]]:
    """The node labels and relationship types a beam string references."""
    return _NODE_LABEL.findall(beam), _REL_TYPE.findall(beam)
