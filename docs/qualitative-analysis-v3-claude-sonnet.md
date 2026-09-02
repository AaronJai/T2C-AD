# T2C-AD Qualitative Analysis — v3 Substrate, Claude Sonnet 4.6, C2 vs C3 (per-question)

*Author: Aaron Tan · Run: local Neo4j Desktop (`neo4j://127.0.0.1:7687`, database `policev3`),
2026-07-27 — Kaya in maintenance, so this is a companion run, not the canonical Kaya job
(`results/metrics_claude-sonnet_v3.json`, job 1061343). Aggregate numbers on this run
(EX 39.2/54.2 C2/C3) track the canonical ones (37.5/52.5) closely but are not guaranteed
byte-identical — the API Schema Linker uses temperature sampling. Source: `results/qual_records_claude-sonnet_v3_localdb.json`
(per-question detail, 120 items × {C2, C3}) via `experiments/analyze_qualitative.py`; full
case-study dump in `results/qualitative_analysis_claude-sonnet_v3_localdb.md`. Illustrative
pipeline step-through diagrams for two of the cases below: [Q-105, temporal](diagram-q105-temporal-stepthrough.svg)
and [Q-041, schema](diagram-q041-schema-stepthrough.svg). All 80 ambiguous questions, colour-coded
green/red by condition: [EX](qual-comparison-tables-v3-claude-sonnet.docx) (0 regressions) and
[EA](qual-comparison-tables-v3-claude-sonnet-ea.docx) (1 regression, Q-104 — see decisions-log 2026-07-28).*

