# Session Handoff — Phase 9: External Benchmark Validation

**Project:** T2C Disambiguation Pipeline (Honours thesis, UWA) — repo `T2C-AD`
**Date:** 2026-08-02
**Status at handoff:** 100-item benchmark skeleton drafted, 4 items unresolved, no gold Cypher yet, no formal spec file.

Read `context/ai-workflow-rules.md`, `context/project-overview.md`, and this file before doing anything. `context/progress-tracker.md` (new Phase 9 section) and `context/decisions-log.md` (2026-08-02 row) were updated this session and are the canonical record — this document is a narrative supplement, not a replacement for them.

---

## 1. Why this phase exists

Supervisor reviewed the qualitative analysis + diagrams and flagged a validity concern: the exact-match improvement "resonates with author intent" because the student authored both `benchmark-updated.json`/`benchmark-v3.json` **and** their ground truth — same person designing the benchmark and the architecture being tested against it. Suggested next step: validate against an existing benchmark or graph schema found online (named CySpider as one example, or another POLE-schema dataset), rather than another self-authored benchmark.

v2 and v3 stay frozen and remain the primary evaluated benchmarks. This is a **supplementary external-validity check**, not a replacement.

## 2. Dataset chosen

[`neo4j-graph-examples/pole`](https://github.com/neo4j-graph-examples/pole) — a real, publicly-sourced dataset: Greater Manchester, UK street-crime data (August 2017, from data.gov.uk) modeled on the POLE (Person/Object/Location/Event) schema. ~61.5k nodes / ~105.8k relationships. Downloaded as a Neo4j dump and loaded into the user's **local Neo4j Desktop** (off-cluster — this phase does not use Kaya).

Chosen over alternatives (CySpider, Neo4j's own Text2Cypher 2024/2025v1 corpus, CypherBench) because it's a real POLE-schema graph matching the thesis's own framing, and because Text2Cypher 2025v1 is already the SFT training corpus — reusing it for eval would risk train/test leakage.

## 3. Schema audit — key findings

Explored via `db.labels()`/`db.relationshipTypes()`/`db.propertyKeys()` and targeted Cypher (all results real, gathered interactively — nothing below is assumed).

**11 node labels:** Person (369), Location (14904), Phone (328), Email (328), Officer (1000), PostCode (14196), Area (93), PhoneCall (534), Crime (28762), Object (7), Vehicle (1000).

**17 relationship types:** CURRENT_ADDRESS, HAS_PHONE, HAS_EMAIL, HAS_POSTCODE, POSTCODE_IN_AREA, LOCATION_IN_AREA, KNOWS_SN, KNOWS, CALLER, CALLED, KNOWS_PHONE, OCCURRED_AT, INVESTIGATED_BY, INVOLVED_IN, PARTY_TO, FAMILY_REL, KNOWS_LW.

**Two findings that materially reshaped the plan vs. v2/v3:**

1. **No role-split Person→Crime edges.** Only a single generic `PARTY_TO` (55 edges total — small). `INVOLVED_IN` is Vehicle→Crime (978) and Object→Crime (7), **not** an alternate Person→Crime edge — confirmed by checking `labels(a)`/`labels(b)` on both relationship types.
2. **No dated/state-change relationships anywhere in the graph.** Every relationship's property list is empty except `FAMILY_REL.rel_type` (confirmed via a full `type(r), keys(r), count(*)` audit across all 17 types). Nothing analogous to v3's `active`/`from_date`/`to_date` on `LIVES_AT`/`OWNS`/`USES_PHONE`. All temporal signal lives on **node** properties instead: `Crime.date` (day-level, all within Aug 2017) and `PhoneCall.call_date`/`call_time`.

**Consequence — temporal ambiguity was redefined for this external set** (user decision, asked via explicit tradeoff, chosen: "Redefine, keep at 20"): same-day-vs-trailing-week date/time-window ambiguity over `Crime.date`/`PhoneCall.call_date`+`call_time`, rather than v2/v3's edge-state mechanism. **This is a different mechanism under the same category label — state this explicitly in any write-up comparing temporal EX/EA across benchmark versions, don't conflate them.**

**Schema ambiguity reframed onto two confirmed axes** (since there's no role-edge axis here):
- **Person-Person KNOWS-family**: `KNOWS` / `KNOWS_SN` (social network) / `KNOWS_PHONE` / `KNOWS_LW` (lives with) / `FAMILY_REL`. Confirmed **default-vs-narrow structure**: every specific-type edge has a parallel generic `KNOWS` edge (checked via a `specific_without_generic=0` query), so "any connection" (bare `KNOWS`) is a genuine superset of each specific type, not a redundant reading — mirrors the v3 authoring convention (`cypher_default` = any-role, narrower interpretations = specific types).
- **Crime-participant scope**: `PARTY_TO` (person) vs `INVOLVED_IN` (vehicle/object). Confirmed multiple real crimes (mostly "Vehicle crime" type) have both a non-empty PARTY_TO person and a non-empty INVOLVED_IN vehicle/object.

**Entity ambiguity**: strong support from surname clustering (Fuller/Murray/Nguyen/Austin at n=5; ~14 more clusters at n=3-4). Two pairs are exact full-name duplicates even at first+surname level — **Andrea George** (nhs_no 800-46-2184 vs 391-46-9135) and **Anne Rice** (nhs_no 632-68-0917 vs 612-83-6356) — the hardest, most honest entity items in the set. `CURRENT_ADDRESS` covers 368/369 Persons, so address-lookup is a reliable universal disambiguation vector regardless of surname.

**Intent ambiguity**: real superlative ties found — Inspector rank (Skynner Winonah / Miskimmon Ricca tied at n=44), Police Constable rank (Vinson Hedy / Greensall Simmonds tied at n=43), and an exact 3-way area tie (M14/BL4/BL2 all at 562 total crimes). Also a genuine **definitional divergence** (no tie needed): BL3 leads on total crime (814) but M40 leads on violent-crime count specifically (234 vs 223) — "which area is more dangerous" is real ambiguity depending on definition. Count-vs-list items (e.g. "how many crimes in M1" vs "list crimes in M1") are trivially well-supported since result cardinality differs by construction.

## 4. Current artifact: the 100-item skeleton

**Location:** `scratchpad/benchmark-pole-external-skeleton-draft.json` in the T2C-AD repo (copied there this session from a scratch working area — verified 100 items intact). **Not yet in `data/`** — deliberately, since 4 items are still unresolved (see below) and no gold Cypher exists yet. Same non-canonical convention as the existing `scratchpad/gen_benchmark_v3.py`.

**Shape:** identical to 7.1's `benchmark-v3-skeleton.json` contract — `question_id`, `question`, `num_hops`, `is_ambiguous`, `ambiguity_type`, `default_interp`, `planned_interpretations`, `data_support` (no Cypher yet, that's the next authoring pass). IDs prefixed `Q-POLE-{E,S,I,T,U}nn`.

**Distribution:** 20 entity (E01-E20) / 20 schema (S01-S20) / 20 intent (I01-I20) / 20 temporal (T01-T20) / 20 unambiguous control (U01-U20) = 100 total. Locked by explicit user decision, matching the per-type-reportable-cell logic v3 uses.

**Every item's `data_support` field is either `CONFIRMED` (traced to a specific real query result from this session) or explicitly flagged `PARTIAL`/`NEEDS VERIFICATION`** — nothing was invented to fill a quota. Some batches lean structurally on one data source more than ideal (e.g. 9 of the 20 schema items — S11-S19 — reuse the same PARTY_TO/INVOLVED_IN "Vehicle crime" template with different crime IDs; 15 of the 20 temporal items — T01-T15 — all use area M1's per-day data since that's the only area with day-level granularity pulled so far). Flagged as worth revisiting for variety, not blocking.

## 5. Unresolved — 4 items need attention before Cypher authoring

- **I10** (`PARTIAL`): "Which Chief Inspector has investigated the most crimes, aside from Monelli Kort?" — Chief Inspector's actual top-3 (40/39/38) shows no tie, so there's no genuine second-place ambiguity here as written. Either find a real tie further down the Chief Inspector rank distribution, or drop/replace.
- **I11** (`NEEDS VERIFICATION`): "Which area has the most crime, aside from M1?" — BL1 (860) leads the remainder uniquely, no tie found. Not usable as-is; replace or reframe as an unambiguous control item instead.
- **I15** (`NEEDS VERIFICATION`): "Which area is more dangerous, BL2 or M6?" — intended as a total-vs-violent divergence example (like I04's BL3-vs-M40), but BL2 actually leads M6 on *both* metrics (562>540 total, 197>176 violent). Not a genuine divergence. Replace the comparison pair — re-run the total/violent area query for other pairs to find one that actually diverges, or drop.
- **T20** (`NEEDS VERIFICATION`): pure template, no real numbers — "How many crimes happened in area BL1 around a mid-August date, same-day vs trailing-week?" needs the same per-day breakdown query used for M1 (see §3) re-run scoped to `areaCode:'BL1'` (or any other area) to fill in real day/week counts.

## 6. What's already done in the repo (this session)

- `context/progress-tracker.md`: new **Phase 9 — External Benchmark Validation** section added (after Phase 8, before "Target module layout"), step 9.1 status `in progress`, full narrative of findings/status/next-steps in the Outputs/Handoff cell.
- `context/decisions-log.md`: one new row dated 2026-08-02 recording the supervisor-feedback trigger, the dataset choice and structural findings, and the 4 flagged items with reasoning.
- `scratchpad/benchmark-pole-external-skeleton-draft.json`: the 100-item skeleton (copied in, see §4).
- **No spec file exists for Phase 9 yet.** This stage is closer to 7.1's design/skeleton step than 7.2's authoring step — a formal spec (likely split 9.1/9.2 mirroring 7.1/7.2) should be written before the gold-Cypher authoring pass begins, per `ai-workflow-rules.md`'s "read the spec before implementing" rule. Nobody has done this yet.

## 7. Next steps, in order

1. **Resolve the 4 flagged items** (§5) — either via one more targeted Cypher query each, or by swapping in a different, already-confirmed comparison/tie.
2. **Write a formal spec** for Phase 9 (or 9.1 specifically) before proceeding — the project's own governance requires this; skipping it so far was acceptable for exploratory skeleton drafting but not for the authoring step next.
3. **Author `cypher_default` + per-interpretation Cypher** for all 100 items, mirroring 7.2's authoring discipline (single-line, real whitespace, ≤3 hops, only v3-analog real POLE-Manchester labels/rel-types/properties — note this graph's actual labels/props differ from the synthetic v3 schema, don't mix them up).
4. **Copy the finished, Cypher-complete file into `data/`** (e.g. `data/benchmark-pole-external.json`) once ready.
5. **Run `experiments/validate_benchmark.py` against it, unmodified** — it was deliberately built version-agnostic in 7.2 ("reusable on any benchmark authored to the contract") specifically so a future external benchmark like this one wouldn't need a new harness. All 8 gates (syntax, schema closure, non-empty execution, pairwise-distinct interpretations, etc.) must pass before this benchmark is canonical for any run.
6. Once canonical, the existing pipeline (C1/C2/C3, `run_evaluation.py`) should run against it by config only — no pipeline code changes expected, same pattern as v2→v3.

## 8. Useful raw data (to avoid re-querying)

Real records referenced by the skeleton, for quick lookup without re-running Cypher:

- **Officers:** badge 80-1015383=Lineen/Sophronia/Sergeant; 70-0643982=Glossup/Uri/Inspector; 57-6110377=Hannam/Christian/Police Constable; 18-0221971=Lampet/Eimile/Chief Inspector; 38-1719233=Makinson/Wynn/Chief Inspector. Busiest per rank: Sergeant DeSousa Madelon n=50; Inspector Nettles Worthy n=45 (tie below: Skynner Winonah/Miskimmon Ricca n=44); Police Constable Ings Cloe n=47 (tie below: Vinson Hedy/Greensall Simmonds n=43); Chief Inspector Monelli Kort n=40.
- **Vehicles:** RY52 APF=Toyota 4Runner 2005; RH42 TAB=Jaguar XJ Series 1992; LW72 POF=Audi Coupe GT 1985; TZ72 UGE=Scion xB 2011; BN52 ACF=GMC Sierra 2500 2012.
- **Areas (total/violent crimes):** M1 975/249, BL1 860/242, BL3 814/223, M40 766/234, M9 699/187, BL9 623/204, M14 562/144, BL4 562/195, BL2 562/197, M6 540/176.
- **M1 per-day crime counts (Aug 2017):** 1=35,2=28,3=28,4=41,5=31,6=30,7=21,8=22,9=26,10=40,11=47,12=29,13=24,14=24,15=27,16=30,17=21,18=36,19=31,20=39,21=33,22=30,23=34,24=37,25=28,26=46,27=30,28=36,29=20,30=29,31=42.
- **Citywide per-day crime counts (Aug 2017):** 1=923,2=932,3=920,4=976,5=913,6=897,7=897,8=886,9=928,10=972,11=930,12=900,13=904,14=959,15=922,16=918,17=951,18=965,19=928,20=924,21=899,22=934,23=894,24=957,25=927,26=903,27=927,28=1014,29=958,30=871,31=933.
- **Phone pair:** 0-(008)297-1581 called 9-(984)524-5395 twice: 04/08/2017 00:32 and 20/08/2017 00:05 (only multi-call pair found in a top-5-busiest-phone sample).
- **KNOWS-family pairs with confirmed multiple relationship types:** Benjamin Hamilton↔Todd Hamilton (FAMILY_REL+KNOWS); Benjamin Hamilton→8 people via KNOWS_SN+KNOWS (Alexander, Martin, Fields, Taylor, Cox, Howell, Allen, Murray); Benjamin Hamilton↔Frances Sullivan (KNOWS_PHONE+KNOWS); Rachel Turner↔Todd Garcia (KNOWS_LW+KNOWS); Rachel Turner↔Eric Gutierrez (KNOWS_PHONE+KNOWS); Mildred Kelly↔Stephen Perez (KNOWS_LW+KNOWS); Mildred Kelly↔Jeffrey Campbell (KNOWS_PHONE+KNOWS); Nancy Campbell↔Carl Hayes (KNOWS_PHONE+KNOWS); Nancy Campbell↔Angela Mccoy (KNOWS_SN+KNOWS); Todd Garcia↔Phillip Perry (KNOWS_PHONE+KNOWS).
- **Crimes with confirmed PARTY_TO person + INVOLVED_IN vehicle/object** (20 IDs, mostly "Vehicle crime" type, one "Drugs" with 2 Objects instead of a vehicle): full list in `scratchpad/benchmark-pole-external-skeleton-draft.json` items S11-S20.
- **Duplicate-surname person clusters with confirmed distinct addresses:** ~40 surnames at n=3-5 with full name/nhs_no/address triples — full list in the skeleton file items E01-E20 and the raw query result earlier in this session's transcript (not reproduced here for length — re-query `MATCH (p:Person) WITH p.surname AS surname, collect(p) AS people WHERE size(people)>=3 UNWIND people AS person OPTIONAL MATCH (person)-[:CURRENT_ADDRESS]->(l:Location) RETURN surname, person.name, person.nhs_no, l.address ORDER BY surname` if needed again).
