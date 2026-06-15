# pipeline/entity_lookup/span_extractor.py
"""Rule-based extraction of entity mention spans from a question (no NER model)."""
from __future__ import annotations

import re

# Known limitation (flag): span extraction is heuristic regex, not learned NER. It can miss
# lowercased or unusual mentions and over-extract generic capitalised words. The entity_lookup
# threshold + the >max-candidates warning bound the damage. If recall on entity-ambiguous
# benchmark questions is poor, this is the place to improve (record in decisions-log.md).

# Perth suburbs that may appear in SyntheticPoliceKG Location values. Used case-insensitively
# as a safety net for the (otherwise capitalisation-dependent) proper-noun rules.
_KNOWN_SUBURBS: set[str] = {
    "Northbridge", "Fremantle", "Subiaco", "Joondalup", "Armadale", "Midland",
    "Cannington", "Mirrabooka", "Cottesloe", "Scarborough", "Rockingham", "Mandurah",
    "Victoria Park", "Mount Lawley", "Leederville", "Nedlands", "Claremont", "Bassendean",
    "Bayswater", "Morley", "Balga", "Gosnells", "Kalamunda", "Wanneroo", "Belmont",
    "Cockburn", "Kwinana", "Melville", "Stirling", "Vincent", "Wembley", "Maylands",
    "Osborne Park", "Balcatta", "Innaloo", "Karawara", "Como", "Applecross",
}

# (1) "Operation X" / "Operation X Y" patterns
_OPERATION_RE = re.compile(r"\bOperation\s+[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\b")
# (2) multi-word proper nouns (≥2 consecutive Capitalised words)
_MULTIWORD_PROPER_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
# (3) single capitalised words
_SINGLE_PROPER_RE = re.compile(r"\b[A-Z][a-z]+\b")
# (4) quoted strings (single or double quotes)
_QUOTED_RE = re.compile(r"\"([^\"]+)\"|'([^']+)'")


def _is_subspan(short: str, long: str) -> bool:
    """True if `short` appears as a whole-word substring of `long` (case-insensitive)."""
    if short.lower() == long.lower():
        return False
    return re.search(rf"\b{re.escape(short.lower())}\b", long.lower()) is not None


def extract_entity_spans(question: str) -> list[str]:
    """Deduplicated mention strings, longest-first (prefer 'James Whitfield' over 'James').

    Merges: (1) 'Operation X' patterns; (2) multi-word proper nouns; (3) single capitalised
    words excluding the question's first word; (4) quoted strings; (5) known Perth suburbs
    (case-insensitive). Single-word spans contained within a retained longer span are dropped.
    """
    spans: list[str] = []

    spans += _OPERATION_RE.findall(question)
    spans += _MULTIWORD_PROPER_RE.findall(question)

    # (3) single capitalised words — exclude the leading question word.
    stripped = question.lstrip()
    for m in _SINGLE_PROPER_RE.finditer(stripped):
        if m.start() == 0:
            continue
        spans.append(m.group())

    # (4) quoted strings
    for double, single in _QUOTED_RE.findall(question):
        match = double or single
        if match.strip():
            spans.append(match.strip())

    # (5) known suburbs (case-insensitive presence in the question)
    lowered = question.lower()
    for suburb in _KNOWN_SUBURBS:
        if re.search(rf"\b{re.escape(suburb.lower())}\b", lowered):
            spans.append(suburb)

    # Dedup (case-insensitive), then longest-first, dropping word-subsets of longer spans.
    seen: set[str] = set()
    unique: list[str] = []
    for s in spans:
        s = s.strip()
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            unique.append(s)
    unique.sort(key=len, reverse=True)

    result: list[str] = []
    for s in unique:
        if any(_is_subspan(s, kept) for kept in result):
            continue
        result.append(s)
    return result
