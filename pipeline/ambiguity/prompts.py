# pipeline/ambiguity/prompts.py
"""Ambiguity Detector prompt templates and shared candidate/entity serialisers."""
from __future__ import annotations

from pipeline.types import CandidateMapping, EntityLookupResult, SchemaElement

# The teaching system prompt: taxonomy + curated POLE schema + 4 few-shot examples.
# The schema section is kept consistent with build_pole_schema_repr (0.3): the same 9 node
# labels and the relationship paths the Schema Linker can emit.
_AD_SYSTEM_HEAD = """\
You are an ambiguity classifier for a police knowledge graph question-answering system.
Your task is to determine whether a natural-language question is ambiguous with respect to
the graph schema, and if so, identify the type of ambiguity.

A question is ambiguous if it could map to more than one structurally different Cypher query,
each returning different results. A question is NOT ambiguous if all reasonable interpretations
lead to the same query result.

The knowledge graph uses a POLE schema (Person, Object, Location, Event/Incident).
Node labels: Person, Incident, Case, Location, Vehicle, Phone, Evidence, Organisation, Communication
Key relationship types:
  (Person)-[:SUSPECTED_OF]->(Incident)
  (Person)-[:WITNESSED]->(Incident)
  (Person)-[:VICTIM_OF]->(Incident)
  (Person)-[:INVESTIGATES]->(Incident)
  (Person)-[:LIVES_AT {active, from_date, to_date}]->(Location)
  (Person)-[:OWNS {active, from_date, to_date}]->(Vehicle)
  (Person)-[:USES_PHONE {active}]->(Phone)
  (Person)-[:WORKS_FOR {active}]->(Organisation)
  (Person)-[:ASSOCIATED_WITH {active, from_date, to_date}]-(Person)
  (Incident)-[:OCCURRED_AT]->(Location)
  (Case)-[:CONTAINS]->(Incident)
  (Evidence)-[:LINKED_TO]->(Person)

## Ambiguity Types
**SCHEMA**: an NL term maps to multiple relationship types / node labels / properties.
  e.g. "connected to" -> SUSPECTED_OF / WITNESSED / VICTIM_OF / INVESTIGATES.
**ENTITY**: a named entity matches more than one node and the question doesn't disambiguate.
  e.g. "incidents linked to James" with two Persons named James.
**INTENT**: the target operation is underspecified; valid readings need different RETURN clauses.
  e.g. "what is the relationship between X and Y" -> the type label / its properties / all paths.
**TEMPORAL**: current vs historical state unspecified, where the schema stores both via
  active/from_date/to_date. e.g. "who owns the vehicle" -> current owner vs all past owners.

## Input You Will Receive
1. The question. 2. The schema candidate distribution (Cypher syntax + normalised scores).
3. Entity lookup results (KG instances matching mentions). 4. A schema ambiguity score and an
entity ambiguity score (0-1) from the candidate-distribution entropy - a signal, not a decision.

## Output Format
Respond with a JSON object ONLY. No preamble.
{"is_ambiguous": true|false, "detected_types": [], "rationale": "..."}
detected_types is a subset of {"schema","entity","intent","temporal"}; empty if not ambiguous.

## Examples
"""

# Four few-shot examples, one per type. The exact wording is authored here (the spec's
# "Pass 4 §5.4" source text is not in the repo); each is faithful to the spec's described
# content and rendered in the same format as build_ad_user_turn + the block serialisers below,
# so the model sees an identical layout at inference time. See decisions-log 2026-06-15.
_AD_FEW_SHOT = """\
### Example 1
Question: Who is connected to the Riverside robbery?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.91 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["schema"], "rationale": "The phrase 'connected to' spreads almost evenly across four different Person->Incident relationship types (high schema score 0.91); each returns a different set of people, so the mapping is schema-ambiguous."}

### Example 2
Question: Show incidents linked to James.

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.82]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.18]

Entity lookup results:
"James" matches:
  1. Person: James Whitfield (PER-007) [match: 0.95]
  2. Person: James Holloway (PER-013) [match: 0.93]

Schema ambiguity score: 0.32 (higher = more spread across candidates)
Entity ambiguity score: 0.99 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["entity"], "rationale": "Two distinct Person nodes (PER-007, PER-013) match 'James' and the question gives nothing to disambiguate them (high entity score 0.99), so the result depends on which James is meant."}

### Example 3
Question: What is the relationship between Alice and the Sesame Street incident?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:WITNESSED]->(Incident)   [score: 0.53]
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.47]

Entity lookup results:
"Alice" matches:
  1. Person: Alice Brennan (PER-022) [match: 0.96]

Schema ambiguity score: 0.40 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["intent"], "rationale": "'the relationship between' is underspecified: even with the entity fixed, valid readings ask for the edge type label, that edge's properties, or every connecting path - each needs a different RETURN clause."}

### Example 4
Question: Who owns the vehicle used in the robbery?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1_temporal candidates:
  (Person)-[:OWNS {active:true}]->(Vehicle)   [score: 0.55]
  (Person)-[:OWNS]->(Vehicle)   [score: 0.45]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.50 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["temporal"], "rationale": "OWNS carries active/from_date/to_date, and the candidates split between the current owner ({active:true}) and all past owners; 'owns' does not say which, so the two readings return different people."}
"""

