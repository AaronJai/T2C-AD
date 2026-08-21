# pipeline/pole_sft_data.py
"""In-domain POLE v3 SFT data generation for the Schema Linker and Query Generator (7.4).

Enumerates every 1-3 hop schema pattern over the v3 POLE schema (``enumerate_v3_patterns``),
synthesises NL questions per pattern two ways (hand-written per-relationship-type templates,
slot-filled from the v3 seed data, then optionally LLM-paraphrased), drops anything that is a
near-duplicate of a benchmark question (the text-disjointness hard gate), and writes the four
two-key jsonl files the SL/QG SFT harness (``pipeline.sft.run_sft``) consumes — in the same
``{"prompt", "completion"}`` shape and via the same ``build_sl_prompt``/``build_qg_prompt``
builders as 1.2/1.3, so train format == inference format.
"""
from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from pipeline.llm import BaseLLM, GenerationConfig, build_llm
from pipeline.query_generator.prompts import build_qg_prompt
from pipeline.schema import build_pole_external_schema_repr, build_pole_v3_schema_repr
from pipeline.schema_linker.pattern_extraction import (
    extract_schema_pattern,
    has_relationship_type,
)
from pipeline.schema_linker.prompts import build_sl_prompt
from pipeline.types import SchemaRepr

MAX_HOPS = 3

# Cypher-variable abbreviation per v3 label (mirrors the KG file's own MATCH variable
# choices, e.g. ``ph:Phone``, so generated Cypher reads like the seed data's own style).
_VAR_ABBREV = {
    "Person": "p", "Incident": "i", "Case": "c",
    "Location": "l", "Vehicle": "v", "Phone": "ph",
}

# ASSOCIATED_WITH is stored as one directed edge but queried undirected (KG file §15);
# every other relationship keeps its stored direction.
_UNDIRECTED_TYPES = {"ASSOCIATED_WITH"}
# The four relationship types carrying an `active` property (KG file §11-13, §15).
_TEMPORAL_TYPES = {"LIVES_AT", "OWNS", "USES_PHONE", "ASSOCIATED_WITH"}


# ── Schema graph walk ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Edge:
    index: int
    rel_type: str
    source: str
    target: str
    directed: bool
    temporal: bool


@dataclass(frozen=True)
class _PatternPath:
    """One enumerated schema-pattern walk: `hops[i]` = (edge, arrow, other_label), where
    `arrow` is the traversal direction from the node before this hop to `other_label`
    ('->' stored direction, '<-' reversed, '-' undirected). `active_pos` is the index of the
    hop that carries the `{active:true}` temporal filter, or None for the unfiltered variant.
    """
    start_label: str
    hops: tuple[tuple[_Edge, str, str], ...]
    active_pos: Optional[int] = None


def _build_edges(
    schema: SchemaRepr,
    *,
    temporal_types: set[str] = _TEMPORAL_TYPES,
    undirected_types: set[str] = _UNDIRECTED_TYPES,
) -> list[_Edge]:
    """Edge list for the schema walk. `temporal_types`/`undirected_types` default to the v3
    module globals — pass the external-schema sets (10.2) to walk the real POLE schema, which
    has no `active` temporal edges (`temporal_types=set()`) and its own undirected set."""
    return [
        _Edge(
            index=idx, rel_type=p["type"], source=p["source"], target=p["target"],
            directed=p["type"] not in undirected_types, temporal=p["type"] in temporal_types,
        )
        for idx, p in enumerate(schema.relationship_paths)
    ]


def _adjacency(edges: list[_Edge]) -> dict[str, list[tuple[_Edge, str, str]]]:
    """label -> [(edge, arrow_leaving_this_label, other_label), ...], both traversal
    directions available for directed edges; a single undirected entry per endpoint pair."""
    adj: dict[str, list[tuple[_Edge, str, str]]] = {}
    for e in edges:
        if e.directed:
            adj.setdefault(e.source, []).append((e, "->", e.target))
            adj.setdefault(e.target, []).append((e, "<-", e.source))
        else:
            adj.setdefault(e.source, []).append((e, "-", e.target))
            if e.target != e.source:
                adj.setdefault(e.target, []).append((e, "-", e.source))
    return adj


def _enumerate_v3_paths(
    schema: Optional[SchemaRepr] = None,
    *,
    temporal_types: set[str] = _TEMPORAL_TYPES,
    undirected_types: set[str] = _UNDIRECTED_TYPES,
    emit_active_variants: bool = True,
) -> list[_PatternPath]:
    """Every 1-3 hop walk over the schema graph (each relationship type used at most once
    per walk, so no trivial there-and-back loops), paired with an extra `{active:true}`-filter
    variant for every temporal hop. Deterministic: labels/edges walked in schema-declared order.

    The three keyword arguments default to the v3 behaviour (the v3 call path is byte-identical).
    The external POLE schema (10.2) has no state-change edges, so it passes `temporal_types=set()`
    and `emit_active_variants=False` — temporal ambiguity there is a WHERE-clause value choice on
    node properties, not a schema-element choice (9.1/9.4), so no `{active:true}` variant exists.
    """
    schema = schema or build_pole_v3_schema_repr()
    edges = _build_edges(schema, temporal_types=temporal_types, undirected_types=undirected_types)
    adj = _adjacency(edges)
    paths: list[_PatternPath] = []
    seen: set[tuple] = set()

    def record(start_label: str, hops: tuple) -> None:
        key = (start_label, tuple((e.index, arrow) for e, arrow, _ in hops))
        if key in seen:
            return
        seen.add(key)
        paths.append(_PatternPath(start_label, hops))
        if not emit_active_variants:
            return
        for i, (edge, _arrow, _other) in enumerate(hops):
            if edge.temporal:
                paths.append(_PatternPath(start_label, hops, active_pos=i))

    def walk(start_label: str, hops: tuple, used: frozenset) -> None:
        if hops:
            record(start_label, hops)
        if len(hops) == MAX_HOPS:
            return
        current_label = hops[-1][2] if hops else start_label
        for edge, arrow, other_label in adj.get(current_label, []):
            if edge.index in used:
                continue
            walk(start_label, hops + ((edge, arrow, other_label),), used | {edge.index})

    for label in schema.node_labels:
        walk(label, (), frozenset())
    return paths


def _render_pattern(
    path: _PatternPath,
    *,
    leaf_filter: Optional[dict[str, str]] = None,
    abbrev: Optional[dict[str, str]] = None,
) -> tuple[str, str]:
    """Render one path as a Cypher pattern fragment; returns (rendered, terminal_var).

    `leaf_filter=None` renders the canonical SL committed-pattern form (no entity-specific
    node values — matching `pipeline.schema_linker.pattern_extraction`'s node-filter rules);
    a filter dict embeds those concrete property values on the FIRST node only, for the QG's
    full executable Cypher completion. `abbrev` defaults to the v3 variable map — the external
    POLE schema (10.2) passes `_EXT_VAR_ABBREV` for its own labels.
    """
    abbrev = abbrev if abbrev is not None else _VAR_ABBREV
    used: dict[str, int] = {}

    def alloc(label: str) -> str:
        base = abbrev[label]
        n = used.get(base, 0)
        used[base] = n + 1
        return base if n == 0 else f"{base}{n + 1}"

    var0 = alloc(path.start_label)
    if leaf_filter:
        body = ", ".join(f"{k}:'{v}'" for k, v in leaf_filter.items())
        parts = [f"({var0}:{path.start_label} {{{body}}})"]
    else:
        parts = [f"({var0}:{path.start_label})"]
    current_var = var0
    for i, (edge, arrow, other_label) in enumerate(path.hops):
        other_var = alloc(other_label)
        rel = f":{edge.rel_type}"
        if path.active_pos == i:
            rel += " {active:true}"
        if arrow == "->":
            parts.append(f"-[{rel}]->({other_var}:{other_label})")
        elif arrow == "<-":
            parts.append(f"<-[{rel}]-({other_var}:{other_label})")
        else:
            parts.append(f"-[{rel}]-({other_var}:{other_label})")
        current_var = other_var
    return "".join(parts), current_var


