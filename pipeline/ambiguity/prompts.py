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
# (INC-V3-001, 3 suspects / 2 witnesses / 2 investigators), two Persons named James
# (James Whitfield PER-V3-007, James Kowalski PER-V3-004), David Chen (PER-V3-001, an
# investigator on INC-V3-001), and James Whitfield's OWNS edge to a Holden Commodore
# (VEH-V3-001). Rendered in the same layout as build_ad_user_turn + the block serialisers.
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
  1. Person: James Whitfield (PER-V3-007) [match: 0.95]
  2. Person: James Kowalski (PER-V3-004) [match: 0.93]

Schema ambiguity score: 0.31 (higher = more spread across candidates)
Entity ambiguity score: 0.99 (higher = more matching instances)

Classify this question.
{"is_ambiguous": true, "detected_types": ["entity"], "rationale": "Two distinct Person nodes (PER-V3-007, PER-V3-004) match 'James' and the question gives nothing to disambiguate them (high entity score 0.99), so the result depends on which James is meant."}

### Example 3
Question: What is the relationship between David Chen and the Northbridge robbery?

Schema candidate distribution (from Schema Linker, beam k=5):
rel_1 candidates:
  (Person)-[:INVESTIGATES]->(Incident)   [score: 0.52]
  (Person)-[:SUSPECTED_OF]->(Incident)   [score: 0.48]

Entity lookup results:
"David Chen" matches:
  1. Person: David Chen (PER-V3-001) [match: 0.97]

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