AD_SYSTEM_PROMPT = _AD_SYSTEM_HEAD + _AD_FEW_SHOT


# ── v3 variant (7.3) ────────────────────────────────────────────────────────────────────
# Same taxonomy/structure/output contract as the v2 head, but the schema block is the concise
# 6-label / 11-relationship v3 schema (build_pole_v3_schema_repr, spec 7.1) and the few-shots
# are re-grounded in v3 seed data (SyntheticPoliceKG-v3.cypher). Selection between v2/v3 happens
# in the condition builders from `dataset_version`; the detector receives it via `system_prompt`.
_AD_SYSTEM_HEAD_V3 = """\
You are an ambiguity classifier for a police knowledge graph question-answering system.
Your task is to determine whether a natural-language question is ambiguous with respect to
the graph schema, and if so, identify the type of ambiguity.

A question is ambiguous if it could map to more than one structurally different Cypher query,
each returning different results. A question is NOT ambiguous if all reasonable interpretations
lead to the same query result.

The knowledge graph uses a concise POLE schema (Person, Object, Location, Event/Incident).
Node labels: Person, Incident, Case, Location, Vehicle, Phone
Relationship types:
  (Person)-[:SUSPECTED_OF]->(Incident)
  (Person)-[:WITNESSED]->(Incident)
  (Person)-[:VICTIM_OF]->(Incident)
  (Person)-[:INVESTIGATES]->(Incident)
  (Case)-[:CONTAINS]->(Incident)
  (Incident)-[:OCCURRED_AT]->(Location)
  (Person)-[:LIVES_AT {active, from_date, to_date}]->(Location)
  (Person)-[:OWNS {active, from_date, to_date}]->(Vehicle)
  (Person)-[:USES_PHONE {active, from_date, to_date}]->(Phone)
  (Phone)-[:CALLED {timestamp}]->(Phone)
  (Person)-[:ASSOCIATED_WITH {active, from_date, to_date}]-(Person)

Roles are expressed ONLY by the four Person->Incident edges (there is no Person.role property),
so a vague "connected to" / "involved with" question is schema-ambiguous across those four edges.

## Ambiguity Types
**SCHEMA**: an NL term maps to multiple relationship types / node labels / properties.
  e.g. "connected to" -> SUSPECTED_OF / WITNESSED / VICTIM_OF / INVESTIGATES.
**ENTITY**: a named entity matches more than one node and the question doesn't disambiguate.
  e.g. "incidents linked to James" with two Persons named James.
**INTENT**: the target operation is underspecified; valid readings need different RETURN clauses.
  e.g. "what is the relationship between X and Y" -> the type label / its properties / all paths.
**TEMPORAL**: current vs historical state unspecified, where the schema stores both via
  active/from_date/to_date. e.g. "who owns the vehicle" -> current owner vs all past owners.

## Input You Will Receive
1. The question. 2. The schema candidate distribution (Cypher syntax + normalised scores).
3. Entity lookup results (KG instances matching mentions). 4. A schema ambiguity score and an
entity ambiguity score (0-1) from the candidate-distribution entropy - a signal, not a decision.

## Output Format
Respond with a JSON object ONLY. No preamble.
{"is_ambiguous": true|false, "detected_types": [], "rationale": "..."}
detected_types is a subset of {"schema","entity","intent","temporal"}; empty if not ambiguous.

## Examples
"""