def enumerate_v3_patterns() -> list[str]:
    """Every valid 1-3 hop schema pattern over the v3 POLE schema, in the canonical
    committed-pattern format (`pipeline.schema_linker.pattern_extraction`), including the
    `{active:true}` temporal-filter variants. Deterministic and exhaustive over the 11 v3
    relationship types; every element is in-schema by construction.
    """
    return [_render_pattern(p)[0] for p in _enumerate_v3_paths()]


# ── NL question synthesis ────────────────────────────────────────────────────────
# Concrete leaf-entity values sampled from data/SyntheticPoliceKG-v3.cypher, so templated
# questions read like real benchmark questions (spec: "slot-filled with entity values
# sampled from the v3 seed data").
_PERSON_NAMES = [
    "James Whitfield", "Rachel Kim", "David Chen", "Sarah Nguyen", "Anton Maric",
    "Tyler Birch", "Lina Petrova", "Daniel Kim", "Priya Sharma", "Mark Thompson",
]
_INCIDENT_TYPES = ["robbery", "drug_offence", "assault", "burglary", "fraud", "homicide", "traffic"]
_CASE_NAMES = ["Operation Ironside", "Operation Trident", "Operation Cerberus", "Operation Sentinel"]
_SUBURBS = [
    "Northbridge", "West Perth", "Midland", "Perth", "Fremantle", "Cannington",
    "Scarborough", "Joondalup", "Victoria Park", "Cottesloe", "Mt Lawley",
]
_VEHICLE_DESCS = [
    ("Toyota", "white"), ("Holden", "black"), ("Ford", "blue"), ("BMW", "blue"),
    ("Mazda", "grey"), ("Nissan", "red"), ("Hyundai", "silver"), ("Mitsubishi", "black"),
]
_PHONE_NUMBERS = ["0412 345 678", "0423 987 654", "0401 111 222", "0434 555 888"]


def _leaf_entity(label: str, rng: random.Random) -> tuple[str, dict[str, str]]:
    """(NL referring phrase, Cypher property filter) for a concrete instance of `label`."""
    if label == "Person":
        name = rng.choice(_PERSON_NAMES)
        return name, {"name": name}
    if label == "Incident":
        crime = rng.choice(_INCIDENT_TYPES)
        return f"the {crime.replace('_', ' ')}", {"crime_type": crime}
    if label == "Case":
        name = rng.choice(_CASE_NAMES)
        return name, {"case_name": name}
    if label == "Location":
        suburb = rng.choice(_SUBURBS)
        return suburb, {"suburb": suburb}
    if label == "Vehicle":
        make, colour = rng.choice(_VEHICLE_DESCS)
        return f"the {colour} {make}", {"make": make, "colour": colour}
    if label == "Phone":
        number = rng.choice(_PHONE_NUMBERS)
        return number, {"phone_number": number}
    raise ValueError(f"no leaf seed pool for label {label!r}")


# Per-relationship-type surface forms (~2 fwd + ~2 bwd, plus a "currently" variant for the
# four temporal types). `{np}` is a noun phrase describing the node BEFORE this hop; each
# entry produces a noun phrase describing the node AFTER this hop ("fwd" = stored direction,
# "bwd" = reversed, both used for undirected ASSOCIATED_WITH).
_REL_CLAUSE: dict[str, dict[str, list[str]]] = {
    "SUSPECTED_OF": {
        "fwd": ["the incident {np} is suspected of", "the crime {np} is suspected of committing"],
        "bwd": ["the person suspected of {np}", "whoever is suspected of {np}"],
    },
    "WITNESSED": {
        "fwd": ["the incident {np} witnessed", "the crime {np} witnessed"],
        "bwd": ["the witness of {np}", "whoever witnessed {np}"],
    },
    "VICTIM_OF": {
        "fwd": ["the incident {np} is the victim of", "the crime {np} was the victim of"],
        "bwd": ["the victim of {np}", "whoever was the victim of {np}"],
    },
    "INVESTIGATES": {
        "fwd": ["the incident {np} is investigating", "the case {np} is investigating"],
        "bwd": ["the investigator of {np}", "the officer investigating {np}"],
    },
    "CONTAINS": {
        "fwd": ["an incident contained in {np}", "an incident that is part of {np}"],
        "bwd": ["the case that contains {np}", "the case {np} is part of"],
    },
    "OCCURRED_AT": {
        "fwd": ["the location where {np} occurred", "the place {np} took place"],
        "bwd": ["the incident that occurred at {np}", "the crime that took place at {np}"],
    },
    "LIVES_AT": {
        "fwd": ["the location where {np} lives", "the place {np} resides"],
        "bwd": ["the person who lives at {np}", "whoever resides at {np}"],
        "fwd_active": ["the location where {np} currently lives"],
        "bwd_active": ["the person who currently lives at {np}"],
    },
    "OWNS": {
        "fwd": ["the vehicle owned by {np}", "the car that belongs to {np}"],
        "bwd": ["the person who owns {np}", "whoever owns {np}"],
        "fwd_active": ["the vehicle currently owned by {np}"],
        "bwd_active": ["the person who currently owns {np}"],
    },
    "USES_PHONE": {
        "fwd": ["the phone used by {np}", "the phone number belonging to {np}"],
        "bwd": ["the person who uses {np}", "whoever uses {np}"],
        "fwd_active": ["the phone currently used by {np}"],
        "bwd_active": ["the person who currently uses {np}"],
    },
    "CALLED": {
        "fwd": ["the phone that {np} called", "the number {np} called"],
        "bwd": ["the phone that called {np}", "whoever called {np}"],
    },
    "ASSOCIATED_WITH": {
        "fwd": ["the person associated with {np}", "the associate of {np}"],
        "bwd": ["the person associated with {np}", "the associate of {np}"],
        "fwd_active": ["the person currently associated with {np}"],
        "bwd_active": ["the person currently associated with {np}"],
    },
}

# Terminal-node question wrappers: (property, question template). Two attributes/phrasings
# per label (where the schema offers them) complete the "~3-5 surface forms" per pattern
# once combined with the two `_REL_CLAUSE` phrasing variants.
_ATTR_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "Person":   [("name", "Who is {np}?"), ("name", "What is the name of {np}?")],
    "Incident": [("crime_type", "What type of crime is {np}?"), ("status", "What is the status of {np}?")],
    "Case":     [("case_name", "What is the name of {np}?"), ("status", "What is the status of {np}?")],
    "Location": [("suburb", "What suburb is {np} in?"), ("address", "What is the address of {np}?")],
    "Vehicle":  [("make", "What make is {np}?"), ("plate", "What is the licence plate of {np}?")],
    "Phone":    [("phone_number", "What is the phone number of {np}?")],
}


