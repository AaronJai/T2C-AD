# Qualitative C2 vs C3 comparison

n_total joined = 100

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 19 | 19.0% |
| both_wrong | 74 | 74.0% |
| fixed | 5 | 5.0% |
| regressed | 2 | 2.0% |

`fixed` = C2 wrong -> C3 right (candidate evidence the module helps).
`regressed` = C2 right -> C3 wrong (candidate evidence the module hurts).
Net lift should roughly match `ex(C3) - ex(C2)` from metrics_*.json; if it
doesn't, something in this join is off — check the question_id mismatch warning.

## Stratified by ambiguity_type

All four buckets, so "handled well" vs "still struggling" is visible per type,
not just the fixed/regressed pair below:

| ambiguity_type | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| entity | 10 | 10 | 0 | 0 |
| intent | 2 | 15 | 3 | 0 |
| schema | 0 | 20 | 0 | 0 |
| temporal | 0 | 18 | 2 | 0 |
| unambiguous | 7 | 11 | 0 | 2 |

**fixed** by type: {'intent': 3, 'temporal': 2}
**regressed** by type: {'unambiguous': 2}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 0/5
- regressed: AD's is_ambiguous call matched gold for 1/2

## Case studies — fixed (C2 wrong, C3 right)

### Q-POLE-I09 — How many crimes happened in area M1?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Return the count (single number)* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M1' RETURN count(*) AS n`
- alternative gold interpretations:
  - *Count only (975)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M1' RETURN count(*) AS n`
  - *List every individual crime in area M1*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M1' RETURN c.id, c.type, c.date`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: No schema ambiguity detected.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA', 'node_1': 'Crime', 'node_2': 'Location', 'node_3': 'Area'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I12 — How many crimes happened in area BL9?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Return the count (single number)* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='BL9' RETURN count(*) AS n`
- alternative gold interpretations:
  - *Count only (623)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='BL9' RETURN count(*) AS n`
  - *List every individual crime in area BL9*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='BL9' RETURN c.id, c.type, c.date`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL9'}) RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: No schema ambiguity detected.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA', 'node_1': 'Crime', 'node_2': 'Location', 'node_3': 'Area'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I13 — How many crimes happened in area M14?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Return the count (single number)* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M14' RETURN count(*) AS n`