# Four few-shot examples (one per type), re-grounded in v3 seed data: the Northbridge robbery
# (INC-001, 3 suspects / 2 witnesses / 2 investigators), two Persons named James
# (James Whitfield PER-007, James Kowalski PER-004), David Chen (PER-001, an
# investigator on INC-001), and James Whitfield's OWNS edge to a Holden Commodore
# (VEH-001). Rendered in the same layout as build_ad_user_turn + the block serialisers.
_AD_FEW_SHOT_V3 = """\
### Example 1
Question: Who is connected to the Northbridge robbery?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.34]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.28]
  (Person)-[:VICTIM_OF]->(Incident)   [score: 0.22]
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.16]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.91 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["schema"], "rationale": "The phrase 'connected to' spreads almost evenly across the four Person->Incident role edges (high schema score 0.91); the Northbridge robbery has distinct suspects, witnesses and investigators, so each edge returns a different set of people."}

### Example 2
Question: Show incidents linked to James.

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.81]
  (Person)-[:WITNESSED]->(Incident)   [score: 0.19]

Entity lookup results:
"James" matches:
  1. Person: James Whitfield (PER-007) [match: 0.95]
  2. Person: James Kowalski (PER-004) [match: 0.93]

Schema ambiguity score: 0.31 (higher = more spread across candidates)
Entity ambiguity score: 0.99 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["entity"], "rationale": "Two distinct Person nodes (PER-007, PER-004) match 'James' and the question gives nothing to disambiguate them (high entity score 0.99), so the result depends on which James is meant."}

### Example 3
Question: What is the relationship between David Chen and the Northbridge robbery?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.52]
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.48]

Entity lookup results:
"David Chen" matches:
  1. Person: David Chen (PER-001) [match: 0.97]

Schema ambiguity score: 0.40 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["intent"], "rationale": "'the relationship between' is underspecified: even with the entity fixed, valid readings ask for the edge type label, that edge's properties, or every connecting path - each needs a different RETURN clause."}

### Example 4
Question: Who owns the Holden Commodore?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1_temporal candidates:
  (Person)-[:OWNS {active:true}]->(Vehicle)   [score: 0.55]
  (Person)-[:OWNS]->(Vehicle)   [score: 0.45]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.50 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["temporal"], "rationale": "OWNS carries active/from_date/to_date, and the candidates split between the current owner ({active:true}) and all past owners; 'owns' does not say which, so the two readings return different people."}
"""

AD_SYSTEM_PROMPT_V3 = _AD_SYSTEM_HEAD_V3 + _AD_FEW_SHOT_V3


