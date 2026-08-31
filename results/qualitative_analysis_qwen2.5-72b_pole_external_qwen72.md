# Qualitative C2 vs C3 comparison

n_total joined = 100

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 33 | 33.0% |
| both_wrong | 54 | 54.0% |
| fixed | 10 | 10.0% |
| regressed | 3 | 3.0% |

`fixed` = C2 wrong -> C3 right (candidate evidence the module helps).
`regressed` = C2 right -> C3 wrong (candidate evidence the module hurts).
Net lift should roughly match `ex(C3) - ex(C2)` from metrics_*.json; if it
doesn't, something in this join is off — check the question_id mismatch warning.

## Stratified by ambiguity_type

All four buckets, so "handled well" vs "still struggling" is visible per type,
not just the fixed/regressed pair below:

| ambiguity_type | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| entity | 11 | 6 | 0 | 3 |
| intent | 4 | 14 | 2 | 0 |
| schema | 0 | 20 | 0 | 0 |
| temporal | 3 | 9 | 8 | 0 |
| unambiguous | 15 | 5 | 0 | 0 |

**fixed** by type: {'intent': 2, 'temporal': 8}
**regressed** by type: {'entity': 3}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 9/10
- regressed: AD's is_ambiguous call matched gold for 3/3

## Case studies — fixed (C2 wrong, C3 right)

