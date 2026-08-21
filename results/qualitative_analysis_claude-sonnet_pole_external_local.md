# Qualitative C2 vs C3 comparison

n_total joined = 100

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 57 | 57.0% |
| both_wrong | 34 | 34.0% |
| fixed | 7 | 7.0% |
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
| entity | 15 | 1 | 3 | 1 |
| intent | 7 | 12 | 0 | 1 |
| schema | 0 | 19 | 1 | 0 |
| temporal | 17 | 1 | 2 | 0 |
| unambiguous | 18 | 1 | 1 | 0 |

**fixed** by type: {'entity': 3, 'schema': 1, 'temporal': 2, 'unambiguous': 1}
**regressed** by type: {'entity': 1, 'intent': 1}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 5/7
- regressed: AD's is_ambiguous call matched gold for 2/2

## Case studies — fixed (C2 wrong, C3 right)

### Q-POLE-E11 — Where does a person with the surname Hanson currently live?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Hanson persons* — `MATCH (p:Person {surname:'Hanson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Andrea*: `MATCH (p:Person {surname:'Hanson', name:'Andrea'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Irene*: `MATCH (p:Person {surname:'Hanson', name:'Irene'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Patricia*: `MATCH (p:Person {surname:'Hanson', name:'Patricia'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Richard*: `MATCH (p:Person {surname:'Hanson', name:'Richard'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {surname: 'Hanson'})-[:CURRENT_ADDRESS]->(l:Location)
RETURN DISTINCT l.address, l.postcode`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:CURRENT_ADDRESS]->(l:Location) WHERE p.surname = 'Hanson' RETURN DISTINCT l.address`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema is unambiguous (CURRENT_ADDRESS with score 1.00). The entity lookup returns multiple Person nodes with surname Hanson, but the question asks about 'a person with the surname Hanson' — this is intentionally a general/open query seeking all persons with that surname, not a specific individual. All matching Person nodes (Richard, Patricia, Andrea, Irene, Norma, Ruth — all with surname Hanson) would be included in a single query result. The Location matches (Hanson Mews, Hanson Street, etc.) are street names, not surnames, and are clearly not the intended entity. There is no ambiguity about which person is meant because the question is asking about any/all persons with that surname, and all reasonable interpretations lead to the same query structure and result set.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-E13 — Find the home address of Jackson.

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Jackson persons* — `MATCH (p:Person {surname:'Jackson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Diana*: `MATCH (p:Person {surname:'Jackson', name:'Diana'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Mark*: `MATCH (p:Person {surname:'Jackson', name:'Mark'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Norma*: `MATCH (p:Person {surname:'Jackson', name:'Norma'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Steven*: `MATCH (p:Person {surname:'Jackson', name:'Steven'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Jackson'})-[:CURRENT_ADDRESS]->(l:Location) RETURN DISTINCT l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:CURRENT_ADDRESS]->(l:Location) WHERE p.surname = 'Jackson' OR p.name CONTAINS 'Jackson' RETURN DISTINCT l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: 'Jackson' is ambiguous as it could refer to a Person named Jackson (whose home address is sought) or to one of many Location nodes containing 'Jackson' in their address string. The entity lookup returns 10 different Location nodes matching 'Jackson' but no Person node named 'Jackson', yet the question asks for a person's home address. It is unclear whether 'Jackson' is a first name, last name, or part of a street name, and the question does not disambiguate which specific individual or location is meant. The high entity ambiguity score (1.00) reflects this multiplicity of matches.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-E16 — What address does Mason live at?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Mason persons* — `MATCH (p:Person {surname:'Mason'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Michael*: `MATCH (p:Person {surname:'Mason', name:'Michael'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Nicholas*: `MATCH (p:Person {surname:'Mason', name:'Nicholas'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Philip*: `MATCH (p:Person {surname:'Mason', name:'Philip'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Wayne*: `MATCH (p:Person {surname:'Mason', name:'Wayne'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Mason'})-[:CURRENT_ADDRESS]->(l:Location) RETURN DISTINCT l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:CURRENT_ADDRESS]->(l:Location) WHERE p.surname = 'Mason' RETURN DISTINCT l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: 'Mason' matches multiple Person nodes (Nicholas, Philip, Michael, Wayne, and possibly Jason) all with last name Mason, and the question does not provide enough information to disambiguate which Mason is meant. Each person could have a different address, so the result depends on which Person node is intended. The Location matches are irrelevant to the query intent (asking where Mason lives), but the multiple Person matches create genuine entity ambiguity.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S05 — Who has Brenda Edwards been digitally connected to?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Edwards', name:'Brenda'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Steven Jackson)*: `MATCH (p1:Person {surname:'Edwards', name:'Brenda'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (8 people)*: `MATCH (p1:Person {surname:'Edwards', name:'Brenda'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Brenda', surname:'Edwards'})-[:KNOWS_SN]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Person {nhs_no: '778-24-6852'})-[:KNOWS_SN]-(p2:Person)
RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['schema', 'entity']
  AD rationale: Two independent ambiguities are present. (1) SCHEMA: 'digitally connected' does not specify which digital channel — KNOWS_SN (social-network) and KNOWS_PHONE (phone contact) are disjoint edge types returning different, non-overlapping people (schema score 0.72). (2) ENTITY: The entity lookup returns multiple Person nodes potentially matching 'Brenda Edwards' (e.g., Brenda 620-85-3606 and Brenda 778-24-6852 among others), and the question provides no further disambiguation to identify which specific person is meant (entity score 1.00).
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T13 — How many calls did phone 0-(608)989-7174 make around 8 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
  - *Trailing 7-day window, 2-8 Aug (6)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 2 AND toInteger(split(pc.call_date,'/')[0]) <= 8 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'Around 8 August 2017' does not fix a precise date window: a same-day-only reading (calls on exactly 8 August 2017) and a trailing multi-day window (e.g., 5–8 August or 8–14 August) are both reasonable interpretations of Crime.date/PhoneCall.call_date, and would return different counts. The schema is unambiguous (CALLER relationship, score 1.00) and no entity ambiguity exists.
  committed mapping: {'rel_1': 'CALLER|CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T14 — How many calls did phone 0-(807)194-4140 make around 4 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1)*: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
  - *Trailing 7-day window, 1-4 Aug (4)*: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 1 AND toInteger(split(pc.call_date,'/')[0]) <= 4 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'Around 4 August 2017' does not fix a precise date window: a same-day-only reading (calls on exactly 4 August 2017) and a trailing/surrounding multi-day window (e.g., ±3 days or a week around that date) are both reasonable interpretations of Crime.date/PhoneCall.call_date, and would return different counts. The schema is unambiguous (CALLER relationship, score 1.00) and no entity ambiguity exists.
  committed mapping: {'rel_1': 'CALLER|CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U04 — Who is Betty Kennedy related to by family?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct FAMILY_REL relationship lookup (2 people: Donna Frazier, Anne Clark)* — `MATCH (p1:Person {surname:'Kennedy', name:'Betty'})-[:FAMILY_REL]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Betty', surname:'Kennedy'})-[:FAMILY_REL]->(p2:Person)
RETURN DISTINCT p2.name, p2.surname`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Person {name: 'Betty', surname: 'Kennedy'})-[:FAMILY_REL]-(p2:Person)
RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (nhs_no 856-03-3848 and 274-72-8781) both match 'Betty Kennedy' with a perfect score of 1.00, and the question provides no additional information to distinguish between them. Each may have different family relationships, so the result depends on which Betty Kennedy is meant.
  committed mapping: {'rel_1': 'FAMILY_REL'} | resolution_mode: automated | n_mappings_tried: 1

## Case studies — regressed (C2 right, C3 wrong)

### Q-POLE-E02 — What is Anne Rice's address?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — two distinct Persons share the identical full name* — `MATCH (p:Person {name:'Anne', surname:'Rice'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *nhs_no 632-68-0917*: `MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'632-68-0917'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *nhs_no 612-83-6356*: `MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'612-83-6356'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Anne', surname:'Rice'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {nhs_no: '632-68-0917'})-[:CURRENT_ADDRESS]->(l:Location)
RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Multiple distinct Person nodes match 'Anne Rice' (at least 6 matches with score 1.00, including persons with different nhs_no values), and the question provides no additional information to disambiguate which individual is meant. Each person may have a different address, so the result depends entirely on which node is selected.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-I05 — Which area recorded the most crime, after BL9?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode <> 'BL9' WITH a, count(*) AS n RETURN a.areaCode, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *M14 (n=562)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M14'}) RETURN a.areaCode, count(*) AS n`
  - *BL4 (n=562)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL4'}) RETURN a.areaCode, count(*) AS n`
  - *BL2 (n=562)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL2'}) RETURN a.areaCode, count(*) AS n`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area)
WHERE a.areaCode <> 'BL9'
RETURN a.areaCode, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WITH a, count(c) AS crimeCount ORDER BY crimeCount DESC SKIP 1 LIMIT 1 RETURN a.areaCode, crimeCount`
  AD predicted ambiguous: True | detected_types: ['intent']
  AD rationale: 'After BL9' implies BL9 is the top area, and the question asks for the second-place area. If there is a genuine tie for second place among the remaining areas, the question does not specify whether to return a single arbitrary result, all tied records, or a count. Additionally, 'after BL9' could mean the next highest crime count area (rank 2) or all areas excluding BL9 ordered by crime count, which are structurally different RETURN clauses. The schema and entity signals are unambiguous (scores 0.00), so the ambiguity is purely about intent/what to return.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA', 'node_1': 'Crime'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 9 of 34 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

### Q-POLE-E15 — Where can Martin be found living?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Martin persons* — `MATCH (p:Person {surname:'Martin'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Brandon*: `MATCH (p:Person {surname:'Martin', name:'Brandon'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Cheryl*: `MATCH (p:Person {surname:'Martin', name:'Cheryl'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Douglas*: `MATCH (p:Person {surname:'Martin', name:'Douglas'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Michael*: `MATCH (p:Person {surname:'Martin', name:'Michael'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Martin'})-[:CURRENT_ADDRESS]->(l:Location) RETURN DISTINCT l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Martin'})-[:CURRENT_ADDRESS]->(l:Location) RETURN DISTINCT l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The name 'Martin' matches multiple Person nodes (e.g., Person: Martin (872-88-7149), Douglas (447-68-8669), Brandon (853-69-5350)) as well as multiple Location nodes containing 'Martin' in their address. The question asks about a person named 'Martin' living somewhere, but there are multiple Person nodes that could match, and the question provides no additional disambiguating information (e.g., full name, NHS number) to identify which 'Martin' is intended. This leads to entity ambiguity with potentially different address results depending on which person is selected.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS', 'node_1': 'Person', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-I01 — Which Inspector has investigated the most crimes, aside from Nettles Worthy?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Inspector'}) WHERE NOT (o.surname='Nettles' AND o.name='Worthy') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Winonah Skynner (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN o.surname, o.name, count(*) AS n`
  - *Ricca Miskimmon (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Miskimmon', name:'Ricca'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Inspector'})
WHERE o.surname <> 'Worthy'
WITH o, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1
RETURN o.name, o.surname, crimeCount`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer) WHERE o.badge_no <> '27-2227814' AND o.rank = 'Inspector' WITH o, count(c) AS crimeCount ORDER BY crimeCount DESC LIMIT 1 RETURN o.name, o.surname, crimeCount`
  AD predicted ambiguous: True | detected_types: ['intent']
  AD rationale: The schema and entity are both unambiguous (single Officer match, clear relationship). However, 'aside from Nettles Worthy' (the likely top investigator) may leave a genuine tie among the remaining Inspectors. If two or more Officers share the same maximum crime count after excluding Worthy, the question does not specify whether to return a single arbitrary record, all tied records, or just the count — each reading produces a structurally different query and different results. This is a pure intent ambiguity.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Crime'} | resolution_mode: automated | n_mappings_tried: 4

### Q-POLE-I02 — Which Police Constable has investigated the most crimes, aside from Ings Cloe?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Police Constable'}) WHERE NOT (o.surname='Ings' AND o.name='Cloe') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Hedy Vinson (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN o.surname, o.name, count(*) AS n`
  - *Simmonds Greensall (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Greensall', name:'Simmonds'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer)
WHERE o.rank = 'Police Constable' AND NOT (o.name = 'Ings' AND o.surname = 'Cloe')
WITH o, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1
RETURN o.name, o.surname, crimeCount`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer)
WHERE o.name + ' ' + o.surname <> 'Ings Cloe' AND o.rank = 'Police Constable'
WITH o, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1
RETURN o.name, o.surname, crimeCount`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema is unambiguous (single relationship INVESTIGATED_BY, score 1.00). The entity 'Ings Cloe' matches exactly one Officer node (match 1.00, no duplicates). The only potential ambiguity would be an intent/tie issue (as in Example 3), but without data evidence of a tie among the remaining Police Constables after excluding Cloe, there is no basis to declare ambiguity. The question asks for a single superlative ('most crimes'), which is a well-defined aggregation returning one result unless a tie is confirmed in the data — and no such tie is indicated here.
  committed mapping: {'rel_1': 'INVESTIGATED_BY'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-I03 — Which Chief Inspector has investigated the most crimes, aside from the top three (Monelli Kort, Stave Urban, Febry Roberto)?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Chief Inspector'}) WHERE NOT (o.surname='Monelli' AND o.name='Kort') AND NOT (o.surname='Stave' AND o.name='Urban') AND NOT (o.surname='Febry' AND o.name='Roberto') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Whitney Jeandot (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Jeandot', name:'Whitney'}) RETURN o.surname, o.name, count(*) AS n`
  - *Esma Gorrie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Gorrie', name:'Esma'}) RETURN o.surname, o.name, count(*) AS n`
  - *Evey Rahlof (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Rahlof', name:'Evey'}) RETURN o.surname, o.name, count(*) AS n`
  - *Dottie Syddie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Syddie', name:'Dottie'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Chief Inspector'})
WHERE NOT (o.name = 'Monelli' AND o.surname = 'Kort')
AND NOT (o.name = 'Stave' AND o.surname = 'Urban')
AND NOT (o.name = 'Febry' AND o.surname = 'Roberto')
RETURN o.name, o.surname, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer) WHERE o.rank = 'Chief Inspector' AND o.name <> 'Kort' AND o.name <> 'Urban' AND o.name <> 'Roberto'
RETURN o.name, o.surname, count(c) AS crimeCount
ORDER BY crimeCount DESC
LIMIT 1`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: Schema is unambiguous (single clear path: Crime-[:INVESTIGATED_BY]->Officer, score 1.00). All three named entities resolve uniquely. The question asks for the Chief Inspector with the most crimes after excluding the top three named officers — if there is a tie at rank 4, the question could be ambiguous (intent), but the exclusion of three specific top officers makes a tie at the next rank unlikely to be a structural issue, and the question phrasing 'which Chief Inspector' implies a single answer exists. No schema, entity, or temporal ambiguity is present. Without evidence of an actual tie in the data at rank 4, this is not classifiable as an intent ambiguity.
  committed mapping: {'rel_1': 'INVESTIGATED_BY'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-S01 — Who has Alan Hicks communicated with digitally?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Cynthia Knight)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (7 people)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Alan', surname:'Hicks'})-[:HAS_PHONE]->(ph:Phone)<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(ph2:Phone)<-[:HAS_PHONE]-(p2:Person)
RETURN DISTINCT p2.name, p2.surname
UNION
MATCH (p:Person {name:'Alan', surname:'Hicks'})-[:HAS_PHONE]->(ph:Phone)<-[:CALLED]-(pc:PhoneCall)-[:CALLER]->(ph2:Phone)<-[:HAS_PHONE]-(p2:Person)
RETURN DISTINCT p2.name, p2.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (per:Person {name:'Alan', surname:'Hicks'})-[:HAS_PHONE]->(ph:Phone)<-[:CALLER|CALLED]-(pc:PhoneCall)-[:CALLER|CALLED]->(ph2:Phone)<-[:HAS_PHONE]-(per2:Person)
WHERE per2 <> per
RETURN DISTINCT per2.name, per2.surname`
  AD predicted ambiguous: True | detected_types: ['schema', 'entity']
  AD rationale: Two ambiguities are present. First, 'communicated with digitally' maps to both KNOWS_SN (social-network contact) and KNOWS_PHONE (phone contact), which are disjoint edge types returning different, non-overlapping people — a clear schema ambiguity. The schema linker here resolved to a phone-call traversal path (HAS_PHONE -> PhoneCall -> CALLER/CALLED), but KNOWS_SN is an equally valid reading of 'digital communication', making the schema ambiguous. Second, the entity lookup returns three distinct Person nodes (nhs_no 881-20-2396, 852-52-0933, 846-65-7776) for 'Alan Hicks', none of which is clearly the intended referent, so the question is also entity-ambiguous.
  committed mapping: {'rel_1': 'HAS_PHONE', 'rel_2': 'CALLER', 'rel_3': 'CALLED', 'rel_4': 'HAS_PHONE', 'node_1': 'Person', 'node_2': 'Phone', 'node_3': 'PhoneCall', 'node_4': 'Phone', 'node_5': 'Person'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S02 — Who has Ann Fox been in digital contact with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 10 people* — `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Jessica Kelly)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (9 people)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Ann', surname:'Fox'})-[:KNOWS_SN]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {nhs_no: '576-99-9244'})-[:KNOWS_SN]-(p2:Person)
RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['schema', 'entity']
  AD rationale: Two ambiguities are present. First, 'digital contact' maps to both KNOWS_SN (social-network) and KNOWS_PHONE (phone contact), which are disjoint edge types returning different, non-overlapping people — a confirmed schema ambiguity axis in this graph. The schema linker only surfaced KNOWS_SN (score 1.00) but KNOWS_PHONE is an equally valid reading of 'digital contact'. Second, the entity lookup returns multiple Person nodes that do not clearly match 'Ann Fox' — the top match is 'Ann' (576-99-9244) but two other persons (Johnny, Matthew) also score 1.00, suggesting the name lookup is unreliable and there may be multiple candidate nodes for 'Ann Fox', leaving the intended person unresolved.
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S03 — Who has Benjamin Hamilton had digital communication with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE)* — `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:HAS_EMAIL]->(e:Email)<-[:HAS_EMAIL]-(other:Person)
RETURN DISTINCT other.name, other.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:HAS_EMAIL]->(e:Email)<-[:HAS_EMAIL]-(other:Person)
RETURN DISTINCT other.name, other.surname`
  AD predicted ambiguous: True | detected_types: ['schema', 'entity']
  AD rationale: Two ambiguities are present. First, 'digital communication' maps to both KNOWS_SN (social-network contact) and KNOWS_PHONE (phone contact), which are disjoint edge types returning different, non-overlapping people — a schema ambiguity. The schema linker has collapsed onto HAS_EMAIL, but the broader NL term 'digital communication' legitimately spans KNOWS_SN and KNOWS_PHONE as well. Second, 'Benjamin Hamilton' matches multiple distinct Person nodes (nhs_no 117-66-8129, 991-70-5333, 903-87-6930, 305-25-0352) with no disambiguating information provided, making it an entity ambiguity.
  committed mapping: {'rel_1': 'HAS_EMAIL', 'rel_2': 'HAS_EMAIL', 'node_1': 'Person', 'node_2': 'Email', 'node_3': 'Person'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T16 — How many crimes happened in area BL1 around 15 August 2017, same-day vs trailing-week?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) = 15 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (26)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) = 15 RETURN count(*) AS n`
  - *Trailing 7-day window, 09-15 Aug (182)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) >= 9 AND toInteger(split(c.date,'/')[0]) <= 15 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'})
WITH c, toInteger(split(c.date,'/')[0]) AS day, split(c.date,'/')[1] AS month, split(c.date,'/')[2] AS year
WHERE year = '2017' AND month = '08' AND day >= 8 AND day <= 15
RETURN
  sum(CASE WHEN day = 15 THEN 1 ELSE 0 END) AS same_day_count,
  sum(CASE WHEN day >= 8 AND day < 15 THEN 1 ELSE 0 END) AS trailing_week_count`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) >= 15 AND toInteger(split(c.date,'/')[0]) <= 22 RETURN toInteger(split(c.date,'/')[0]) = 15 AS same_day, count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'Around 15 August 2017' does not fix a precise time window: same-day-only and a trailing 7-day window (or other multi-day interpretations) are both reasonable readings of Crime.date and return very different counts. The question itself even explicitly flags this ambiguity ('same-day vs trailing-week'). The schema is unambiguous (single clear path through OCCURRED_AT and LOCATION_IN_AREA), and there is no entity ambiguity.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U05 — Who does Denise Rodriguez know?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct generic KNOWS relationship lookup (1 person: Alice Mcdonald)* — `MATCH (p1:Person {surname:'Rodriguez', name:'Denise'})-[:KNOWS]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Multiple Person nodes match 'Denise Rodriguez' (at least three nodes with first name 'Denise' and others), all with match score 1.00 and different nhs_no identifiers. The question provides no additional information to disambiguate which specific person is meant, so the query result depends on which node is selected.
  committed mapping: {'rel_1': 'KNOWS', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 1
