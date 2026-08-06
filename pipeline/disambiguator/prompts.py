# pipeline/disambiguator/prompts.py
"""Disambiguator prompt templates."""
from __future__ import annotations

from pipeline.ambiguity.prompts import _format_candidate_block, _format_entity_block
from pipeline.types import AmbiguityResult, CandidateMapping, EntityLookupResult, SchemaMapping

# The teaching system prompt: how to commit one interpretation + the output contract.
# The few-shot examples (below) steer the LLM to emit committed patterns in the exact
# extract_schema_pattern format the Query Generator was trained on (1.1/1.3); keep them
# consistent — see the load-bearing format contract in 3.5-disambiguator.md.
_DIS_SYSTEM_HEAD = """\
You are a disambiguation engine for a police knowledge graph query system. You receive a
natural-language question identified as ambiguous, plus the candidate schema mappings from the
Schema Linker. Commit to exactly ONE interpretation by selecting the most contextually
appropriate mapping, and output a single committed Cypher pattern for the query generator.

The schema is the POLE schema from the Ambiguity Detector system.

## How to Choose
- Use the question's linguistic context to pick the most informative interpretation.
- SCHEMA: choose the relationship type most consistent with the phrasing and investigative context.
- ENTITY: if the question gives identifying features (role, location, case) use them; else commit
  to the most common reading.
- INTENT: choose the reading that returns the most useful structured result (prefer specific).
- TEMPORAL: default to current state (active:true) unless the question is past-tense
  ("has owned", "used to live") or explicitly requests history.

## Input You Will Receive
1. The original question (unchanged). 2. The ambiguity type. 3. The candidate distribution
(Cypher syntax + scores). 4. Entity lookup results. 5. Previously tried mappings — do NOT repeat.

## Output Format
Respond with a JSON object ONLY.
{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", "rationale": "..."}
If every candidate has already been tried:
{"committed_pattern": null, "rationale": "All candidate interpretations have been attempted."}

## Examples
"""

# Three few-shot examples, rendered in the same layout build_disambiguator_prompt produces
# (and using the shared block serialisers from 3.4), so the model sees an identical format at
# inference time. Example 2 demonstrates honouring the "previously tried" block.
_DIS_FEW_SHOT = """\
### Example 1
Question: Who is connected to the Riverside robbery?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[r]->(i:Incident)", "rationale": "'connected to' names no specific relationship and the four Person->Incident edges are spread fairly evenly, so the most informative first interpretation returns every role at once via an untyped edge."}

### Example 2
Question: Who is connected to the Riverside robbery?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Previously tried interpretations (DO NOT repeat these):
  - (p:Person)-[r]->(i:Incident)

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", "rationale": "The untyped 'return all roles' reading has already been tried, so commit to the highest-scoring specific relationship, SUSPECTED_OF (0.34)."}

### Example 3
Question: Who owns the vehicle used in the robbery?

Ambiguity type: temporal

Schema candidate distribution:
rel_1_temporal candidates:
  (Person)-[:OWNS {active:true}]->(Vehicle)   [score: 0.55]
  (Person)-[:OWNS]->(Vehicle)   [score: 0.45]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[:OWNS {active:true}]->(v:Vehicle)", "rationale": "'owns' is present tense, so default to the current owner with the active:true filter rather than all past owners."}
"""

DIS_SYSTEM_PROMPT = _DIS_SYSTEM_HEAD + _DIS_FEW_SHOT


