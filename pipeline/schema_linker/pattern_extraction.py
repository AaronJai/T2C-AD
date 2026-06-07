# pipeline/schema_linker/pattern_extraction.py
"""Extract the schema pattern (value-stripped MATCH skeleton) from gold Cypher.

Defines the canonical committed-pattern format used by SL training (1.2), QG training
(1.3), and — by contract — by every inference-time producer of SchemaMapping.cypher_syntax.

The output style is: ``variable:Label`` nodes, ``-[:TYPE]->`` directed (and ``-[:TYPE]-``
undirected) relationships, property-name-only filters, and boolean property values
retained. This must stay aligned with ``pipeline.types._build_cypher_pattern`` (0.1) and
the Disambiguator serialisation (3.5), or the QG sees an unfamiliar pattern format.
"""
from __future__ import annotations

from typing import Optional

# Brackets that open/close a Cypher pattern grouping. Used for depth-aware scanning so
# that delimiters (commas, colons, braces) inside nested groups or strings are ignored.
_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")", "]", "}"}

# Top-level clause keywords. Anything after a MATCH up to the next of these (at bracket
# depth 0, outside string literals) is the MATCH body. Longer phrases are matched first.
_CLAUSE_KEYWORDS = [
    "OPTIONAL MATCH", "DETACH DELETE", "ORDER BY", "UNION ALL",
    "MATCH", "WHERE", "RETURN", "WITH", "CREATE", "MERGE", "SET",
    "DELETE", "REMOVE", "LIMIT", "SKIP", "UNION", "UNWIND", "CALL", "FOREACH",
]
_MATCH_KEYWORDS = {"MATCH", "OPTIONAL MATCH"}


def extract_schema_pattern(cypher: str) -> Optional[str]:
    """Return the schema pattern, or None on parse failure (row excluded from training).

    Strategy: isolate the MATCH clause(s) with a depth-aware scanner, strip non-boolean
    property values and entity-specific node maps per the rules, and reconstruct the
    pattern in standard Cypher syntax. A targeted MATCH-clause parser is used rather than
    CyVer's validators: CyVer's SyntaxValidator requires a *live* Neo4j driver (it issues
    EXPLAIN against the DB), which is unavailable at this phase, so it cannot serve as an
    offline parser. The final CyVer SyntaxValidator pass is applied later by the caller
    (1.2 / 1.3) as part of row filtering.

    Rules (see spec 1.1):
      - Node labels, relationship types, and relationship direction kept as-is.
      - On *relationships*: every property name is kept; boolean values are retained
        (``{active:true}``), all other values are stripped to the name (``{from_date}``).
      - On *nodes*: only boolean property entries are kept; string/int entries are
        dropped, and if nothing remains the whole map is dropped (label only).
      - WHERE / RETURN / WITH / ORDER BY / LIMIT / SKIP are dropped entirely.
      - Multiple MATCH clauses are newline-joined; multiple paths in one clause are
        comma-joined. Undirected edges keep their undirected form.

    Returns None when: there is no MATCH clause, brackets are unbalanced, or the
    reconstructed pattern is empty. Never raises.
    """
    if not cypher or not cypher.strip():
        return None
    try:
        bodies = _match_clause_bodies(cypher)
        if not bodies:
            return None
        clause_patterns: list[str] = []
        for body in bodies:
            paths = [p.strip() for p in _split_top_level(body, ",")]
            rewritten = [_rewrite_path(p) for p in paths if p]
            if rewritten:
                clause_patterns.append(", ".join(rewritten))
        pattern = "\n".join(cp for cp in clause_patterns if cp).strip()
        return pattern or None
    except (ValueError, IndexError):
        return None


def has_relationship_type(pattern: str) -> bool:
    """True if the pattern contains at least one *typed* relationship (``[...:TYPE...]``).

    The relationship-type filter predicate used by 1.2 / 1.3: a row whose extracted
    pattern has no relationship type does not exercise relationship schema linking and is
    excluded from training. Lives here so extraction and its filter share one definition.
    """
    if not pattern:
        return False
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i] == "[":
            close = _matching_index(pattern, i)
            relspec = pattern[i + 1:close].split("{", 1)[0]
            if ":" in relspec:
                return True
            i = close + 1
        else:
            i += 1
    return False


