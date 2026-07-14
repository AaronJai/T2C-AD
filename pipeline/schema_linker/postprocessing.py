# pipeline/schema_linker/postprocessing.py
"""Transform k beam completions into a CandidateMapping (the novel step)."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

from pipeline.llm import Completion
from pipeline.schema_linker.inference import extract_pattern_from_completion
from pipeline.types import CandidateMapping, SchemaCandidate, SchemaElement, SchemaRepr


@dataclass
class ParsedPattern:
    raw_text: str
    nodes: list[tuple]          # [(alias, label), ...]
    relationships: list[tuple]  # [(src_alias, type, tgt_alias, direction, props), ...]
    is_valid: bool              # False if unparseable OR uses labels/rels not in schema
    score: float                # the beam's log-prob (from Completion.score)


def parse_schema_pattern(pattern_text: str, schema: SchemaRepr, score: float) -> ParsedPattern:
    """Parse a Cypher pattern fragment into nodes/relationships and validate against schema.
    is_valid=False when: unparseable, a node label ∉ schema.node_labels, or a relationship
    type ∉ {p['type'] for p in schema.relationship_paths}. Property filters (incl. {active:true})
    are captured in the relationship/node `props`.

    The dangling committed-pattern filter-suffix marker (a trailing bare ``--`` with nothing
    after it, cf. decisions-log 2026-06-15) is ignored: an edge with no target node produces no
    relationship, so it never blocks an otherwise schema-correct beam from matching gold.
    """
    valid_labels = set(schema.node_labels)
    valid_rels = {p["type"] for p in schema.relationship_paths}

    nodes: list[tuple] = []
    relationships: list[tuple] = []
    try:
        anon = 0
        for fragment in _split_top_level(pattern_text, ","):
            tokens = _tokenize_path(fragment)
            # Resolve node/relationship adjacency within the fragment positionally.
            prev_alias: Optional[str] = None
            pending_rel: Optional[tuple] = None  # (type, direction, props) awaiting a target
            for kind, text in tokens:
                if kind == "node":
                    alias, label, props = _parse_node(text)
                    if label is None and alias and alias in valid_labels:
                        # Colon-less label repair (8.1): an instruct model writes `(Person)`
                        # (no label colon), which parses as a variable name → the label is
                        # lost. When the bare alias is an EXACT case-sensitive match for a
                        # schema label, treat it as the label and leave the node anonymous.
                        # Real aliases ((p), (x)) don't match a schema label, so are untouched.
                        label = alias
                        alias = ""
                    if not alias:
                        alias = f"_n{anon}"
                        anon += 1
                    nodes.append((alias, label))
                    if props:
                        # node property filters are tracked but unused downstream for now
                        pass
                    if pending_rel is not None and prev_alias is not None:
                        rtype, direction, rprops = pending_rel
                        relationships.append((prev_alias, rtype, alias, direction, rprops))
                    pending_rel = None
                    prev_alias = alias
                else:  # relationship connector
                    pending_rel = _parse_rel(text)
            # a trailing connector with no following node (the bare `--` suffix) is dropped
    except (ValueError, IndexError):
        return ParsedPattern(pattern_text, [], [], False, score)

    is_valid = bool(nodes or relationships)
    for _alias, label in nodes:
        if label and label not in valid_labels:
            is_valid = False
    for _src, rtype, _tgt, _dir, _props in relationships:
        if rtype is None or rtype not in valid_rels:
            is_valid = False

    return ParsedPattern(pattern_text, nodes, relationships, is_valid, score)


def align_beam_candidates(parsed: list[ParsedPattern]) -> dict[str, list[tuple[SchemaElement, float]]]:
    """Find positions that VARY across valid beams → candidate slots.

    Algorithm:
      1. Establish the common structural skeleton across valid beams (positions where the
         label/rel-type is identical in every beam).
      2. Positions that differ → candidate slots, keyed positionally:
         relationships → "rel_1", "rel_2", … (in hop order); nodes → "node_1", ….
      3. For each slot, collect the distinct SchemaElements seen and SUM the log-scores of the
         beams exhibiting each (merging duplicate beams in log-space).
      4. Temporal variant rule: if some beams carry {active:true} on a relationship and others
         don't, that is a SEPARATE slot keyed "rel_{n}_temporal" — same rel type, differing
         property filter. (Detected as relationship_type with/without the active property.)

    Returns {slot_key: [(SchemaElement, summed_log_score), ...]} (unordered scores; normalised next).
    """
    out: dict[str, list[tuple[SchemaElement, float]]] = {}

    # ── Relationship positions (in hop order) ──────────────────────────────────
    max_rels = max((len(p.relationships) for p in parsed), default=0)
    for i in range(max_rels):
        contributors = []  # (parsed, element, active_bool)
        for p in parsed:
            if i < len(p.relationships):
                alias_to_label = {a: l for a, l in p.nodes}
                src, rtype, tgt, direction, props = p.relationships[i]
                element = _rel_element(src, rtype, tgt, direction, alias_to_label, active=False)
                contributors.append((p, element, _has_active(props)))
        if not contributors:
            continue
        keys = {_element_key(el) for _, el, _ in contributors}
        if len(keys) > 1:
            # The relationship TYPE/triple varies → a type-level candidate slot.
            groups: dict[tuple, tuple[SchemaElement, list[float]]] = {}
            for p, el, _ in contributors:
                key = _element_key(el)
                groups.setdefault(key, (el, []))[1].append(p.score)
            out[f"rel_{i + 1}"] = [(el, _logsumexp(scores)) for el, scores in groups.values()]
        else:
            # Same triple in every beam — check the temporal (active-filter) variant rule.
            actives = {active for _, _, active in contributors}
            if len(actives) > 1:
                template = contributors[0][1]
                scores_by_active: dict[bool, list[float]] = {True: [], False: []}
                for p, _, active in contributors:
                    scores_by_active[active].append(p.score)
                slot = [
                    (replace(template, parent="active" if active else None), _logsumexp(scores))
                    for active, scores in scores_by_active.items()
                    if scores
                ]
                out[f"rel_{i + 1}_temporal"] = slot
            # else: skeleton position (all beams agree) → not a candidate slot

    # ── Node positions ─────────────────────────────────────────────────────────
    max_nodes = max((len(p.nodes) for p in parsed), default=0)
    for i in range(max_nodes):
        contributors_n = []  # (parsed, label)
        for p in parsed:
            if i < len(p.nodes):
                _alias, label = p.nodes[i]
                if label:
                    contributors_n.append((p, label))
        if not contributors_n:
            continue
        labels = {label for _, label in contributors_n}
        if len(labels) > 1:
            groups_n: dict[str, list[float]] = {}
            for p, label in contributors_n:
                groups_n.setdefault(label, []).append(p.score)
            out[f"node_{i + 1}"] = [
                (SchemaElement(element_type="node_label", name=label), _logsumexp(scores))
                for label, scores in groups_n.items()
            ]

    return out


def normalise_candidate_scores(
    raw: dict[str, list[tuple[SchemaElement, float]]],
) -> dict[str, list[SchemaCandidate]]:
    """Softmax each slot's log-scores into probabilities; emit SchemaCandidate lists ordered
    by score desc with beam_rank assigned. Uses log-sum-exp for stability."""
    def logsumexp(xs: list[float]) -> float:
        m = max(xs)
        return m + math.log(sum(math.exp(x - m) for x in xs))

    out: dict[str, list[SchemaCandidate]] = {}
    for key, cands in raw.items():
        lse = logsumexp([s for _, s in cands])
        ranked = sorted(
            (SchemaCandidate(element=el, score=math.exp(s - lse), beam_rank=0) for el, s in cands),
            key=lambda c: c.score, reverse=True,
        )
        for i, c in enumerate(ranked, 1):
            c.beam_rank = i
        out[key] = ranked
    return out


def build_candidate_mapping(question: str, completions: list[Completion],
                            schema: SchemaRepr, min_valid_beams: int = 1) -> CandidateMapping:
    """completions → CandidateMapping.

    1. Parse each completion (text, score) → ParsedPattern (extract_pattern_from_completion first).
    2. Drop invalid beams. If fewer than min_valid_beams remain, raise SchemaLinkerError.
    3. If all valid beams are the SAME pattern (no varying slot): single-candidate mapping —
       one slot per element, score 1.0. This yields ~0 entropy downstream (confident/unambiguous).
    4. Else: align_beam_candidates → normalise_candidate_scores → mentions.
    5. CandidateMapping(question, mentions, beam_k=len(completions)).

    min_valid_beams is forwarded from SchemaLinker (see spec note: "the caller (linker) decides").
    It is a keyword with default 1 so the spec's 3-arg signature still works unchanged; the
    linker passes its configured value. See decisions-log 2026-06-15.
    """
    parsed = [
        parse_schema_pattern(extract_pattern_from_completion(c.text), schema, c.score)
        for c in completions
    ]
    valid = [p for p in parsed if p.is_valid]
    if len(valid) < min_valid_beams:
        from pipeline.schema_linker.linker import SchemaLinkerError
        raise SchemaLinkerError(
            f"Only {len(valid)} parseable in-schema beam(s) among {len(completions)} "
            f"completions; need >= {min_valid_beams}."
        )

    raw = align_beam_candidates(valid)
    if not raw:
        mentions = _single_candidate_mentions(valid[0])
    else:
        mentions = normalise_candidate_scores(raw)
    return CandidateMapping(question=question, mentions=mentions, beam_k=len(completions))


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _single_candidate_mentions(parsed: ParsedPattern) -> dict[str, list[SchemaCandidate]]:
    """All beams agree → one slot per element, each a single candidate with score 1.0."""
    alias_to_label = {a: l for a, l in parsed.nodes}
    mentions: dict[str, list[SchemaCandidate]] = {}
    for i, (src, rtype, tgt, direction, _props) in enumerate(parsed.relationships, 1):
        element = _rel_element(src, rtype, tgt, direction, alias_to_label, active=False)
        mentions[f"rel_{i}"] = [SchemaCandidate(element=element, score=1.0, beam_rank=1)]
    for i, (_alias, label) in enumerate(parsed.nodes, 1):
        if label:
            mentions[f"node_{i}"] = [
                SchemaCandidate(
                    element=SchemaElement(element_type="node_label", name=label),
                    score=1.0, beam_rank=1,
                )
            ]
    return mentions


def _rel_element(src_alias: str, rtype: Optional[str], tgt_alias: str, direction: str,
                 alias_to_label: dict[str, str], active: bool) -> SchemaElement:
    """Build a relationship_type SchemaElement, oriented by arrow direction.

    For ``<-`` the schema source is the right-hand node. The active-filter temporal marker is
    carried on `parent` ("active" vs None) so two otherwise-identical relationship elements
    remain distinct (see decisions-log 2026-06-15)."""
    left = alias_to_label.get(src_alias)
    right = alias_to_label.get(tgt_alias)
    if direction == "<-":
        source_label, target_label = right, left
    else:
        source_label, target_label = left, right
    return SchemaElement(
        element_type="relationship_type",
        name=rtype,
        source_label=source_label,
        target_label=target_label,
        parent="active" if active else None,
    )


def _element_key(element: SchemaElement) -> tuple:
    return (element.name, element.source_label, element.target_label)


def _has_active(props: dict[str, str]) -> bool:
    return any(name.lower() == "active" for name in props)


def _logsumexp(xs: list[float]) -> float:
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


# ── Depth-aware Cypher-fragment tokenising ───────────────────────────────────────
_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")", "]", "}"}


def _tokenize_path(path: str) -> list[tuple[str, str]]:
    """Split one path fragment into ('node', '(...)') and ('rel', '<-[...]->') tokens."""
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(path)
    while i < n:
        c = path[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            j = _matching_index(path, i)
            tokens.append(("node", path[i:j + 1]))
            i = j + 1
            continue
        # Relationship connector: read until the next top-level '(' (start of a node).
        start = i
        depth = 0
        in_str: Optional[str] = None
        while i < n:
            ch = path[i]
            if in_str is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch in "'\"":
                in_str = ch
            elif ch == "(" and depth == 0:
                break
            elif ch in _OPEN:
                depth += 1
            elif ch in _CLOSE:
                depth -= 1
            i += 1
        tokens.append(("rel", path[start:i]))
    return tokens


def _parse_node(token: str) -> tuple[str, Optional[str], dict[str, str]]:
    """Parse ``(alias:Label {props})`` → (alias, label, props). Missing parts → "" / None / {}."""
    inner = token[1:-1]
    brace = _find_top_level(inner, "{")
    props: dict[str, str] = {}
    if brace is not None:
        close = _matching_index(inner, brace)
        props = _parse_props(inner[brace + 1:close])
        inner = inner[:brace]
    inner = inner.strip()
    colon = _find_top_level(inner, ":")
    if colon is None:
        return inner.strip(), None, props
    alias = inner[:colon].strip()
    label = inner[colon + 1:].strip() or None
    return alias, label, props


def _parse_rel(token: str) -> tuple[Optional[str], str, dict[str, str]]:
    """Parse a relationship connector → (type, direction, props). type is None if untyped."""
    s = token.strip()
    direction = "->" if s.endswith(">") else ("<-" if s.startswith("<") else "--")
    props: dict[str, str] = {}
    rtype: Optional[str] = None
    open_b = _find_top_level(s, "[")
    if open_b is not None:
        close_b = _matching_index(s, open_b)
        content = s[open_b + 1:close_b]
        map_open = _find_top_level(content, "{")
        if map_open is not None:
            map_close = _matching_index(content, map_open)
            props = _parse_props(content[map_open + 1:map_close])
            content = content[:map_open]
        relspec = content.strip()
        colon = _find_top_level(relspec, ":")
        if colon is not None:
            rtype = relspec[colon + 1:].strip() or None
    return rtype, direction, props


def _parse_props(content: str) -> dict[str, str]:
    """Parse a property-map body into {name: value} (value "" when name-only)."""
    out: dict[str, str] = {}
    for part in _split_top_level(content, ","):
        part = part.strip()
        if not part:
            continue
        colon = _find_top_level(part, ":")
        if colon is None:
            out[part] = ""
        else:
            out[part[:colon].strip()] = part[colon + 1:].strip()
    return out


def _matching_index(s: str, start: int) -> int:
    """Index of the bracket matching s[start]; raises ValueError if unbalanced."""
    depth = 0
    in_str: Optional[str] = None
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"":
            in_str = c
        elif c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced brackets")


def _split_top_level(s: str, delim: str) -> list[str]:
    """Split s on delim at bracket depth 0, outside string literals."""
    parts: list[str] = []
    depth = 0
    in_str: Optional[str] = None
    start = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"":
            in_str = c
        elif c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth -= 1
        elif c == delim and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


def _find_top_level(s: str, char: str) -> Optional[int]:
    """Index of the first char at bracket depth 0 outside strings, or None."""
    depth = 0
    in_str: Optional[str] = None
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"":
            in_str = c
        elif c == char and depth == 0:
            return i
        elif c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth -= 1
        i += 1
    return None
