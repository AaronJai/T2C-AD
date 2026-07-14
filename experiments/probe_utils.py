# experiments/probe_utils.py
"""Lightweight beam + entropy helpers for the diversity sweep (2.2) and probe re-run (2.3)."""
from __future__ import annotations

import math
import re
from collections import Counter

from pipeline.llm import BaseLLM
from pipeline.schema_linker.inference import sl_generation_config, sl_sampling_config
from pipeline.schema_linker.pattern_extraction import extract_schema_pattern
from pipeline.schema_linker.postprocessing import _has_active, _rel_element, parse_schema_pattern
from pipeline.schema_linker.prompts import build_sl_prompt, build_sl_prompt_api
from pipeline.types import BenchmarkItem


def generate_beams(llm: BaseLLM, question: str, schema_block: str, decoding: dict,
                   *, prompt_style: str = "completion") -> list[str]:
    """k SL completion pattern strings for one question (ordered by score desc).

    Backend-agnostic: `decoding` selects the strategy so the sweep/probe decode EXACTLY as the
    live SL (3.1) — diverse beam search for a local model (`strategy="beam"`, `diversity_penalty`)
    or temperature sampling for an API model (`strategy="sample"`, `temperature`/`top_p`). `k` is
    the number of completions. Reuses the SL inference configs so beam-mode output is byte-identical
    to the prior local sweeps.

    `prompt_style` mirrors `SchemaLinker` (8.1): "completion" (default) uses the shared
    `build_sl_prompt`; "instruct" uses `build_sl_prompt_api`, so the sweep/probe/G1 decode with
    the same prompt the live SL uses for the same backend.
    """
    k = decoding.get("k", 5)
    if decoding.get("strategy") == "sample":
        cfg = sl_sampling_config(k, decoding.get("temperature", 1.0), decoding.get("top_p", 1.0))
    else:
        cfg = sl_generation_config(k, decoding.get("diversity_penalty", 1.0))
    build_prompt = build_sl_prompt_api if prompt_style == "instruct" else build_sl_prompt
    return [c.text.strip() for c in llm.generate(build_prompt(question, schema_block), cfg)]


def _entropy_signature(beam: str):
    """Canonical signature used to count distinct beam outcomes for entropy.

    The direction-/dangling-connector-invariant `_canonical_pattern` structure — the same
    comparison `covered()` uses. Junk guard: when the signature is empty (no relationships AND
    no bare labels — i.e. unparseable/garbage), fall back to the raw string so distinct garbage
    completions keep counting as distinct outcomes (matching the pre-8.1 raw-string behaviour).
    """
    try:
        sig = _canonical_pattern(beam)
    except (ValueError, IndexError):
        sig = ((), ())
    return sig if sig != ((), ()) else beam


def normalised_entropy(beams: list[str]) -> float:
    """Shannon entropy over the distribution of DISTINCT beam pattern SIGNATURES, normalised
    to [0,1].

    Counts canonical `_canonical_pattern` signatures (8.1) rather than raw strings, so
    superficial phrasing variation across sampled completions no longer inflates entropy (which
    would corrupt the 8.3 temperature sweep and entropy-probe AUC); unparseable garbage falls
    back to its raw string. H_norm = H / log(k). Low when beams collapse to one structure
    (confident/unambiguous), high when spread (ambiguous).
    """
    counts = Counter(_entropy_signature(b) for b in beams)
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


class _AnySchema:
    """Accept-all stand-in for `parse_schema_pattern`'s schema arg: `covered()` only needs the
    structural (nodes/relationships) parse, not the label/rel-type validity check, so which real
    schema would be passed is irrelevant here."""
    node_labels: tuple = ()
    relationship_paths: tuple = ()


def _canonical_pattern(pattern: str) -> tuple:
    """Structural signature of a pattern: relationship (type, source_label, target_label,
    active) tuples in hop order, direction-canonicalised via the same `_rel_element` logic the
    live SL postprocessing (`pipeline/schema_linker/postprocessing.py`) uses to build a
    CandidateMapping. A dangling trailing `--` (see decisions-log 2026-06-15) is dropped the
    same way there too. Two Cypher strings describing the same schema pattern from opposite
    anchors, or differing only by a dangling connector, produce the same signature."""
    parsed = parse_schema_pattern(pattern, _AnySchema(), 0.0)
    alias_to_label = {alias: label for alias, label in parsed.nodes}
    rels = tuple(
        (elem.name, elem.source_label, elem.target_label, elem.parent)
        for elem in (
            _rel_element(src, rtype, tgt, direction, alias_to_label, active=_has_active(props))
            for src, rtype, tgt, direction, props in parsed.relationships
        )
    )
    touched = {alias for src, _rtype, tgt, _dir, _props in parsed.relationships for alias in (src, tgt)}
    bare_labels = tuple(sorted(
        label for alias, label in parsed.nodes if label and alias not in touched
    ))
    return (rels, bare_labels)


def covered(beams: list[str], gold_patterns: list[str]) -> bool:
    """Cov@k guardrail: does any beam match any gold pattern (structural comparison — direction-
    and dangling-connector-invariant, matching what the live SL postprocessing would accept)?"""
    golds = {_canonical_pattern(g) for g in gold_patterns if g}
    return any(_canonical_pattern(b) in golds for b in beams if b)


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