# ── MATCH-clause isolation ──────────────────────────────────────────────────────
def _match_clause_bodies(query: str) -> list[str]:
    """Return the body text of each MATCH / OPTIONAL MATCH clause, in order."""
    keywords = sorted(_CLAUSE_KEYWORDS, key=len, reverse=True)
    upper = query.upper()
    n = len(query)
    i = 0
    depth = 0
    in_str: Optional[str] = None
    cur_is_match = False
    body_start: Optional[int] = None
    bodies: list[str] = []
    while i < n:
        c = query[i]
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in "'\"":
            in_str = c
            i += 1
            continue
        if c in _OPEN:
            depth += 1
            i += 1
            continue
        if c in _CLOSE:
            depth -= 1
            i += 1
            continue
        if depth == 0:
            matched = None
            for kw in keywords:
                length = len(kw)
                if upper[i:i + length] == kw:
                    before = query[i - 1] if i > 0 else ""
                    after = query[i + length] if i + length < n else ""
                    if not _is_word_char(before) and not _is_word_char(after):
                        matched = kw
                        break
            if matched is not None:
                if cur_is_match and body_start is not None:
                    bodies.append(query[body_start:i])
                cur_is_match = matched in _MATCH_KEYWORDS
                i += len(matched)
                body_start = i
                continue
        i += 1
    if cur_is_match and body_start is not None:
        bodies.append(query[body_start:])
    return bodies


# ── Path / node / relationship rewriting ────────────────────────────────────────
def _rewrite_path(path: str) -> str:
    """Rewrite one path pattern (alternating nodes and relationships)."""
    out: list[str] = []
    for kind, text in _tokenize_path(path):
        out.append(_rewrite_node(text) if kind == "node" else _rewrite_rel(text))
    return "".join(out)


def _tokenize_path(path: str) -> list[tuple[str, str]]:
    """Split a path into ('node', '(...)') and ('rel', '<-[...]->') tokens."""
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
        # Relationship connector: read until the next top-level '(' (start of a node),
        # honouring brackets and string literals so '(' inside a property value is safe.
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


def _rewrite_node(token: str) -> str:
    """Rewrite a node token, keeping only boolean property entries."""
    inner = token[1:-1]
    brace = _find_top_level(inner, "{")
    if brace is None:
        return "(" + inner.strip() + ")"
    prefix = inner[:brace].strip()
    close = _matching_index(inner, brace)
    kept = [(name, value) for name, value, is_bool in _parse_map(inner[brace + 1:close]) if is_bool]
    if kept:
        body = ", ".join(f"{name}:{value.lower()}" for name, value in kept)
        return f"({prefix} {{{body}}})"
    return f"({prefix})"


def _rewrite_rel(token: str) -> str:
    """Rewrite a relationship connector, preserving direction; keep all property names."""
    s = token.strip()
    left = "<-" if s.startswith("<") else "-"
    right = "->" if s.endswith(">") else "-"
    brace_open = _find_top_level(s, "[")
    if brace_open is None:
        return left + right
    close = _matching_index(s, brace_open)
    content = s[brace_open + 1:close]
    map_open = _find_top_level(content, "{")
    if map_open is None:
        return f"{left}[{content.strip()}]{right}"
    relspec = content[:map_open].strip()
    map_close = _matching_index(content, map_open)
    parts: list[str] = []
    for name, value, is_bool in _parse_map(content[map_open + 1:map_close]):
        parts.append(f"{name}:{value.lower()}" if is_bool else name)
    mapout = (" {" + ", ".join(parts) + "}") if parts else ""
    return f"{left}[{relspec}{mapout}]{right}"


def _parse_map(content: str) -> list[tuple[str, str, bool]]:
    """Parse a property-map body into (name, value, is_boolean) entries."""
    entries: list[tuple[str, str, bool]] = []
    for part in _split_top_level(content, ","):
        part = part.strip()
        if not part:
            continue
        colon = _find_top_level(part, ":")
        if colon is None:
            name, value = part, ""
        else:
            name, value = part[:colon].strip(), part[colon + 1:].strip()
        is_bool = value.lower() in ("true", "false")
        entries.append((name, value, is_bool))
    return entries


# ── Depth-aware scanning primitives ─────────────────────────────────────────────
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


def _is_word_char(c: str) -> bool:
    return c.isalnum() or c == "_"