- alternative gold interpretations:
  - *Count only (562)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M14' RETURN count(*) AS n`
  - *List every individual crime in area M14*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M14' RETURN c.id, c.type, c.date`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M14'}) RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: No schema ambiguity detected.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA', 'node_1': 'Crime', 'node_2': 'Location', 'node_3': 'Area'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T17 — How many crimes were recorded (citywide) around 28 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 28 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1014)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 28 RETURN count(*) AS n`
  - *Trailing 7-day window, 22-28 Aug (6556)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) >= 22 AND toInteger(split(c.date,'/')[0]) <= 28 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location) WHERE toInteger(split(c.date,'/')[0]) = 28 RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: No schema ambiguity detected. The question is unambiguous: 'citywide' is a Location-scope signal, and 'around 28 August 2017' is a date-window signal. The question is not ambiguous.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'node_1': 'Crime', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T18 — How many crimes were recorded (citywide) around 30 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 30 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (871)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 30 RETURN count(*) AS n`
  - *Trailing 7-day window, 24-30 Aug (6557)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) >= 24 AND toInteger(split(c.date,'/')[0]) <= 30 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location),       (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE c.date >= '2017-08-30' AND c.date < '2017-09-01' RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(c.date,'/')[0]) = 30 RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: No schema ambiguity detected.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — regressed (C2 right, C3 wrong)

### Q-POLE-U06 — What make is the vehicle with registration RY52 APF?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (v:Vehicle {reg:'RY52 APF'}) RETURN v.make`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (v:Vehicle {reg:'RY52 APF'})-[:INVOLVED_IN]->(c:Crime) RETURN v.make`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (v:Vehicle)-[:INVOLVED_IN]->(c:Crime) WHERE v.registration = 'RY52 APF' RETURN v.make`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: The question is ambiguous with respect to the graph schema. 'What make is the vehicle with registration RY52 APF?' could map to two structurally different Cypher queries, each returning different results. The first query is: MATCH (v:Vehicle {registration: 'RY52 APF'}) RETURN v.make. The second query is: MATCH (c:Crime {registration: 'RY52 APF'})-[:INVOLVED_IN]->(v:Vehicle) RETURN v.make. The first query returns a single Vehicle node, and the second query returns a single Crime node. The two queries return different results, so this is a schema ambiguity.
  committed mapping: {'rel_1': 'INVOLVED_IN', 'node_1': 'Vehicle', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U16 — What type of crime was recorded under ID 10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (c:Crime {id:'10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31'}) RETURN c.type`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime {id:'10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31'}) RETURN c.type`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime {id:'10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31'})-[:OCCURRED_AT]->(l:Location), (o:Object) WHERE c.id = o.id RETURN o.type`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution is a single candidate (Crime.involved_in) with a score of 1.00, so there is no schema ambiguity. The entity candidate distribution is a single candidate (Crime.id 10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31) with a score of 1.00, so there is no entity ambiguity.
  committed mapping: {'rel_1': 'INVOLVED_IN', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 3

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 15 of 74 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

### Q-POLE-E10 — What is the address of a person with the surname Foster?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Foster persons* — `MATCH (p:Person {surname:'Foster'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Andrew*: `MATCH (p:Person {surname:'Foster', name:'Andrew'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Cynthia*: `MATCH (p:Person {surname:'Foster', name:'Cynthia'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Jessica*: `MATCH (p:Person {surname:'Foster', name:'Jessica'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Tammy*: `MATCH (p:Person {surname:'Foster', name:'Tammy'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:KNOWS_SN]->(p:Person {surname:'Foster'}) RETURN p.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:KNOWS_SN]->(l:Location) WHERE p.surname = 'Foster' RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: 'the address of a person with the surname Foster' does not say which digital channel: KNOWS_SN (social-network contact, 6 people) and CURRENT_ADDRESS (6 locations) are disjoint edge types returning different, non-overlapping people (high schema score 0.00).
  committed mapping: {'rel_1': 'CURRENT_ADDRESS', 'rel_2': 'CURRENT_ADDRESS', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 4

### Q-POLE-E12 — What address is on file for Hughes?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Hughes persons* — `MATCH (p:Person {surname:'Hughes'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Louis*: `MATCH (p:Person {surname:'Hughes', name:'Louis'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Maria*: `MATCH (p:Person {surname:'Hughes', name:'Maria'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Nancy*: `MATCH (p:Person {surname:'Hughes', name:'Nancy'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Stephanie*: `MATCH (p:Person {surname:'Hughes', name:'Stephanie'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Hughes'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Hughes'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question doesn't disambiguate between the 5 distinct Person nodes (nhs_no 821-11-2735, 678-06-9352, 328-87-5383, 301-93-2650) sharing the identical full name 'Hughes' (high entity score 1.00), so the result depends on which one is meant.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-E13 — Find the home address of Jackson.

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Jackson persons* — `MATCH (p:Person {surname:'Jackson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Diana*: `MATCH (p:Person {surname:'Jackson', name:'Diana'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Mark*: `MATCH (p:Person {surname:'Jackson', name:'Mark'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Norma*: `MATCH (p:Person {surname:'Jackson', name:'Norma'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Steven*: `MATCH (p:Person {surname:'Jackson', name:'Steven'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Jackson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Jackson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question does not disambiguate between the 10 distinct Locations named 'Jackson' (high entity score 1.00), so the result depends on which one is meant.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I01 — Which Inspector has investigated the most crimes, aside from Nettles Worthy?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Inspector'}) WHERE NOT (o.surname='Nettles' AND o.name='Worthy') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Winonah Skynner (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN o.surname, o.name, count(*) AS n`
  - *Ricca Miskimmon (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Miskimmon', name:'Ricca'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Inspector'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE NOT (n)-[:KNOWS_LW]->(o) RETURN o.name, count(c) AS crimes_investigated ORDER BY crimes_investigated DESC`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Inspector'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE NOT (n)-[:KNOWS_LW]->(o) RETURN o.name, count(c) AS crimes_investigated ORDER BY crimes_investigated DESC`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Officer', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I02 — Which Police Constable has investigated the most crimes, aside from Ings Cloe?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Police Constable'}) WHERE NOT (o.surname='Ings' AND o.name='Cloe') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Hedy Vinson (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN o.surname, o.name, count(*) AS n`
  - *Simmonds Greensall (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Greensall', name:'Simmonds'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Police Constable'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE o.name <> 'Ings' AND o.surname <> 'Cloe' RETURN n.name AS name, count(c) AS crimes_investigated ORDER BY crimes_investigated DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Police Constable'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE o.name <> 'Ings' AND o.surname <> 'Cloe' RETURN n.name AS name, count(c) AS crimes_investigated ORDER BY crimes_investigated DESC LIMIT 1`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Officer', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I03 — Which Chief Inspector has investigated the most crimes, aside from the top three (Monelli Kort, Stave Urban, Febry Roberto)?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Chief Inspector'}) WHERE NOT (o.surname='Monelli' AND o.name='Kort') AND NOT (o.surname='Stave' AND o.name='Urban') AND NOT (o.surname='Febry' AND o.name='Roberto') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Whitney Jeandot (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Jeandot', name:'Whitney'}) RETURN o.surname, o.name, count(*) AS n`
  - *Esma Gorrie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Gorrie', name:'Esma'}) RETURN o.surname, o.name, count(*) AS n`
  - *Evey Rahlof (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Rahlof', name:'Evey'}) RETURN o.surname, o.name, count(*) AS n`
  - *Dottie Syddie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Syddie', name:'Dottie'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Chief Inspector'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE o.name <> n.name RETURN n.name, count(c) AS crimes_count ORDER BY crimes_count DESC`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {rank:'Chief Inspector'})-[:INVESTIGATED_BY]->(n:), (c:Crime) WHERE o.name <> n.name RETURN n.name, count(c) AS crimes_count ORDER BY crimes_count DESC`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Officer', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S01 — Who has Alan Hicks communicated with digitally?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Cynthia Knight)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (7 people)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Alan', surname:'Hicks'})-[:KNOWS_SN]->(p:Person) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {name:'Alan', surname:'Hicks'})-[:KNOWS_SN]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S02 — Who has Ann Fox been in digital contact with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 10 people* — `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Jessica Kelly)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (9 people)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ann', surname:'Fox'})-[:KNOWS_SN]->(p:Person) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {name:'Ann', surname:'Fox'})-[:KNOWS_SN]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: 'been in digital contact with' does not say which digital channel: KNOWS_SN (social-network contact, 3 people) and KNOWS_PHONE (phone contact, 0 people) are disjoint edge types returning different, non-overlapping people (high schema score 0.00).
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S03 — Who has Benjamin Hamilton had digital communication with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE)* — `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_SN]->(p:Person) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_SN]->(p:Person) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Four distinct Person nodes (nhs_no 117-66-8129, 991-70-5333, 903-87-6930, 305-25-0352) share the identical full name 'Benjamin Hamilton' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T01 — How many crimes happened in area M1 around 11 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (47)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  - *Trailing 7-day window, 5-11 Aug (217)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 5 AND toInteger(split(c.date,'/')[0]) <= 11 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}),       (l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}),       (c:Crime) WHERE c.date >= '2017-08-01' AND c.date <= '2017-08-11' RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'LOCATION_IN_AREA', 'rel_2': 'LOCATION_IN_AREA', 'node_1': 'Crime', 'node_3': 'Area'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T02 — How many crimes happened in area M1 around 26 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (46)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
  - *Trailing 7-day window, 20-26 Aug (247)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 20 AND toInteger(split(c.date,'/')[0]) <= 26 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T03 — How many crimes happened in area M1 around 4 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (41)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
  - *Trailing window, 1-4 Aug clipped at month start (132)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 1 AND toInteger(split(c.date,'/')[0]) <= 4 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location),       (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE c.date >= '2017-07-31' AND c.date <= '2017-08-04' AND a.areaCode = 'M1' RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U01 — What rank does the officer with badge number 80-1015383 hold?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (o:Officer {badge_no:'80-1015383'}) RETURN o.rank`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'80-1015383'})-[:INVESTIGATED_BY]->(c:Crime),       (p:Person)-[:KNOWS_SN]->(c:Crime),       (p:Person)-[:HAS_PHONE]->(p:Phone),       (p:PhoneCall)-[:CALLER]->(p:Phone) RETURN o.rank`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'80-1015383'})-[:INVESTIGATED_BY]->(c:Crime),       (p:Person)-[:KNOWS_SN]->(c:Crime),       (p:Person)-[:HAS_PHONE]->(p:Phone),       (p:PhoneCall)-[:CALLER]->(p:Phone) RETURN o.rank`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'rel_2': 'KNOWS_SN', 'rel_3': 'HAS_PHONE', 'rel_4': 'CALLER', 'node_1': 'Officer', 'node_2': 'Crime', 'node_3': 'Person', 'node_4': 'Phone', 'node_5': 'PhoneCall'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U02 — What is the surname of the officer with badge number 70-0643982?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (o:Officer {badge_no:'70-0643982'}) RETURN o.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'70-0643982'})-[:INVESTIGATED_BY]->(c:Crime) RETURN o.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'70-0643982'})-[:INVESTIGATED_BY]->(c:Crime) RETURN c.last_outcome`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: FALLBACK: LLM output unparseable; decided by entropy thresholds.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Officer', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U03 — What rank is the officer with badge number 57-6110377?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (o:Officer {badge_no:'57-6110377'}) RETURN o.rank`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'57-6110377'})-[:INVESTIGATED_BY]->(c:Crime) RETURN o.rank`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (o:Officer {badge_no:'57-6110377'})-[:INVESTIGATED_BY]->(c:Crime) RETURN c.last_outcome`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The only reasonable reading is 'What rank is the officer with badge number 57-6110377?'. The question is not ambiguous with respect to the graph schema.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Officer', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1