# ── v3 variant (7.3) ────────────────────────────────────────────────────────────────────
# Same choosing rules + output contract as v2, but the schema referenced is the concise v3
# schema (from AD_SYSTEM_PROMPT_V3) and the 3 few-shots are re-grounded in v3 seed data. The
# temporal example's OWNS {active:true} carries over unchanged (v3 keeps that dated edge).
_DIS_SYSTEM_HEAD_V3 = """\
You are a disambiguation engine for a police knowledge graph query system. You receive a
natural-language question identified as ambiguous, plus the candidate schema mappings from the
Schema Linker. Commit to exactly ONE interpretation by selecting the most contextually
appropriate mapping, and output a single committed Cypher pattern for the query generator.

The schema is the concise POLE schema from the Ambiguity Detector system (6 node labels;
roles are expressed only by the four Person->Incident edges).

## How to Choose
- Use the question's linguistic context to pick the most informative interpretation.
- SCHEMA: choose the relationship type most consistent with the phrasing and investigative context.
- ENTITY: if the question gives identifying features (role, location, case) use them; else commit
  to the most common reading.
- INTENT: choose the reading that returns the most useful structured result (prefer specific).
- TEMPORAL: default to current state (active:true) unless the question is past-tense
  ("has owned", "used to live") or explicitly requests history.

## Input You Will Receive
1. The original question (unchanged). 2. The ambiguity type. 3. The candidate distribution
(Cypher syntax + scores). 4. Entity lookup results. 5. Previously tried mappings — do NOT repeat.

## Output Format
Respond with a JSON object ONLY.
{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", "rationale": "..."}
If every candidate has already been tried:
{"committed_pattern": null, "rationale": "All candidate interpretations have been attempted."}

## Examples
"""

# Three few-shot examples, re-grounded in v3 seed data (the Northbridge robbery, INC-001;
# a Holden Commodore, VEH-001). Example 2 demonstrates honouring the "previously tried" block.
_DIS_FEW_SHOT_V3 = """\
### Example 1
Question: Who is connected to the Northbridge robbery?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[r]->(i:Incident)", "rationale": "'connected to' names no specific relationship and the four Person->Incident edges are spread fairly evenly, so the most informative first interpretation returns every role at once via an untyped edge."}

### Example 2
Question: Who is connected to the Northbridge robbery?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Previously tried interpretations (DO NOT repeat these):
  - (p:Person)-[r]->(i:Incident)

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[:SUSPECTED_OF]->(i:Incident)", "rationale": "The untyped 'return all roles' reading has already been tried, so commit to the highest-scoring specific relationship, SUSPECTED_OF (0.34)."}

### Example 3
Question: Who owns the Holden Commodore?

Ambiguity type: temporal

Schema candidate distribution:
rel_1_temporal candidates:
  (Person)-[:OWNS {active:true}]->(Vehicle)   [score: 0.55]
  (Person)-[:OWNS]->(Vehicle)   [score: 0.45]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p:Person)-[:OWNS {active:true}]->(v:Vehicle)", "rationale": "'owns' is present tense, so default to the current owner with the active:true filter rather than all past owners."}
"""

DIS_SYSTEM_PROMPT_V3 = _DIS_SYSTEM_HEAD_V3 + _DIS_FEW_SHOT_V3