### Q-POLE-I15 — How many crimes has Sergeant DeSousa Madelon investigated?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Return the count (single number)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN count(*) AS n`
- alternative gold interpretations:
  - *Count only (50)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN count(*) AS n`
  - *List every individual crime investigated*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN c.id, c.date`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {name:'DeSousa', surname:'Madelon', rank:'Sergeant'}) RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {name: 'Madelon'}) WHERE o.surname = 'DeSousa' RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question mentions 'Sergeant DeSousa Madelon', but the entity lookup results show that 'Sergeant' matches two different Officer nodes (Shellysheldon and Ellynn) and 'Madelon' matches two different Officer nodes (Madelon and Madelaine). The question does not provide enough information to determine which specific Officer is meant, leading to ambiguity in the entity lookup results.
  committed mapping: {'rel_1': 'INVESTIGATED_BY'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I19 — Which is the most common crime type across all areas?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top type (Violence and sexual offences, n=8765)* — `MATCH (c:Crime) RETURN c.type AS crime_type, count(c) AS total ORDER BY count(c) DESC limit 1`
- alternative gold interpretations:
  - *List all types above a threshold (>2000 occurrences)*: `MATCH (c:Crime) WHERE c.type IS NOT NULL WITH c.type AS t, count(*) AS n WHERE n > 2000 RETURN t, n ORDER BY n DESC`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) RETURN a.areaCode AS areaCode, c.type AS type, count(*) AS count ORDER BY count DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) RETURN c.type AS type, count(*) AS n ORDER BY n DESC LIMIT 1`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution shows a clear mapping to the relationships and nodes involved in the query. There is no entity ambiguity detected, and the schema ambiguity score is low, indicating a clear mapping to the graph schema.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T01 — How many crimes happened in area M1 around 11 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (47)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  - *Trailing 7-day window, 5-11 Aug (217)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 5 AND toInteger(split(c.date,'/')[0]) <= 11 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[1]) = 1 AND c.date =~ '2017-08-11.*' RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 11 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 05-11 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T02 — How many crimes happened in area M1 around 26 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (46)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
  - *Trailing 7-day window, 20-26 Aug (247)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 20 AND toInteger(split(c.date,'/')[0]) <= 26 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[0]) = 1 AND toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 26 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 26 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 20-26 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T03 — How many crimes happened in area M1 around 4 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (41)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
  - *Trailing window, 1-4 Aug clipped at month start (132)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 1 AND toInteger(split(c.date,'/')[0]) <= 4 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[0]) = 1 AND toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 4 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 4 August' does not fix a window: same-day-only (15 crimes) and the trailing 7-day window 29 July - 4 Aug (112 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T04 — How many crimes happened in area M1 around 31 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 31 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (42)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 31 RETURN count(*) AS n`
  - *Trailing 7-day window, 25-31 Aug (231)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 25 AND toInteger(split(c.date,'/')[0]) <= 31 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[0]) = 1 AND toInteger(split(c.date,'/')[0]) = 31 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 31 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 31 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 25-31 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T07 — How many crimes happened in area M1 around 20 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 20 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (39)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 20 RETURN count(*) AS n`
  - *Trailing 7-day window, 14-20 Aug (208)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 14 AND toInteger(split(c.date,'/')[0]) <= 20 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[0]) = 1 AND toInteger(split(c.date,'-')[0]) = 2017 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 20 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 20 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 14-20 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T08 — How many crimes happened in area M1 around 9 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 9 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (26)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 9 RETURN count(*) AS n`
  - *Trailing 7-day window, 3-9 Aug (199)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 3 AND toInteger(split(c.date,'/')[0]) <= 9 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(a.areaCode,' ')[0]) = 1 AND toInteger(split(c.date,'/')[0]) = 9 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 9 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 9 August' does not fix a window: same-day-only (19 crimes) and the trailing 7-day window 03-09 Aug (137 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T11 — When did phone 9-(777)035-6240 last contact phone 0-(273)550-0236?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 21/08/2017 03:52*: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 23:32, 02/08 22:07, 03/08 21:01, 08/08 10:01, 10/08 13:39, 21/08 03:52*: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'9-(777)035-6240'}) WITH p.call_date AS last_call_date MATCH (p:PhoneCall {call_date:last_call_date})-[:CALLED]->(p:Phone {phoneNo:'0-(273)550-0236'}) RETURN p.call_date`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T13 — How many calls did phone 0-(608)989-7174 make around 8 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
  - *Trailing 7-day window, 2-8 Aug (6)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 2 AND toInteger(split(pc.call_date,'/')[0]) <= 8 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'0-(608)989-7174'}) WHERE toInteger(split(p.call_date,' ')[0]) >= 7 AND toInteger(split(p.call_date,' ')[0]) <= 9 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 8 AND toInteger(split(pc.call_date,'/')[0]) <= 14 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 8 August' does not fix a window: same-day-only (1 call) and the trailing 7-day window 02-08 Aug (12 calls) are both reasonable readings of PhoneCall.call_date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on PhoneCall.call_date, not edge-state.
  committed mapping: {'rel_1': 'CALLER'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — regressed (C2 right, C3 wrong)

### Q-POLE-E01 — What is Andrea George's address?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — two distinct Persons share the identical full name* — `MATCH (p:Person {name:'Andrea', surname:'George'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *nhs_no 800-46-2184*: `MATCH (p:Person {name:'Andrea', surname:'George', nhs_no:'800-46-2184'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *nhs_no 391-46-9135*: `MATCH (p:Person {name:'Andrea', surname:'George', nhs_no:'391-46-9135'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Andrea', surname:'George'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Andrea George'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Andrea George's address, but there are multiple persons with the name 'Andrea George' in the entity lookup results. The question does not provide any additional information to disambiguate which 'Andrea George' is meant, leading to ambiguity in the entity identification.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-E02 — What is Anne Rice's address?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — two distinct Persons share the identical full name* — `MATCH (p:Person {name:'Anne', surname:'Rice'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *nhs_no 632-68-0917*: `MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'632-68-0917'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *nhs_no 612-83-6356*: `MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'612-83-6356'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Anne', surname:'Rice'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name: 'Anne', nhs_no: '632-68-0917'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Anne Rice's address, but there are multiple persons named Anne in the entity lookup results. The question does not provide any additional information to disambiguate which Anne is meant, so the result depends on which Anne is intended.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-E17 — Find Moreno's address.

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Moreno persons* — `MATCH (p:Person {surname:'Moreno'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Andrea*: `MATCH (p:Person {surname:'Moreno', name:'Andrea'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Barbara*: `MATCH (p:Person {surname:'Moreno', name:'Barbara'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Daniel*: `MATCH (p:Person {surname:'Moreno', name:'Daniel'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Julie*: `MATCH (p:Person {surname:'Moreno', name:'Julie'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {surname:'Moreno'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Julie'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question 'Find Moreno's address' is ambiguous due to the entity ambiguity. There are multiple persons with the last name 'Moreno' in the graph, and the question does not specify which one is meant. The entity lookup results show four distinct Person nodes with the last name 'Moreno', and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 15 of 54 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

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
  AD rationale: The question asks for the home address of Jackson, but there are multiple Location nodes that match the name 'Jackson' (high entity score 1.00). The question does not provide any additional information to disambiguate which Jackson is meant, so the result depends on which one is intended.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-E14 — What is Knight's registered address?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Knight persons* — `MATCH (p:Person {surname:'Knight'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Christopher*: `MATCH (p:Person {surname:'Knight', name:'Christopher'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Cynthia*: `MATCH (p:Person {surname:'Knight', name:'Cynthia'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *James*: `MATCH (p:Person {surname:'Knight', name:'James'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Peter*: `MATCH (p:Person {surname:'Knight', name:'Peter'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Knight'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Knight'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Knight's registered address, but there are multiple entities matching 'Knight'. The entity lookup results show that 'Knight' matches a Location and four Persons. The question does not specify which 'Knight' is meant, so the result depends on which one is intended.
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-E15 — Where can Martin be found living?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *No safe default — 4 distinct Martin persons* — `MATCH (p:Person {surname:'Martin'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Brandon*: `MATCH (p:Person {surname:'Martin', name:'Brandon'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Cheryl*: `MATCH (p:Person {surname:'Martin', name:'Cheryl'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Douglas*: `MATCH (p:Person {surname:'Martin', name:'Douglas'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  - *Michael*: `MATCH (p:Person {surname:'Martin', name:'Michael'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Martin'})-[:KNOWS_LW]->(p:Person)-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Martin'})-[:KNOWS_LW]->(p2:Person)-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Martin's living location, but there are multiple entities named 'Martin' in the graph, including both Persons and Locations. The entity lookup results show 10 matching instances, with 3 Persons and 7 Locations. The question does not provide any additional information to disambiguate which 'Martin' is meant, so the result depends on which one is intended.
  committed mapping: {'rel_1': 'KNOWS_LW', 'rel_2': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-I01 — Which Inspector has investigated the most crimes, aside from Nettles Worthy?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Inspector'}) WHERE NOT (o.surname='Nettles' AND o.name='Worthy') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Winonah Skynner (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN o.surname, o.name, count(*) AS n`
  - *Ricca Miskimmon (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Miskimmon', name:'Ricca'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``
  AD predicted ambiguous: None | detected_types: None
  committed mapping: None | resolution_mode: None | n_mappings_tried: None

### Q-POLE-I02 — Which Police Constable has investigated the most crimes, aside from Ings Cloe?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Police Constable'}) WHERE NOT (o.surname='Ings' AND o.name='Cloe') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Hedy Vinson (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN o.surname, o.name, count(*) AS n`
  - *Simmonds Greensall (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Greensall', name:'Simmonds'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``
  AD predicted ambiguous: None | detected_types: None
  committed mapping: None | resolution_mode: None | n_mappings_tried: None

### Q-POLE-I03 — Which Chief Inspector has investigated the most crimes, aside from the top three (Monelli Kort, Stave Urban, Febry Roberto)?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Chief Inspector'}) WHERE NOT (o.surname='Monelli' AND o.name='Kort') AND NOT (o.surname='Stave' AND o.name='Urban') AND NOT (o.surname='Febry' AND o.name='Roberto') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Whitney Jeandot (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Jeandot', name:'Whitney'}) RETURN o.surname, o.name, count(*) AS n`
  - *Esma Gorrie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Gorrie', name:'Esma'}) RETURN o.surname, o.name, count(*) AS n`
  - *Evey Rahlof (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Rahlof', name:'Evey'}) RETURN o.surname, o.name, count(*) AS n`
  - *Dottie Syddie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Syddie', name:'Dottie'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``
  AD predicted ambiguous: None | detected_types: None
  committed mapping: None | resolution_mode: None | n_mappings_tried: None

### Q-POLE-S01 — Who has Alan Hicks communicated with digitally?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Cynthia Knight)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (7 people)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Alan', surname:'Hicks'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Alan', surname:'Hicks'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Three distinct Person nodes (nhs_no 881-20-2396, 852-52-0933, and 846-65-7776) share the partial name 'Alan' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_PHONE', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-S02 — Who has Ann Fox been in digital contact with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 10 people* — `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Jessica Kelly)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (9 people)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ann', surname:'Fox'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ann', surname:'Fox'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Three distinct Person nodes (nhs_no 576-99-9244, 641-52-2437, and 255-89-9885) share the partial name 'Ann Fox' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_PHONE', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-S03 — Who has Benjamin Hamilton had digital communication with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE)* — `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_PHONE]->(p:Person) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Four distinct Person nodes (nhs_no 117-66-8129, 991-70-5333, 903-87-6930, 305-25-0352) share the identical first name 'Benjamin' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_PHONE', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T05 — When did phone 9-(776)276-2772 last contact phone 0-(377)507-0388?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 16/08/2017 14:14*: `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 23:30, 02/08 22:02, 03/08 21:00, 11/08 16:27, 13/08 04:37, 16/08 14:14*: `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'9-(776)276-2772'}), (p:PhoneCall)-[:CALLED]->(p:Phone {phoneNo:'0-(377)507-0388'}) RETURN max(p.call_date) AS last_contact_date`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'9-(776)276-2772'}), (p:PhoneCall)-[:CALLED]->(p:Phone {phoneNo:'0-(377)507-0388'}) RETURN max(p.call_date) AS last_contact_date`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution shows a clear mapping to the relationship types and node labels, and there is no entity ambiguity detected. The question is asking for the last contact between two specific phones, and the schema candidate distribution provides a clear path to answer this question.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED', 'node_1': 'Phone', 'node_2': 'PhoneCall', 'node_3': 'Phone'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T06 — When did phone 9-(488)105-0765 last contact phone 0-(711)302-8090?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 26/08/2017 13:45*: `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 02/08 22:45, 03/08 21:31, 04/08 20:29, 18/08 14:16, 23/08 10:45, 26/08 13:45*: `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'9-(488)105-0765'}) WITH p.call_date AS last_call_date MATCH (p:PhoneCall {call_date:last_call_date})-[:CALLED]->(p:Phone {phoneNo:'0-(711)302-8090'}) RETURN p.call_date`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T09 — When did phone 9-(494)467-2643 last contact phone 0-(649)542-7430?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 26/08/2017 12:33*: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 02/08 22:48, 03/08 21:34, 04/08 20:32, 09/08 02:34, 22/08 20:28, 26/08 12:33*: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:PhoneCall)-[:CALLER]->(p:Phone {phoneNo:'9-(494)467-2643'}), (p:PhoneCall)-[:CALLED]->(p:Phone {phoneNo:'0-(649)542-7430'}) RETURN max(p.call_date) AS last_contact_date`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U04 — Who is Betty Kennedy related to by family?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct FAMILY_REL relationship lookup (2 people: Donna Frazier, Anne Clark)* — `MATCH (p1:Person {surname:'Kennedy', name:'Betty'})-[:FAMILY_REL]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Betty', surname:'Kennedy'})-[:FAMILY_REL]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Betty', surname:'Kennedy'})-[:FAMILY_REL]->(p:Person) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (nhs_no 856-03-3848 and 274-72-8781) share the identical full name 'Betty Kennedy' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'FAMILY_REL', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U05 — Who does Denise Rodriguez know?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct generic KNOWS relationship lookup (1 person: Alice Mcdonald)* — `MATCH (p1:Person {surname:'Rodriguez', name:'Denise'})-[:KNOWS]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p:Person) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Five distinct Person nodes (nhs_no 801-38-9691, 529-97-6193, 507-22-5331, 694-81-0546, 335-36-7489) share the identical first name 'Denise' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U07 — What model is the vehicle with registration RH42 TAB?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (v:Vehicle {reg:'RH42 TAB'}) RETURN v.model`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``
  AD predicted ambiguous: None | detected_types: None
  committed mapping: None | resolution_mode: None | n_mappings_tried: None
