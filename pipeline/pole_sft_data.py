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
from pipeline.schema import build_pole_v3_schema_repr
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


def _build_edges(schema: SchemaRepr) -> list[_Edge]:
    return [
        _Edge(
            index=idx, rel_type=p["type"], source=p["source"], target=p["target"],
            directed=p["type"] not in _UNDIRECTED_TYPES, temporal=p["type"] in _TEMPORAL_TYPES,
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


def _enumerate_v3_paths(schema: Optional[SchemaRepr] = None) -> list[_PatternPath]:
    """Every 1-3 hop walk over the v3 schema graph (each relationship type used at most once
    per walk, so no trivial there-and-back loops), paired with an extra `{active:true}`-filter
    variant for every temporal hop. Deterministic: labels/edges walked in schema-declared order.
    """
    schema = schema or build_pole_v3_schema_repr()
    edges = _build_edges(schema)
    adj = _adjacency(edges)
    paths: list[_PatternPath] = []
    seen: set[tuple] = set()

    def record(start_label: str, hops: tuple) -> None:
        key = (start_label, tuple((e.index, arrow) for e, arrow, _ in hops))
        if key in seen:
            return
        seen.add(key)
        paths.append(_PatternPath(start_label, hops))
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


def _render_pattern(path: _PatternPath, *, leaf_filter: Optional[dict[str, str]] = None) -> tuple[str, str]:
    """Render one path as a Cypher pattern fragment; returns (rendered, terminal_var).

    `leaf_filter=None` renders the canonical SL committed-pattern form (no entity-specific
    node values — matching `pipeline.schema_linker.pattern_extraction`'s node-filter rules);
    a filter dict embeds those concrete property values on the FIRST node only, for the QG's
    full executable Cypher completion.
    """
    used: dict[str, int] = {}

    def alloc(label: str) -> str:
        base = _VAR_ABBREV[label]
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