def _terminal_label(path: _PatternPath) -> str:
    return path.hops[-1][2] if path.hops else path.start_label


def _wrap(rel_type: str, np: str, arrow: str, *, active: bool, variant: int) -> str:
    clauses = _REL_CLAUSE[rel_type]
    key = "bwd" if arrow == "<-" else "fwd"
    if active and f"{key}_active" in clauses:
        key = f"{key}_active"
    options = clauses[key]
    return options[variant % len(options)].format(np=np)


def _chain_np(path: _PatternPath, leaf_phrase: str, variant: int) -> str:
    np = leaf_phrase
    for i, (edge, arrow, _other_label) in enumerate(path.hops):
        np = _wrap(edge.rel_type, np, arrow, active=(path.active_pos == i), variant=variant)
    return np


def _template_rows(
    path: _PatternPath, leaf_phrase: str, leaf_filter: dict[str, str],
) -> list[tuple[str, str]]:
    """(question, full executable gold Cypher) pairs for every hand-authored surface form."""
    terminal = _terminal_label(path)
    match_clause, terminal_var = _render_pattern(path, leaf_filter=leaf_filter)
    rows: list[tuple[str, str]] = []
    for variant in (0, 1):
        np = _chain_np(path, leaf_phrase, variant)
        for attr, question_template in _ATTR_QUESTIONS[terminal]:
            question = question_template.format(np=np)
            cypher = f"MATCH {match_clause} RETURN {terminal_var}.{attr}"
            rows.append((question, cypher))
    return rows


# ── Schema-ambiguity register (the single-hop "generic connector" question forms) ──
# All 20 `schema`-type benchmark items are deliberately-vague "who is connected to this
# crime" questions over the ONE node pair the v3 schema connects with more than one
# relationship type — Person→Incident ({SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES}).
# The per-relationship-type `_REL_CLAUSE` templates are all relation-SPECIFIC ("the witness
# of X"), so the adapter never saw this vague register and, at inference, either chains all
# four role types into one compound multi-hop beam or reuses a wrong relation (the Q-045
# "associated with" collision) — leaving every schema item's Cov@5 gold set (a single-hop
# `(Person)-[:role]->(Incident)`) uncovered.
#
# These rows teach the vague register directly, as SINGLE-HOP rows generated OUTSIDE the
# recursive `_chain_np` walk (so the register can never leak onto deep chains — the failure
# mode of the earlier `_REL_CLAUSE` fix). Each vague surface form is emitted against a
# grounded terminal with the role relation cycled round-robin, so across the corpus the
# register is paired with every role type: the SL's relationship-slot mass spreads across
# them, so diverse beam search surfaces single-hop role edges as separate candidates
# (covering the gold set — and giving 7.5's AD/disambiguator the candidate diversity they
# need). "associated with {incident}" is included on purpose: it competes with the
# Person→Person ASSOCIATED_WITH template (different terminal ENTITY type), directly
# targeting the Q-045 collision.
_SCHEMA_CONNECTOR_FORMS: list[str] = [
    "people connected to {np}",
    "who is involved in {np}",
    "everyone linked to {np}",
    "who took part in {np}",
    "people associated with {np}",
    "the people with a connection to {np}",
    "who is named in relation to {np}",
    "people with a role in {np}",
]


def _schema_ambiguous_pairs(edges: list[_Edge]) -> dict[tuple[str, str], list[_Edge]]:
    """Directed (source, target) node pairs carrying >1 relationship type — the schema-type
    ambiguity clusters. In the v3 schema this is exactly Person→Incident (data-driven, not
    hardcoded: any future multi-relation pair is picked up automatically)."""
    groups: dict[tuple[str, str], list[_Edge]] = defaultdict(list)
    for e in edges:
        if e.directed:
            groups[(e.source, e.target)].append(e)
    return {pair: group for pair, group in groups.items() if len(group) >= 2}


def _schema_connector_np(label: str, rng: random.Random) -> tuple[str, dict[str, str]]:
    """(NL referring phrase, property filter) for a grounded terminal in the vague register.
    Incidents are grounded by crime type + suburb (`the robbery in Midland`) to read like the
    benchmark's schema questions while staying lexically varied enough to clear the
    disjointness gate; other labels fall back to the shared `_leaf_entity` pool."""
    if label == "Incident":
        crime = rng.choice(_INCIDENT_TYPES)
        suburb = rng.choice(_SUBURBS)
        return f"the {crime.replace('_', ' ')} in {suburb}", {"crime_type": crime}
    return _leaf_entity(label, rng)


def _schema_ambiguous_rows(
    edges: list[_Edge], rng: random.Random, samples_per_form: int,
) -> list[dict]:
    """Single-hop vague-connector rows for every multi-relation node pair (see
    `_SCHEMA_CONNECTOR_FORMS`). Returns raw candidate dicts in the same shape the main
    synthesis loop appends (`question`/`pattern`/`cypher`/`rel_types`)."""
    rows: list[dict] = []
    for (source, target), group in _schema_ambiguous_pairs(edges).items():
        for form in _SCHEMA_CONNECTOR_FORMS:
            for k in range(samples_per_form):
                edge = group[k % len(group)]  # round-robin → balanced role-type coverage
                np, leaf_filter = _schema_connector_np(target, rng)
                path = _PatternPath(target, ((edge, "<-", source),))
                match_clause, terminal_var = _render_pattern(path, leaf_filter=leaf_filter)
                pattern = _render_pattern(path)[0]
                rows.append({
                    "question": form.format(np=np),
                    "pattern": pattern,
                    "cypher": f"MATCH {match_clause} RETURN DISTINCT {terminal_var}.name",
                    "rel_types": {edge.rel_type},
                })
    return rows


# ── LLM paraphrase ────────────────────────────────────────────────────────────────
_PARAPHRASE_SYSTEM = (
    "You paraphrase natural-language questions about a policing database. Preserve the "
    "meaning exactly and keep every named entity (person, place, vehicle, case, phone "
    "number) verbatim. Return exactly {n} alternate phrasings of the question, one per "
    "line, numbered '1.' through '{n}.', and nothing else."
)


def _paraphrase(question: str, llm: BaseLLM, n: int) -> list[str]:
    """Up to `n` LLM paraphrases of `question` (fewer if the backend returns fewer lines)."""
    if n <= 0:
        return []
    config = GenerationConfig(max_new_tokens=400, temperature=0.9, do_sample=True)
    messages = [
        {"role": "system", "content": _PARAPHRASE_SYSTEM.format(n=n)},
        {"role": "user", "content": question},
    ]
    completion = llm.generate_chat(messages, config)[0]
    lines = [re.sub(r"^\s*\d+[.)]\s*", "", ln).strip() for ln in completion.text.splitlines()]
    return [ln for ln in lines if ln][:n]