# ── pole_external variant (9.3) ─────────────────────────────────────────────────────────
# Same taxonomy/output-contract structure as the v3 head, but the schema block is the real
# external POLE schema (build_pole_external_schema_repr, 9.1 audit) and the few-shots are
# re-grounded in real data already on hand from the 9.1/9.2 sessions (no invention needed).
# This graph carries NO dated/state-change relationship properties anywhere (9.1 finding) —
# temporal ambiguity here is a same-day-vs-trailing-week date/time-window mechanism on node
# properties (Crime.date, PhoneCall.call_date/call_time), a DIFFERENT mechanism than v2/v3's
# edge-state (active/from_date/to_date) one; do not conflate the two in the write-up.
_AD_SYSTEM_HEAD_POLE_EXTERNAL = """\
You are an ambiguity classifier for a police knowledge graph question-answering system.
Your task is to determine whether a natural-language question is ambiguous with respect to
the graph schema, and if so, identify the type of ambiguity.

A question is ambiguous if it could map to more than one structurally different Cypher query,
each returning different results. A question is NOT ambiguous if all reasonable interpretations
lead to the same query result.

The knowledge graph is a real external POLE dataset (Person, Object, Location, Event/Crime),
not a designed one.
Node labels: Person, Location, Phone, Email, Officer, PostCode, Area, PhoneCall, Crime, Object, Vehicle
Relationship types:
  (Person)-[:CURRENT_ADDRESS]->(Location)
  (Person)-[:HAS_PHONE]->(Phone)
  (Person)-[:HAS_EMAIL]->(Email)
  (Location)-[:HAS_POSTCODE]->(PostCode)
  (PostCode)-[:POSTCODE_IN_AREA]->(Area)
  (Location)-[:LOCATION_IN_AREA]->(Area)
  (Person)-[:KNOWS_SN]-(Person)
  (Person)-[:KNOWS]-(Person)
  (PhoneCall)-[:CALLER]->(Phone)
  (PhoneCall)-[:CALLED]->(Phone)
  (Person)-[:KNOWS_PHONE]-(Person)
  (Crime)-[:OCCURRED_AT]->(Location)
  (Crime)-[:INVESTIGATED_BY]->(Officer)
  (Vehicle)-[:INVOLVED_IN]->(Crime)   -- Object->Crime also occurs, far rarer (9.1)
  (Person)-[:PARTY_TO]->(Crime)
  (Person)-[:FAMILY_REL {rel_type}]-(Person)
  (Person)-[:KNOWS_LW]-(Person)

This graph has NO dated/state-change relationship properties (unlike v2/v3's active/from_date/
to_date edges) — FAMILY_REL.rel_type is the only relationship property at all. Temporal signal
lives on NODE properties instead: Crime.date, PhoneCall.call_date/call_time.

## Ambiguity Types
**SCHEMA**: an NL term maps to multiple relationship types / node labels / properties. In this
  graph the confirmed axis is the digital-communication channel split: "digital contact" /
  "communicated with digitally" -> KNOWS_SN (social-network) vs KNOWS_PHONE (phone contact),
  which return different, non-overlapping people. Do NOT use a KNOWS-family broad-vs-narrow
  split (e.g. bare KNOWS vs FAMILY_REL) as an ambiguity signal here — every specific KNOWS-family
  edge (KNOWS_SN/KNOWS_PHONE/KNOWS_LW/FAMILY_REL) has a parallel generic KNOWS edge, so a union
  that includes the generic edge returns the same person set regardless of which specific types
  are also included; that mechanism is structurally non-divergent in this graph (9.2 finding).
**ENTITY**: a named entity matches more than one node and the question doesn't disambiguate.
  e.g. two distinct Persons named "Andrea George" (different nhs_no), or "Anne Rice".
**INTENT**: the target operation is underspecified; valid readings need different RETURN clauses.
  e.g. "aside from X" superlative questions with a real tie in the remainder (a count vs a list,
  or which tied record to prefer) — no schema/entity ambiguity, purely what to return.
**TEMPORAL**: which of several readings of an implicit time constraint is meant — either (a) a
  date/time WINDOW is unspecified, e.g. "crimes around 15 August" -> same calendar day vs a
  trailing multi-day window, or (b) the SCOPE of a time-ordered relation is unspecified, e.g.
  "when did phone X last contact phone Y" -> the single most-recent call vs the full call
  history. Both return different, non-overlapping results. This is a DIFFERENT mechanism than
  v2/v3's active/from_date/to_date edge-state ambiguity — there is no `active` property anywhere
  in this graph.

## Input You Will Receive
1. The question. 2. The schema candidate distribution (Cypher syntax + normalised scores).
3. Entity lookup results (KG instances matching mentions). 4. A schema ambiguity score and an
entity ambiguity score (0-1) from the candidate-distribution entropy - a signal, not a decision.

## Output Format
Respond with a JSON object ONLY. No preamble.
{"is_ambiguous": true|false, "detected_types": [], "rationale": "..."}
detected_types is a subset of {"schema","entity","intent","temporal"}; empty if not ambiguous.

## Examples
"""

# Five few-shot examples, grounded in real items already validated in
# data/benchmark-pole-external.json (9.2): Q-POLE-S01 (schema), Q-POLE-E01/E02 (entity),
# Q-POLE-I01 (intent), Q-POLE-T16 (temporal, day-window mechanism), Q-POLE-T05 (temporal,
# most-recent-vs-full-history mechanism — added 9.4, closes the 0% AD recall this mechanism
# had under the original 4 few-shots; see decisions-log 2026-08-06). Rendered in the same
# layout as build_ad_user_turn + the shared block serialisers, so the model sees an
# identical format at inference time.
_AD_FEW_SHOT_POLE_EXTERNAL = """\
### Example 1
Question: Who has Alan Hicks communicated with digitally?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:KNOWS_SN]-(Person)   [score: 0.55]
  (Person)-[:KNOWS_PHONE]-(Person)   [score: 0.45]

Entity lookup results:
"Alan Hicks" matches:
  1. Person: Alan Hicks (312-77-4408) [match: 0.97]

Schema ambiguity score: 0.99 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["schema"], "rationale": "'communicated with digitally' does not say which digital channel: KNOWS_SN (social-network contact, 7 people) and KNOWS_PHONE (phone contact, 1 person) are disjoint edge types returning different, non-overlapping people (high schema score 0.99)."}

### Example 2
Question: What is Andrea George's address?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:CURRENT_ADDRESS]->(Location)   [score: 0.98]

Entity lookup results:
"Andrea George" matches:
  1. Person: Andrea George (800-46-2184) [match: 1.00]
  2. Person: Andrea George (391-46-9135) [match: 1.00]

Schema ambiguity score: 0.02 (higher = more spread across candidates)
Entity ambiguity score: 1.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["entity"], "rationale": "Two distinct Person nodes (nhs_no 800-46-2184 and 391-46-9135) share the identical full name 'Andrea George' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant."}

### Example 3
Question: Which Inspector has investigated the most crimes, aside from Nettles Worthy?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Crime)-[:INVESTIGATED_BY]->(Officer)   [score: 0.94]

Entity lookup results:
"Nettles Worthy" matches:
  1. Officer: Worthy Nettles (70-0643982) [match: 0.92]

Schema ambiguity score: 0.05 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["intent"], "rationale": "Excluding Nettles Worthy (the outright leader) leaves a genuine tie for the remainder (Winonah Skynner and Ricca Miskimmon both n=44); 'aside from X' doesn't say whether to return a single arbitrary top result, a count, or all tied records, and each reading returns a different answer."}

### Example 4
Question: How many crimes happened in area BL1 around 15 August 2017, same-day vs trailing-week?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Crime)-[:OCCURRED_AT]->(Location)   [score: 0.96]
rel_2 candidates:
  (Location)-[:LOCATION_IN_AREA]->(Area)   [score: 0.96]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.04 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["temporal"], "rationale": "'around 15 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 09-15 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state."}

### Example 5
Question: When did phone 9-(776)276-2772 last contact phone 0-(377)507-0388?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (PhoneCall)-[:CALLER]->(Phone)   [score: 0.97]
rel_2 candidates:
  (PhoneCall)-[:CALLED]->(Phone)   [score: 0.97]

Entity lookup results:
No entity ambiguity detected.

Schema ambiguity score: 0.03 (higher = more spread across candidates)
Entity ambiguity score: 0.00 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["temporal"], "rationale": "'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4."}
"""