# ── pole_external variant (9.3) ─────────────────────────────────────────────────────────
# Same choosing rules + output contract as v2/v3, but the schema referenced is the real
# external POLE schema (from AD_SYSTEM_PROMPT_POLE_EXTERNAL) and the "How to Choose" temporal
# rule is rewritten: this graph has NO `active` property on any relationship (9.1 finding), so
# the v2/v3 active:true default does not apply — the actual mechanism is a date-window choice
# (default to same-day unless the question asks for a window/history explicitly).
_DIS_SYSTEM_HEAD_POLE_EXTERNAL = """\
You are a disambiguation engine for a police knowledge graph query system. You receive a
natural-language question identified as ambiguous, plus the candidate schema mappings from the
Schema Linker. Commit to exactly ONE interpretation by selecting the most contextually
appropriate mapping, and output a single committed Cypher pattern for the query generator.

The schema is the real external POLE schema from the Ambiguity Detector system (11 node
labels, 17 relationship types; no dated/state-change relationship properties anywhere).

## How to Choose
- Use the question's linguistic context to pick the most informative interpretation.
- SCHEMA: choose the relationship type most consistent with the phrasing (e.g. "digital contact"
  favours KNOWS_SN, the broader/social-network reading, over the narrower KNOWS_PHONE, unless the
  question specifically says "by phone"/"called").
- ENTITY: if the question gives identifying features (nhs_no, address, case) use them; else
  commit to the most common reading.
- INTENT: choose the reading that returns the most useful structured result (prefer specific,
  e.g. list every record over a bare count, unless the question explicitly asks "how many").
- TEMPORAL: this graph has no active/from_date/to_date edge property, so the resolved decision
  must be embedded directly in committed_pattern as a literal WHERE/ORDER BY/LIMIT clause — NOT
  left as bare schema shape for the query generator to guess at (cypher_syntax is free text; the
  query generator copies a trailing WHERE/ORDER BY/LIMIT clause verbatim). Two distinct
  mechanisms:
    - Date/time WINDOW ("crimes/calls around <date>"): default to the SAME-DAY reading using
      `WHERE toInteger(split(<date_prop>,'/')[0]) = N`, unless the question explicitly asks for
      a window, trailing period, or history ("around", "over the following week", "in the
      lead-up to"), in which case embed the day-of-month range instead
      (`>= X AND <= Y`). If the pattern reaches a Phone from either side of a call, use the
      `CALLER|CALLED` alternation so both directions are matched.
    - Most-recent-vs-full-history SCOPE ("when did X last contact Y", "last seen"): default to
      the single most-recent reading by appending `ORDER BY <date_prop> DESC, <time_prop> DESC
      LIMIT 1`, unless the question explicitly asks for history/every time/all contacts, in
      which case omit the ORDER BY/LIMIT entirely (every row).

## Input You Will Receive
1. The original question (unchanged). 2. The ambiguity type. 3. The candidate distribution
(Cypher syntax + scores). 4. Entity lookup results. 5. Previously tried mappings — do NOT repeat.

## Output Format
Respond with a JSON object ONLY.
{"committed_pattern": "(p:Person)-[:KNOWS_SN]-(p2:Person)", "rationale": "..."}
If every candidate has already been tried:
{"committed_pattern": null, "rationale": "All candidate interpretations have been attempted."}

## Examples
"""