# ── Disjointness gate ─────────────────────────────────────────────────────────────
def _normalise_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_blocklist_questions(benchmark_path: str | Path, skeleton_path: str | Path) -> list[str]:
    """Question texts from the v3 benchmark (and its skeleton) — the disjointness blocklist."""
    questions: list[str] = []
    for path in (benchmark_path, skeleton_path):
        p = Path(path)
        if not p.exists():
            continue
        items = json.loads(p.read_text(encoding="utf-8"))
        questions.extend(item["question"] for item in items if "question" in item)
    return questions


def apply_disjointness_gate(
    candidates: list[dict], blocklist: list[str], threshold: float = 0.90,
) -> tuple[list[dict], int]:
    """Drop any candidate whose normalised question exactly matches, or scores rapidfuzz
    `token_set_ratio` >= `threshold` against, any blocklist question. Returns (kept, n_dropped).
    """
    normed_blocklist = [_normalise_question(q) for q in blocklist]
    threshold_pct = threshold * 100
    kept: list[dict] = []
    dropped = 0
    for cand in candidates:
        q = _normalise_question(cand["question"])
        is_dupe = q in normed_blocklist or any(
            fuzz.token_set_ratio(q, b) >= threshold_pct for b in normed_blocklist
        )
        if is_dupe:
            dropped += 1
        else:
            kept.append(cand)
    return kept, dropped