AD_SYSTEM_PROMPT_POLE_EXTERNAL = _AD_SYSTEM_HEAD_POLE_EXTERNAL + _AD_FEW_SHOT_POLE_EXTERNAL


def _render_element(element: SchemaElement) -> str:
    """Render a SchemaElement for the candidate block.

    relationship_type -> '(Source)-[:TYPE]->(Target)', with a ' {active:true}' filter when the
    temporal active-variant marker is set (SchemaElement.parent == 'active', cf. 3.1). Any other
    element (node label, property) renders as its bare name.
    """
    if element.element_type == "relationship_type":
        src = element.source_label or ""
        tgt = element.target_label or ""
        active = " {active:true}" if element.parent == "active" else ""
        return f"({src})-[:{element.name}{active}]->({tgt})"
    return element.name


def _format_candidate_block(cm: CandidateMapping) -> str:
    """Per slot: '<slot> candidates:' then ranked '(Src)-[:TYPE]->(Tgt)   [score: 0.42]' lines.

    Candidates are already ordered by score descending (CandidateMapping contract). Non-
    relationship elements render as the element name. Returns 'No schema candidates.' if the
    mapping carries no slots.
    """
    if not cm.mentions:
        return "No schema candidates."
    lines: list[str] = []
    for slot, candidates in cm.mentions.items():
        lines.append(f"{slot} candidates:")
        for c in candidates:
            lines.append(f"  {_render_element(c.element)}   [score: {c.score:.2f}]")
    return "\n".join(lines)


def _format_entity_block(el: EntityLookupResult) -> str:
    """Per mention with matches: '"James" matches:' then numbered
    '  1. Person: James Whitfield (PER-007) [match: 0.95]' lines.

    Candidates are already ordered by posterior_score descending (EntityLookupResult contract).
    Returns 'No entity ambiguity detected.' when no mention has any match.
    """
    blocks: list[str] = []
    for mention, candidates in el.entity_mentions.items():
        if not candidates:
            continue
        lines = [f'"{mention}" matches:']
        for i, cand in enumerate(candidates, 1):
            lines.append(
                f"  {i}. {cand.node_label}: {cand.display_name} ({cand.node_id}) "
                f"[match: {cand.match_score:.2f}]"
            )
        blocks.append("\n".join(lines))
    if not blocks:
        return "No entity ambiguity detected."
    return "\n".join(blocks)


def build_ad_user_turn(question: str, candidate_block: str, entity_block: str,
                       schema_entropy: float, entity_entropy: float) -> str:
    return (
        f"Question: {question}\n\n"
        f"Schema candidate distribution (from Schema Linker, beam k=5):\n{candidate_block}\n\n"
        f"Entity lookup results:\n{entity_block}\n\n"
        f"Schema ambiguity score: {schema_entropy:.2f} (higher = more spread across candidates)\n"
        f"Entity ambiguity score: {entity_entropy:.2f} (higher = more matching instances)\n\n"
        f"Classify this question."
    )