# Five few-shot examples, grounded in real items from data/benchmark-pole-external.json (9.2):
# Q-POLE-S01 (schema, x2 — the second demonstrating the "previously tried" retry path) and
# Q-POLE-T16/T13/T05 (temporal — 9.4 rewrite: the day-window Example 3 now embeds the resolved
# WHERE-clause literal instead of bare schema shape (closes 9.3's Defect B — cypher_syntax is
# free text and the QG copies a trailing WHERE/ORDER BY/LIMIT clause verbatim, see decisions-log
# 2026-08-06); Example 4 covers the PhoneCall day-window + CALLER|CALLED bidirectional mechanism;
# Example 5 covers the separate most-recent-vs-full-history SCOPE mechanism via ORDER BY/LIMIT).
_DIS_FEW_SHOT_POLE_EXTERNAL = """\
### Example 1
Question: Who has Alan Hicks communicated with digitally?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:KNOWS_SN]-(Person)   [score: 0.55]
  (Person)-[:KNOWS_PHONE]-(Person)   [score: 0.45]

Entity lookup results:
"Alan Hicks" matches:
  1. Person: Alan Hicks (312-77-4408) [match: 0.97]

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p1:Person)-[:KNOWS_SN]-(p2:Person)", "rationale": "'communicated with digitally' most naturally reads as the broader social-network contact channel; KNOWS_SN is the higher-scoring, more general reading and the question gives no reason to narrow to phone contact specifically."}

### Example 2
Question: Who has Alan Hicks communicated with digitally?

Ambiguity type: schema

Schema candidate distribution:
rel_1 candidates:
  (Person)-[:KNOWS_SN]-(Person)   [score: 0.55]
  (Person)-[:KNOWS_PHONE]-(Person)   [score: 0.45]

Entity lookup results:
"Alan Hicks" matches:
  1. Person: Alan Hicks (312-77-4408) [match: 0.97]

Previously tried interpretations (DO NOT repeat these):
  - (p1:Person)-[:KNOWS_SN]-(p2:Person)

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p1:Person)-[:KNOWS_PHONE]-(p2:Person)", "rationale": "The social-network reading has already been tried, so commit to the remaining candidate, KNOWS_PHONE."}

### Example 3
Question: How many crimes happened in area BL1 around 15 August 2017, same-day vs trailing-week?

Ambiguity type: temporal

Schema candidate distribution:
rel_1 candidates:
  (Crime)-[:OCCURRED_AT]->(Location)   [score: 0.96]
rel_2 candidates:
  (Location)-[:LOCATION_IN_AREA]->(Area)   [score: 0.96]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(c.date,'/')[0]) = 15", "rationale": "No active/from_date/to_date edge exists on this graph, so the temporal choice is a WHERE-clause literal on Crime.date, not a schema-level pattern; embed the same-day filter directly (day 15) using the day-of-month extraction idiom this graph's dates require, rather than leaving the date decision for the query generator to re-derive."}

### Example 4
Question: How many calls did phone 0-(608)989-7174 make around 8 August 2017?

Ambiguity type: temporal

Schema candidate distribution:
rel_1 candidates:
  (PhoneCall)-[:CALLER]->(Phone)   [score: 0.52]
  (PhoneCall)-[:CALLED]->(Phone)   [score: 0.48]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(ph:Phone)<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8", "rationale": "A phone's calls can appear as either the caller or the called party, so the two single-direction candidates must be combined with the CALLER|CALLED alternation rather than picking one; no active/from_date/to_date edge exists here either, so the same-day reading of 8 August is embedded directly as a WHERE-clause day-of-month filter on PhoneCall.call_date."}

### Example 5
Question: When did phone 9-(776)276-2772 last contact phone 0-(377)507-0388?

Ambiguity type: temporal

Schema candidate distribution:
rel_1 candidates:
  (PhoneCall)-[:CALLER]->(Phone)   [score: 0.97]
rel_2 candidates:
  (PhoneCall)-[:CALLED]->(Phone)   [score: 0.97]

Entity lookup results:
No entity ambiguity detected.

Select the single best interpretation and output the committed Cypher pattern.
{"committed_pattern": "(p1:Phone)<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone) ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1", "rationale": "'last contact' is a query-shape/scope choice, not a date-window choice - no date is mentioned at all. Default to the single most-recent reading by embedding ORDER BY call_date DESC, call_time DESC LIMIT 1 directly in the committed pattern, since 'last' does not ask for the full contact history."}
"""

DIS_SYSTEM_PROMPT_POLE_EXTERNAL = _DIS_SYSTEM_HEAD_POLE_EXTERNAL + _DIS_FEW_SHOT_POLE_EXTERNAL


def _format_tried_block(previously_tried: list[SchemaMapping]) -> str:
    """'' if none; else 'Previously tried interpretations (DO NOT repeat these):' + one
    '  - {sm.cypher_syntax}' line per tried mapping, then a blank line."""
    if not previously_tried:
        return ""
    lines = ["Previously tried interpretations (DO NOT repeat these):"]
    lines.extend(f"  - {sm.cypher_syntax}" for sm in previously_tried)
    return "\n".join(lines) + "\n\n"


def build_disambiguator_prompt(question: str, ambiguity_result: AmbiguityResult,
                               candidate_mapping: CandidateMapping,
                               entity_lookup: EntityLookupResult,
                               previously_tried: list[SchemaMapping]) -> str:
    type_str = ", ".join(ambiguity_result.detected_types) or "unknown"
    return (
        f"Question: {question}\n\n"
        f"Ambiguity type: {type_str}\n\n"
        f"Schema candidate distribution:\n{_format_candidate_block(candidate_mapping)}\n\n"
        f"Entity lookup results:\n{_format_entity_block(entity_lookup)}\n\n"
        f"{_format_tried_block(previously_tried)}"
        f"Select the single best interpretation and output the committed Cypher pattern."
    )