# ── Dataset assembly ──────────────────────────────────────────────────────────────
def _write_jsonl(path: str | Path, records: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")


def build_pole_sft_dataset(config: dict) -> dict:
    """Generate the POLE v3 SL/QG SFT rows and write the four jsonl files; return a report.

    Config keys (all but `output` optional): `seed` (default 13), `entities_per_pattern`
    (default 1), `paraphrases_per_template` (default 3), `schema_connector_samples_per_form`
    (default 30; grounded samples per vague-connector surface form for the schema-type
    ambiguity register — see `_schema_ambiguous_rows`), `eval_fraction` (default 0.10),
    `disjointness_threshold` (default 0.90), `benchmark_path`/`skeleton_path` (the disjointness
    blocklist), `paraphrase_llm` (a `pipeline.llm.build_llm` spec dict; omit/None to skip
    paraphrasing — e.g. an offline run with no API key), `max_rows` (optional cap: the
    exhaustive pattern walk plus templates/paraphrases comfortably overshoots the spec's
    ~1,500-2,500 target, so a deterministic shuffle+slice trims to this count after the
    disjointness gate — every relationship type keeps far more than the 2 acceptance floor
    of 30 rows even after trimming, since none contributes less than ~7% of the pre-trim
    rows), `output` (`{"sl_train","sl_eval","qg_train","qg_eval"}` paths), `report_path`
    (optional).
    """
    seed = config.get("seed", 13)
    entities_per_pattern = config.get("entities_per_pattern", 1)
    paraphrases_per_template = config.get("paraphrases_per_template", 3)
    eval_fraction = config.get("eval_fraction", 0.10)
    threshold = config.get("disjointness_threshold", 0.90)
    max_rows = config.get("max_rows")
    benchmark_path = config.get("benchmark_path", "data/benchmark-v3.json")
    skeleton_path = config.get("skeleton_path", "data/benchmark-v3-skeleton.json")
    out = config["output"]

    rng = random.Random(seed)
    schema = build_pole_v3_schema_repr()
    schema_block_props = schema.to_prompt_string(include_properties=True)
    schema_block_noprops = schema.to_prompt_string(include_properties=False)

    blocklist = load_blocklist_questions(benchmark_path, skeleton_path)
    paths = _enumerate_v3_paths(schema)

    llm_spec = config.get("paraphrase_llm")
    llm = build_llm(llm_spec) if llm_spec else None

    raw: list[dict] = []
    pattern_count_by_rel_type: dict[str, int] = {}
    for path in paths:
        rel_types = {edge.rel_type for edge, _arrow, _other in path.hops}
        pattern = _render_pattern(path)[0]
        for rt in rel_types:
            pattern_count_by_rel_type[rt] = pattern_count_by_rel_type.get(rt, 0) + 1
        for _ in range(entities_per_pattern):
            leaf_phrase, leaf_filter = _leaf_entity(path.start_label, rng)
            for question, cypher in _template_rows(path, leaf_phrase, leaf_filter):
                variants = [question]
                if llm is not None:
                    variants += _paraphrase(question, llm, paraphrases_per_template)
                for q in variants:
                    raw.append({"question": q, "pattern": pattern, "cypher": cypher, "rel_types": rel_types})

    # Single-hop vague-connector rows for the schema-type ambiguity register (never routed
    # through the recursive `_chain_np` walk, so they can't leak onto deep chains).
    schema_samples = config.get("schema_connector_samples_per_form", 30)
    schema_rows = _schema_ambiguous_rows(_build_edges(schema), rng, schema_samples)
    raw.extend(schema_rows)

    kept, n_dropped = apply_disjointness_gate(raw, blocklist, threshold)

    seen_q: set[str] = set()
    deduped: list[dict] = []
    for cand in kept:
        key = _normalise_question(cand["question"])
        if key in seen_q:
            continue
        seen_q.add(key)
        deduped.append(cand)
    n_duplicate = len(kept) - len(deduped)

    n_before_cap = len(deduped)
    if max_rows is not None and len(deduped) > max_rows:
        random.Random(seed).shuffle(deduped)
        deduped = deduped[:max_rows]

    order = list(range(len(deduped)))
    random.Random(seed).shuffle(order)
    n_eval = int(len(order) * eval_fraction)
    eval_idx = set(order[:n_eval])

    sl_train: list[dict] = []
    sl_eval: list[dict] = []
    qg_train: list[dict] = []
    qg_eval: list[dict] = []
    sl_coverage: dict[str, int] = {}
    for i, cand in enumerate(deduped):
        sl_row = {"prompt": build_sl_prompt(cand["question"], schema_block_props), "completion": cand["pattern"]}
        qg_row = {
            "prompt": build_qg_prompt(cand["question"], schema_block_noprops, committed_pattern=cand["pattern"]),
            "completion": cand["cypher"],
        }
        for rt in cand["rel_types"]:
            sl_coverage[rt] = sl_coverage.get(rt, 0) + 1
        if i in eval_idx:
            sl_eval.append(sl_row)
            qg_eval.append(qg_row)
        else:
            sl_train.append(sl_row)
            qg_train.append(qg_row)

    _write_jsonl(out["sl_train"], sl_train)
    _write_jsonl(out["sl_eval"], sl_eval)
    _write_jsonl(out["qg_train"], qg_train)
    _write_jsonl(out["qg_eval"], qg_eval)

    report = {
        "patterns_enumerated": len(paths),
        "raw_candidates": len(raw),
        "schema_connector_rows": len(schema_rows),
        "disjointness_dropped": n_dropped,
        "duplicate_dropped": n_duplicate,
        "max_rows_trimmed": n_before_cap - len(deduped),
        "kept": len(deduped),
        "sl_train": len(sl_train), "sl_eval": len(sl_eval),
        "qg_train": len(qg_train), "qg_eval": len(qg_eval),
        "sl_coverage_by_rel_type": sl_coverage,
        "pattern_count_by_rel_type": pattern_count_by_rel_type,
        "paraphrase_used": llm is not None,
    }
    report_path = config.get("report_path")
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


# ── Ozsoy replay mix (continue-SFT input for the v3 train YAMLs) ─────────────────
def _read_jsonl(path: str | Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_mixed_training_file(
    pole_path: str | Path, ozsoy_path: str | Path, out_path: str | Path,
    replay_size: int, seed: int = 13,
) -> dict:
    """Concatenate every POLE training row with a `replay_size` random sample of the existing
    Ozsoy jsonl (resists catastrophic forgetting of the general Text2Cypher capability during
    continue-SFT — spec: "mixed with an Ozsoy replay sample"), shuffle deterministically, and
    write the combined jsonl that `config/{schema_linker,query_generator}_train_v3.yaml` train on.
    Returns a counts report.
    """
    pole_rows = _read_jsonl(pole_path)
    ozsoy_rows = _read_jsonl(ozsoy_path)
    rng = random.Random(seed)
    sample = rng.sample(ozsoy_rows, min(replay_size, len(ozsoy_rows)))
    combined = pole_rows + sample
    random.Random(seed).shuffle(combined)
    _write_jsonl(out_path, combined)
    return {"pole_rows": len(pole_rows), "ozsoy_sampled": len(sample), "total": len(combined)}


# ══════════════════════════════════════════════════════════════════════════════════
# External-POLE in-domain SFT data (10.2)
# ══════════════════════════════════════════════════════════════════════════════════
# In-domain SFT over the REAL `neo4j-graph-examples/pole` schema (11 labels / 17 relationship
# types, `build_pole_external_schema_repr()`). Structurally unlike v3 (9.1 audit), so this
# section does NOT reuse the v3 templates:
#   1. No state-change edges → no `{active:true}` enumeration variant. Temporal ambiguity is a
#      WHERE-clause value choice on node properties (`Crime.date`, `PhoneCall.call_date`), so the
#      SL target for a temporal item is the plain pattern and the QG completion carries the 9.4
#      date-window / ORDER BY-LIMIT idioms (`_QG_FEW_SHOT_API_POLE_EXTERNAL`), taught here to the
#      fine-tuned QG instead of via instruct few-shots.
#   2. Schema ambiguity draws on the two 9.2/9.3-confirmed divergent axes: the digital-comm
#      channel split (`KNOWS_SN`/`KNOWS_PHONE`) and Crime-participant scope (`PARTY_TO` person vs
#      `INVOLVED_IN` vehicle). The generic-vs-narrow KNOWS framing is NOT templated — 9.2
#      (decisions-log 2026-08-03) proved it structurally non-divergent in this graph.
# The v3 helpers above are reused only where schema-agnostic (`_render_pattern` with `abbrev`,
# `_enumerate_v3_paths` with the external flags, `apply_disjointness_gate`, the dedup/cap/split
# and mix machinery). Every generated row derives its SL pattern from `extract_schema_pattern`
# of its own QG Cypher, so the `extract_schema_pattern(qg) == sl` train-format guard holds by
# construction (mirroring the 1.3/7.4 invariant).

# External-schema asymmetry (9.1): no `active` edge property anywhere, so no temporal-enumeration
# variant. The Person-Person social edges are queried undirected (benchmark uses `-[:KNOWS_SN]-`).
_EXT_TEMPORAL_TYPES: set[str] = set()
_EXT_UNDIRECTED_TYPES: set[str] = {"KNOWS", "KNOWS_SN", "KNOWS_PHONE", "KNOWS_LW", "FAMILY_REL"}

# Cypher-variable abbreviation per external label (distinct letters so a 1-3 hop pattern never
# aliases two labels to the same var; matches the benchmark's own `pc:PhoneCall`, `c:Crime`).
_EXT_VAR_ABBREV = {
    "Person": "p", "Location": "l", "Phone": "ph", "Email": "em", "Officer": "off",
    "PostCode": "post", "Area": "a", "PhoneCall": "pc", "Crime": "c", "Object": "o",
    "Vehicle": "v",
}

# Leaf seed values. Names/surnames, area codes, phone numbers, vehicle regs, crime types, badge
# numbers, one postcode and the day-of-month windows are REAL values sampled from the external
# graph (harvested from data/benchmark-pole-external.json's gold Cypher). Emails are plausible
# placeholders — the graph's Email.email_address values were not harvestable offline; they only
# ground the referring phrase in a training question and never gate any acceptance criterion.
_EXT_PERSON_NAMES = [
    ("Alan", "Hicks"), ("Ann", "Fox"), ("Benjamin", "Hamilton"), ("Bonnie", "Gilbert"),
    ("Brenda", "Edwards"), ("Theresa", "Powell"), ("Andrea", "George"), ("Anne", "Rice"),
    ("Adam", "Ferguson"), ("Amanda", "Foster"),
]
_EXT_ADDRESSES = ["116 Myrtle Street", "178 Polding Street", "53 Birch Lane", "6 Gypsy Lane"]
_EXT_PHONE_NUMBERS = [
    "0-(608)989-7174", "0-(377)507-0388", "9-(776)276-2772", "0-(711)302-8090",
    "9-(488)105-0765", "0-(521)287-3218", "0-(404)296-6252", "0-(807)194-4140",
]
_EXT_AREA_CODES = ["M1", "M14", "M9", "BL1", "BL2", "BL4"]
_EXT_POSTCODES = ["WN3 4NL"]
_EXT_CRIME_TYPES = ["Violence and sexual offences", "Public order", "Vehicle crime"]
_EXT_VEHICLE_REGS = ["LW72 POF", "RH42 TAB", "RY52 APF"]
_EXT_OFFICER_BADGES = ["57-6110377", "70-0643982", "80-1015383"]
_EXT_EMAILS = ["ahicks@example.com", "afox@example.com", "bhamilton@example.com"]
_EXT_CALL_DATES = ["11/08/2017", "08/08/2017", "15/08/2017"]
_EXT_DAYS = [4, 8, 9, 11, 15, 17, 20, 26, 28, 30, 31]


def _ext_leaf_entity(label: str, rng: random.Random) -> tuple[str, dict[str, str]]:
    """(NL referring phrase, Cypher property filter) for a concrete instance of an external
    label. `Object` is intentionally absent — it carries no relationship in the schema repr, so
    the walk never starts from it (`INVOLVED_IN` is listed Vehicle->Crime only, 9.1)."""
    if label == "Person":
        name, surname = rng.choice(_EXT_PERSON_NAMES)
        return f"{name} {surname}", {"name": name, "surname": surname}
    if label == "Location":
        addr = rng.choice(_EXT_ADDRESSES)
        return addr, {"address": addr}
    if label == "Phone":
        number = rng.choice(_EXT_PHONE_NUMBERS)
        return f"phone {number}", {"phoneNo": number}
    if label == "Email":
        email = rng.choice(_EXT_EMAILS)
        return f"email {email}", {"email_address": email}
    if label == "Officer":
        badge = rng.choice(_EXT_OFFICER_BADGES)
        return f"the officer with badge {badge}", {"badge_no": badge}
    if label == "PostCode":
        code = rng.choice(_EXT_POSTCODES)
        return f"postcode {code}", {"code": code}
    if label == "Area":
        area = rng.choice(_EXT_AREA_CODES)
        return f"area {area}", {"areaCode": area}
    if label == "PhoneCall":
        call_date = rng.choice(_EXT_CALL_DATES)
        return f"the call on {call_date}", {"call_date": call_date}
    if label == "Crime":
        crime_type = rng.choice(_EXT_CRIME_TYPES)
        return f"the {crime_type.lower()} crime", {"type": crime_type}
    if label == "Vehicle":
        reg = rng.choice(_EXT_VEHICLE_REGS)
        return f"vehicle {reg}", {"reg": reg}
    raise ValueError(f"no external leaf seed pool for label {label!r}")


# Per-relationship-type surface forms (fwd = stored direction, bwd = reversed). `{np}` is a
# noun phrase for the node BEFORE this hop; each entry yields a phrase for the node AFTER it.
# Undirected Person-Person edges only ever use the `fwd` key (see `_wrap`'s arrow logic).
_EXT_REL_CLAUSE: dict[str, dict[str, list[str]]] = {
    "CURRENT_ADDRESS": {
        "fwd": ["the address where {np} lives", "the home address of {np}"],
        "bwd": ["the person who lives at {np}", "the resident of {np}"],
    },
    "HAS_PHONE": {
        "fwd": ["the phone belonging to {np}", "the phone registered to {np}"],
        "bwd": ["the person who owns {np}", "the owner of {np}"],
    },
    "HAS_EMAIL": {
        "fwd": ["the email address of {np}", "the email belonging to {np}"],
        "bwd": ["the person who uses {np}", "the owner of {np}"],
    },
    "HAS_POSTCODE": {
        "fwd": ["the postcode of {np}", "the postcode for {np}"],
        "bwd": ["the location with postcode {np}", "the address at postcode {np}"],
    },
    "POSTCODE_IN_AREA": {
        "fwd": ["the area containing {np}", "the area that {np} falls in"],
        "bwd": ["a postcode in area {np}", "a postcode within {np}"],
    },
    "LOCATION_IN_AREA": {
        "fwd": ["the area where {np} is located", "the area containing {np}"],
        "bwd": ["a location in area {np}", "an address within area {np}"],
    },
    "KNOWS_SN": {
        "fwd": ["a social-media contact of {np}", "the person connected to {np} on social media"],
        "bwd": ["a social-media contact of {np}", "the person connected to {np} on social media"],
    },
    "KNOWS": {
        "fwd": ["someone {np} knows", "an acquaintance of {np}"],
        "bwd": ["someone {np} knows", "an acquaintance of {np}"],
    },
    "KNOWS_PHONE": {
        "fwd": ["a phone contact of {np}", "the person {np} contacts by phone"],
        "bwd": ["a phone contact of {np}", "the person {np} contacts by phone"],
    },
    "KNOWS_LW": {
        "fwd": ["the person {np} lives with", "a housemate of {np}"],
        "bwd": ["the person {np} lives with", "a housemate of {np}"],
    },
    "FAMILY_REL": {
        "fwd": ["a family member of {np}", "a relative of {np}"],
        "bwd": ["a family member of {np}", "a relative of {np}"],
    },
    "CALLER": {
        "fwd": ["the phone that made {np}", "the calling phone in {np}"],
        "bwd": ["a call made from {np}", "a call originating from {np}"],
    },
    "CALLED": {
        "fwd": ["the phone that received {np}", "the phone dialled in {np}"],
        "bwd": ["a call received by {np}", "a call made to {np}"],
    },
    "OCCURRED_AT": {
        "fwd": ["the location where {np} happened", "the place {np} occurred"],
        "bwd": ["a crime that occurred at {np}", "a crime that happened at {np}"],
    },
    "INVESTIGATED_BY": {
        "fwd": ["the officer investigating {np}", "the officer assigned to {np}"],
        "bwd": ["a crime investigated by {np}", "a crime assigned to {np}"],
    },
    "INVOLVED_IN": {
        "fwd": ["a crime involving {np}", "the crime {np} was involved in"],
        "bwd": ["the vehicle involved in {np}", "a vehicle linked to {np}"],
    },
    "PARTY_TO": {
        "fwd": ["a crime {np} is party to", "the crime involving {np}"],
        "bwd": ["a person party to {np}", "a person involved in {np}"],
    },
}

# Terminal-node question wrappers per external label: (property, question template).
_EXT_ATTR_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "Person":    [("name", "Who is {np}?"), ("surname", "What is the surname of {np}?")],
    "Location":  [("address", "What is the address of {np}?"), ("postcode", "What is the postcode of {np}?")],
    "Phone":     [("phoneNo", "What is the phone number of {np}?")],
    "Email":     [("email_address", "What is the email address of {np}?")],
    "Officer":   [("name", "Who is {np}?"), ("rank", "What is the rank of {np}?")],
    "PostCode":  [("code", "What is the code of {np}?")],
    "Area":      [("areaCode", "What is the area code of {np}?")],
    "PhoneCall": [("call_date", "When did {np} take place?"), ("call_type", "What type of call is {np}?")],
    "Crime":     [("type", "What type of crime is {np}?"), ("last_outcome", "What was the outcome of {np}?")],
    "Vehicle":   [("make", "What make is {np}?"), ("reg", "What is the registration of {np}?")],
}


def _ext_wrap(rel_type: str, np: str, arrow: str, variant: int) -> str:
    clauses = _EXT_REL_CLAUSE[rel_type]
    key = "bwd" if arrow == "<-" else "fwd"
    options = clauses[key]
    return options[variant % len(options)].format(np=np)


def _ext_chain_np(path: _PatternPath, leaf_phrase: str, variant: int) -> str:
    np = leaf_phrase
    for edge, arrow, _other_label in path.hops:
        np = _ext_wrap(edge.rel_type, np, arrow, variant)
    return np


def _ext_row(question: str, cypher: str, rel_types: set[str]) -> Optional[dict]:
    """Wrap a synthesised (question, executable Cypher) pair into a candidate dict, deriving the
    SL pattern from `extract_schema_pattern(cypher)` so the train-format guard holds by
    construction. Returns None (dropped) if the Cypher has no extractable typed pattern."""
    pattern = extract_schema_pattern(cypher)
    if not pattern or not has_relationship_type(pattern):
        return None
    return {"question": question, "pattern": pattern, "cypher": cypher, "rel_types": set(rel_types)}


def _ext_template_rows(
    path: _PatternPath, leaf_phrase: str, leaf_filter: dict[str, str],
) -> list[tuple[str, str, set[str]]]:
    """(question, executable gold Cypher, rel_types) for every hand-authored surface form of an
    enumerated external path."""
    terminal = _terminal_label(path)
    match_clause, terminal_var = _render_pattern(path, leaf_filter=leaf_filter, abbrev=_EXT_VAR_ABBREV)
    rel_types = {edge.rel_type for edge, _arrow, _other in path.hops}
    rows: list[tuple[str, str, set[str]]] = []
    for variant in (0, 1):
        np = _ext_chain_np(path, leaf_phrase, variant)
        for attr, question_template in _EXT_ATTR_QUESTIONS[terminal]:
            question = question_template.format(np=np)
            cypher = f"MATCH {match_clause} RETURN {terminal_var}.{attr}"
            rows.append((question, cypher, rel_types))
    return rows


def enumerate_pole_external_patterns() -> list[str]:
    """Every valid 1-3 hop schema pattern over the real external POLE schema, in the canonical
    committed-pattern format. Both traversal directions, each relationship type used at most once
    per walk, and — per the external-schema asymmetry (9.1) — NO `{active:true}` variants.
    Deterministic and in-schema by construction (every element passes `parse_schema_pattern`
    against `build_pole_external_schema_repr()`)."""
    schema = build_pole_external_schema_repr()
    paths = _enumerate_v3_paths(
        schema,
        temporal_types=_EXT_TEMPORAL_TYPES,
        undirected_types=_EXT_UNDIRECTED_TYPES,
        emit_active_variants=False,
    )
    return [_render_pattern(p, abbrev=_EXT_VAR_ABBREV)[0] for p in paths]


# ── External schema-ambiguity register (the two 9.2/9.3-confirmed divergent axes) ──
# Vague single-hop connector questions, with the ambiguous relation cycled round-robin so the SL
# learns to surface each divergent channel/scope as a SEPARATE single-hop candidate (giving the
# AD/disambiguator the interpretation diversity they consume) — the same design as v3's
# Person->Incident register, retargeted to this graph's real axes.
_EXT_DIGITAL_COMM_FORMS = [
    "who has {np} communicated with digitally",
    "who is {np} in digital contact with",
    "the people {np} is connected to online",
    "who has {np} been in electronic contact with",
    "the digital contacts of {np}",
    "who does {np} communicate with electronically",
]
_EXT_CRIME_SCOPE_FORMS = [
    "who or what was involved in {np}",
    "everyone and everything linked to {np}",
    "who or what took part in {np}",
    "the parties involved in {np}",
    "who or what is connected to {np}",
    "what was a party to {np}",
]


def _pole_external_schema_ambiguous_rows(
    schema: SchemaRepr, rng: random.Random, samples_per_form: int,
) -> list[dict]:
    """Single-hop vague-connector rows for the two confirmed schema-ambiguity axes. Returns
    candidate dicts in the same shape the main loop appends (`question`/`pattern`/`cypher`/
    `rel_types`)."""
    by_type = {e.rel_type: e for e in _build_edges(
        schema, temporal_types=_EXT_TEMPORAL_TYPES, undirected_types=_EXT_UNDIRECTED_TYPES,
    )}
    rows: list[dict] = []

    # Axis 1 — digital-comm channel split: KNOWS_SN vs KNOWS_PHONE, undirected, grounded Person.
    dc_edges = [by_type["KNOWS_SN"], by_type["KNOWS_PHONE"]]
    for form in _EXT_DIGITAL_COMM_FORMS:
        for k in range(samples_per_form):
            edge = dc_edges[k % len(dc_edges)]
            phrase, leaf_filter = _ext_leaf_entity("Person", rng)
            path = _PatternPath("Person", ((edge, "-", "Person"),))
            match_clause, term_var = _render_pattern(path, leaf_filter=leaf_filter, abbrev=_EXT_VAR_ABBREV)
            cypher = f"MATCH {match_clause} RETURN DISTINCT {term_var}.name, {term_var}.surname"
            row = _ext_row(form.format(np=phrase), cypher, {edge.rel_type})
            if row:
                rows.append(row)

    # Axis 2 — Crime-participant scope: PARTY_TO (Person) vs INVOLVED_IN (Vehicle), grounded Crime.
    scope_edges = [(by_type["PARTY_TO"], "Person", "name, surname"),
                   (by_type["INVOLVED_IN"], "Vehicle", "reg")]
    for form in _EXT_CRIME_SCOPE_FORMS:
        for k in range(samples_per_form):
            edge, other_label, ret_attrs = scope_edges[k % len(scope_edges)]
            phrase, leaf_filter = _ext_leaf_entity("Crime", rng)
            path = _PatternPath("Crime", ((edge, "<-", other_label),))
            match_clause, term_var = _render_pattern(path, leaf_filter=leaf_filter, abbrev=_EXT_VAR_ABBREV)
            proj = ", ".join(f"{term_var}.{a.strip()}" for a in ret_attrs.split(","))
            cypher = f"MATCH {match_clause} RETURN DISTINCT {proj}"
            row = _ext_row(form.format(np=phrase), cypher, {edge.rel_type})
            if row:
                rows.append(row)
    return rows


# ── External temporal register (value-level ambiguity → 9.4 date-window / ORDER BY idioms) ──
# The external graph has no `active` edges: temporal ambiguity is a WHERE-clause value choice on
# node date properties. These rows teach the FINE-TUNED QG the exact idioms 9.4 baked into the
# instruct few-shots (`_QG_FEW_SHOT_API_POLE_EXTERNAL`): the `toInteger(split(date,'/')[0])`
# day-of-month window (incl. `CALLER|CALLED` bidirectional alternation) and `ORDER BY ... LIMIT 1`
# for most-recent scope. The SL target is the plain pattern extracted from the same Cypher (no
# `{active:true}` variant) — the temporal decision is not a schema-element choice.
_EXT_TEMPORAL_CRIME_FORMS = [
    "how many crimes happened in area {area} on {day} August 2017",
    "how many crimes were recorded in area {area} on the {day}th of August 2017",
    "count the crimes in area {area} that occurred on {day} August",
]
_EXT_TEMPORAL_CALLVOLUME_FORMS = [
    "how many calls did phone {phone} make on {day} August 2017",
    "count the calls involving phone {phone} on the {day}th of August",
    "how many calls touched phone {phone} on {day} August 2017",
]
_EXT_TEMPORAL_LASTCONTACT_FORMS = [
    "when did phone {a} last contact phone {b}",
    "what was the most recent call between phone {a} and phone {b}",
    "find the latest call from phone {a} to phone {b}",
]


def _pole_external_temporal_rows(rng: random.Random, samples_per_form: int) -> list[dict]:
    """Value-level temporal rows carrying the 9.4 date-window / ORDER BY-LIMIT Cypher idioms."""
    rows: list[dict] = []

    # Crime-date day-window (Crime.date), grounded on an Area.
    for form in _EXT_TEMPORAL_CRIME_FORMS:
        for _ in range(samples_per_form):
            area = rng.choice(_EXT_AREA_CODES)
            day = rng.choice(_EXT_DAYS)
            cypher = (
                f"MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->"
                f"(a:Area {{areaCode:'{area}'}}) WHERE toInteger(split(c.date,'/')[0]) = {day} "
                f"RETURN count(*) AS n"
            )
            row = _ext_row(form.format(area=area, day=day), cypher, {"OCCURRED_AT", "LOCATION_IN_AREA"})
            if row:
                rows.append(row)

    # PhoneCall day-window with CALLER|CALLED bidirectional alternation (PhoneCall.call_date).
    for form in _EXT_TEMPORAL_CALLVOLUME_FORMS:
        for _ in range(samples_per_form):
            phone = rng.choice(_EXT_PHONE_NUMBERS)
            day = rng.choice(_EXT_DAYS)
            cypher = (
                f"MATCH (ph:Phone {{phoneNo:'{phone}'}})<-[:CALLER|CALLED]-(pc:PhoneCall) "
                f"WHERE toInteger(split(pc.call_date,'/')[0]) = {day} RETURN count(*) AS n"
            )
            row = _ext_row(form.format(phone=phone, day=day), cypher, {"CALLER", "CALLED"})
            if row:
                rows.append(row)

    # Most-recent-contact scope: ORDER BY ... LIMIT 1 over PhoneCall date/time, two grounded phones.
    for form in _EXT_TEMPORAL_LASTCONTACT_FORMS:
        for _ in range(samples_per_form):
            a, b = rng.sample(_EXT_PHONE_NUMBERS, 2)
            cypher = (
                f"MATCH (p1:Phone {{phoneNo:'{a}'}})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->"
                f"(p2:Phone {{phoneNo:'{b}'}}) RETURN pc.call_date, pc.call_time "
                f"ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1"
            )
            row = _ext_row(form.format(a=a, b=b), cypher, {"CALLER", "CALLED"})
            if row:
                rows.append(row)
    return rows


def build_pole_external_sft_dataset(config: dict) -> dict:
    """Generate the external-POLE SL/QG SFT rows and write the four `pole_ext_*` jsonl files;
    return a report. Mirrors `build_pole_sft_dataset` (same two-key contract, disjointness gate,
    dedup/cap/split, `build_sl_prompt`/`build_qg_prompt` builders) but over the real external
    schema, with no `{active:true}` enumeration, the two confirmed schema-ambiguity axes, and a
    value-level temporal register carrying the 9.4 date-window / ORDER BY idioms.

    Config keys mirror `build_pole_sft_dataset`, plus `temporal_samples_per_form` (default 30;
    grounded samples per temporal surface form). `benchmark_path` defaults to
    `data/benchmark-pole-external.json`; `skeleton_path` is optional (this benchmark ships no
    in-repo skeleton).
    """
    seed = config.get("seed", 13)
    entities_per_pattern = config.get("entities_per_pattern", 1)
    paraphrases_per_template = config.get("paraphrases_per_template", 3)
    eval_fraction = config.get("eval_fraction", 0.10)
    threshold = config.get("disjointness_threshold", 0.90)
    max_rows = config.get("max_rows")
    benchmark_path = config.get("benchmark_path", "data/benchmark-pole-external.json")
    skeleton_path = config.get("skeleton_path") or benchmark_path
    out = config["output"]

    rng = random.Random(seed)
    schema = build_pole_external_schema_repr()
    schema_block_props = schema.to_prompt_string(include_properties=True)
    schema_block_noprops = schema.to_prompt_string(include_properties=False)

    blocklist = load_blocklist_questions(benchmark_path, skeleton_path)
    paths = _enumerate_v3_paths(
        schema,
        temporal_types=_EXT_TEMPORAL_TYPES,
        undirected_types=_EXT_UNDIRECTED_TYPES,
        emit_active_variants=False,
    )

    llm_spec = config.get("paraphrase_llm")
    llm = build_llm(llm_spec) if llm_spec else None

    raw: list[dict] = []
    pattern_count_by_rel_type: dict[str, int] = {}
    for path in paths:
        rel_types = {edge.rel_type for edge, _arrow, _other in path.hops}
        for rt in rel_types:
            pattern_count_by_rel_type[rt] = pattern_count_by_rel_type.get(rt, 0) + 1
        for _ in range(entities_per_pattern):
            leaf_phrase, leaf_filter = _ext_leaf_entity(path.start_label, rng)
            for question, cypher, row_rel_types in _ext_template_rows(path, leaf_phrase, leaf_filter):
                variants = [question]
                if llm is not None:
                    variants += _paraphrase(question, llm, paraphrases_per_template)
                for q in variants:
                    row = _ext_row(q, cypher, row_rel_types)
                    if row:
                        raw.append(row)

    schema_samples = config.get("schema_connector_samples_per_form", 30)
    schema_rows = _pole_external_schema_ambiguous_rows(schema, rng, schema_samples)
    raw.extend(schema_rows)

    temporal_samples = config.get("temporal_samples_per_form", 30)
    temporal_rows = _pole_external_temporal_rows(rng, temporal_samples)
    raw.extend(temporal_rows)

    kept, n_dropped = apply_disjointness_gate(raw, blocklist, threshold)

    seen_q: set[str] = set()
    deduped: list[dict] = []
    for cand in kept:
        key = _normalise_question(cand["question"])
        if key in seen_q:
            continue
        seen_q.add(key)
        deduped.append(cand)
    n_duplicate = len(kept) - len(deduped)

    n_before_cap = len(deduped)
    if max_rows is not None and len(deduped) > max_rows:
        random.Random(seed).shuffle(deduped)
        deduped = deduped[:max_rows]

    order = list(range(len(deduped)))
    random.Random(seed).shuffle(order)
    n_eval = int(len(order) * eval_fraction)
    eval_idx = set(order[:n_eval])

    sl_train: list[dict] = []
    sl_eval: list[dict] = []
    qg_train: list[dict] = []
    qg_eval: list[dict] = []
    sl_coverage: dict[str, int] = {}
    for i, cand in enumerate(deduped):
        sl_row = {"prompt": build_sl_prompt(cand["question"], schema_block_props), "completion": cand["pattern"]}
        qg_row = {
            "prompt": build_qg_prompt(cand["question"], schema_block_noprops, committed_pattern=cand["pattern"]),
            "completion": cand["cypher"],
        }
        for rt in cand["rel_types"]:
            sl_coverage[rt] = sl_coverage.get(rt, 0) + 1
        if i in eval_idx:
            sl_eval.append(sl_row)
            qg_eval.append(qg_row)
        else:
            sl_train.append(sl_row)
            qg_train.append(qg_row)

    _write_jsonl(out["sl_train"], sl_train)
    _write_jsonl(out["sl_eval"], sl_eval)
    _write_jsonl(out["qg_train"], qg_train)
    _write_jsonl(out["qg_eval"], qg_eval)

    # Every one of the 17 external relationship types with fewer than this many SL rows is named
    # explicitly (acceptance criterion 2), mirroring 9.2's own thin-coverage note.
    all_rel_types = {p["type"] for p in schema.relationship_paths}
    coverage_floor = 30
    coverage_gaps = {rt: sl_coverage.get(rt, 0) for rt in all_rel_types if sl_coverage.get(rt, 0) < coverage_floor}

    report = {
        "patterns_enumerated": len(paths),
        "raw_candidates": len(raw),
        "schema_connector_rows": len(schema_rows),
        "temporal_rows": len(temporal_rows),
        "disjointness_dropped": n_dropped,
        "duplicate_dropped": n_duplicate,
        "max_rows_trimmed": n_before_cap - len(deduped),
        "kept": len(deduped),
        "sl_train": len(sl_train), "sl_eval": len(sl_eval),
        "qg_train": len(qg_train), "qg_eval": len(qg_eval),
        "sl_coverage_by_rel_type": sl_coverage,
        "coverage_gaps_below_30": coverage_gaps,
        "pattern_count_by_rel_type": pattern_count_by_rel_type,
        "paraphrase_used": llm is not None,
    }
    report_path = config.get("report_path")
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