This companion to [`results-walkthrough-v3-claude-sonnet.md`](results-walkthrough-v3-claude-sonnet.md)
answers the question the aggregate metrics can't: **is the disambiguation module (C3) resolving
real ambiguity, or is its EX/EA lift over the schema-grounded baseline (C2) just noise from C3's
larger retry budget?** Method: join C2 and C3 by `question_id` on EX (exact match to the
benchmark's *default* interpretation), bucket every one of the 120 items into
`both_correct` / `both_wrong` / `fixed` (C2 wrong → C3 right) / `regressed` (C2 right → C3
wrong), then read the `fixed`/`regressed` cases directly — those are the only two buckets that
say anything about the module, since `both_correct`/`both_wrong` look identical to "C3 did
nothing."

---

## The narrative in one line

**18 of 120 questions flip from wrong to right, zero flip from right to wrong, every flip sits on
a question the benchmark itself marks ambiguous, and the Ambiguity Detector correctly flagged
`is_ambiguous=True` on 18/18 of them.** The 18 fixes are not scattered — they collapse into two
clean, mechanistically legible behaviours (temporal `active:true` gating; schema role-breadth
resolution), each traceable through the Ambiguity Detector's own rationale text. That is about as
far from "random" as example-level evidence gets. The module's weak spot is just as clear:
**intent-type ambiguity gets fixed zero times** — a structural limit of what a `SchemaMapping`
can express, not a detection failure.

---

## Headline: C2-right/wrong vs C3-right/wrong

| bucket | count | % of 120 |
|---|---|---|
| both_correct | 47 | 39.2% |
| both_wrong | 55 | 45.8% |
| **fixed** (C2✗ → C3✓) | **18** | **15.0%** |
| **regressed** (C2✓ → C3✗) | **0** | **0.0%** |

A net +18/−0 swing against a shared 120-item set is the same signature you'd want from an A/B
test with a real effect: one-directional, and the direction is the one the module is supposed to
produce.

## Stratified by ambiguity_type

| ambiguity_type (n=20 each, unambiguous n=40) | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| temporal | 1 | 6 | **13** | 0 |
| schema | 3 | 13 | **4** | 0 |
| entity | 6 | 13 | 1 | 0 |
| intent | 7 | 13 | **0** | 0 |
| unambiguous | 30 | 10 | 0 | 0 |

Two things jump out. First, **temporal (65% fixed) and schema (20% fixed) account for all but one
of the flips** — exactly the two ambiguity classes whose resolution can be expressed as "pick a
schema element/property filter," which is what a `SchemaMapping` is built to carry. Second,
**unambiguous questions never flip in either direction** (0 fixed, 0 regressed out of 40) — C3's
extra machinery doesn't destabilize questions that didn't need it, which is a precision point in
the module's favour, separate from the recall story above.

---

## What's working

**Temporal ambiguity (13/18 fixes, arguably 14 counting one entity-labelled case below).** Every
one of these questions touches a relationship carrying `active`/`from_date`/`to_date` properties
(`LIVES_AT`, `USES_PHONE`, `OWNS`). C2's `failure_mode` on every single one is `valid_non_default`
— it isn't wrong, it's *answering a different valid reading* (all historical values, unfiltered)
than the benchmark's default (current value only, `{active:true}`). C3's Ambiguity Detector flags
the temporal ambiguity, the Disambiguator commits to `{active:true}`, and the Query Generator adds
exactly that filter. Representative example:

> **Q-105** — *Who owns the Ford Ranger?*
> C2: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN DISTINCT p.name` (matches the "including previous owner" reading — `valid_non_default`)
> C3: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name` (matches default)
> AD rationale: *"The OWNS relationship carries active/from_date/to_date properties... 'who owns' could reasonably mean the current owner or all past and present owners... this temporal ambiguity is inherent in the schema and the question does not specify."*

**Schema role-breadth ambiguity (4/18 fixes).** Whenever a question says "connected to" or
"parties to" an incident, C2's schema linker collapses onto a single relationship type
(`SUSPECTED_OF`) — the AD's own rationale calls this "a training bias rather than a genuine
disambiguation." C3 recognises the phrase spans all four Person→Incident roles and generates the
union:

> **Q-041** — *Show people connected to the Northbridge robbery.*
> C2: `...<-[:SUSPECTED_OF]-(p:Person)...` (suspects only — `wrong_result`)
> C3: `MATCH (p:Person)-[r]->(i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'})...` (any role edge — matches default)

Full list of all 18 fixed cases (and the 0 regressed) is in
`results/qualitative_analysis_claude-sonnet_v3_localdb.md`.

---

## Where it still struggles

**Intent ambiguity: 0/20 fixed, 13/20 both_wrong.** This isn't a detection gap — the AD does
sometimes correctly call `detected_types: ['intent']` (e.g. Q-081, *"Tell me about the suspects in
the Lake Street drug offence"* — the AD's rationale correctly identifies that "tell me about"
underspecifies the RETURN clause: name only vs all properties vs count). The problem is
downstream: a `SchemaMapping` — the Disambiguator's only output — is a *NL mention → schema
element* dict plus a `cypher_syntax` hint. It has no field for "return a count instead of a list,"
because RETURN-clause shape isn't a schema-element decision. Intent ambiguity is structurally
outside what the current Disambiguator can commit to, independent of how well the AD detects it.
A second, subtler pattern: on some gold-intent items (Q-082 *"What about the incidents in
Northbridge?"*, Q-084 *"Show incidents in Perth"*) the AD instead flags `entity` ambiguity, because
multiple `Location` nodes share the suburb name — a real ambiguity, just not the one the benchmark
annotated as canonical for that item.

**Entity ambiguity: 1/20 fixed, 13/20 both_wrong.** Detection itself looks solid — the AD reliably
identifies surname collisions (e.g. Q-064 *"Which incidents is Chen connected to?"*: *"Two distinct
Person nodes match 'Chen' with equal confidence... each would return a different set of
incidents"*). But C2 and C3 emit the **same** broken pattern: `{name:'Chen'}` (or `CONTAINS
'Chen'`), an equality/substring filter that doesn't match either full name (`David Chen`, `Wei
Chen`) and returns nothing — rather than the gold default's `WHERE p.name ENDS WITH ' Chen'`
surname-suffix pattern. The Disambiguator's committed mapping (`{'rel_1': 'SUSPECTED_OF'}`) has no
mechanism to fix the QG's WHERE-clause construction for a name filter — entity ambiguity is
detected but the fix never reaches the part of the query that would need to change. This reads as
a QG/prompt gap (teaching the QG the `ENDS WITH`-on-surname pattern), not an ambiguity-detection
gap.

Representative samples (3 per type) are in the `both_wrong sample` section of
`results/qualitative_analysis_claude-sonnet_v3_localdb.md`.

---

## Takeaways for the dissertation

- The module's contribution is real and legible, not noise: one-directional flips (18/0),
  concentrated exclusively on gold-ambiguous items, with AD detection matching gold on every
  flipped item, and zero collateral damage to unambiguous questions.
- Its mechanism of action is narrow and explainable: it fixes ambiguity types resolvable as a
  schema-element or property-filter choice (temporal, schema), and that's a description of what a
  `SchemaMapping` *is*, not a coincidence.
- Its ceiling is architectural, not a tuning problem: intent ambiguity needs a RETURN-clause-level
  decision that the Disambiguator's output type cannot express; entity ambiguity is detected
  correctly but the fix would need to reach the QG's WHERE-clause pattern, which the current
  hand-off doesn't do.

## Open threads

- Whether extending `SchemaMapping`/the Disambiguator's `cypher_syntax` hint to carry a
  RETURN-clause directive would let intent ambiguity resolve the same way temporal/schema do.
- Whether wiring the AD's entity-ambiguity signal into the QG prompt (e.g. "use `ENDS WITH` on the
  surname") would close the entity-type gap without touching the Disambiguator's contract.
- The Q-082/Q-084 pattern (AD detecting a *real* but *off-annotation* ambiguity) is worth a note in
  the limitations section — it suggests the four-type taxonomy sometimes undercounts genuinely
  ambiguous questions with more than one live axis of ambiguity.
