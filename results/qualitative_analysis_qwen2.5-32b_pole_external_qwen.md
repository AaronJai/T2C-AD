# Qualitative C2 vs C3 comparison

n_total joined = 100

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 37 | 37.0% |
| both_wrong | 47 | 47.0% |
| fixed | 16 | 16.0% |
| regressed | 0 | 0.0% |

`fixed` = C2 wrong -> C3 right (candidate evidence the module helps).
`regressed` = C2 right -> C3 wrong (candidate evidence the module hurts).
Net lift should roughly match `ex(C3) - ex(C2)` from metrics_*.json; if it
doesn't, something in this join is off — check the question_id mismatch warning.

## Stratified by ambiguity_type

All four buckets, so "handled well" vs "still struggling" is visible per type,
not just the fixed/regressed pair below:

| ambiguity_type | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| entity | 11 | 9 | 0 | 0 |
| intent | 5 | 15 | 0 | 0 |
| schema | 0 | 19 | 1 | 0 |
| temporal | 7 | 0 | 13 | 0 |
| unambiguous | 14 | 4 | 2 | 0 |

**fixed** by type: {'schema': 1, 'temporal': 13, 'unambiguous': 2}
**regressed** by type: {}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 15/16
- regressed: AD's is_ambiguous call matched gold for 0/0

## Case studies — fixed (C2 wrong, C3 right)

### Q-POLE-S04 — Who has Bonnie Gilbert had electronic communication with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Gilbert', name:'Bonnie'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Fred Williamson)*: `MATCH (p1:Person {surname:'Gilbert', name:'Bonnie'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (8 people)*: `MATCH (p1:Person {surname:'Gilbert', name:'Bonnie'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Person {name:'Bonnie', surname:'Gilbert'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity', 'schema']
  AD rationale: Two distinct Person nodes (nhs_no 528-85-4153 and 622-53-3302) share the identical full name 'Bonnie Gilbert' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant. 'had electronic communication with' does not say which digital channel: KNOWS_SN (social-network contact, 1 person) and KNOWS_PHONE (phone contact, 1 person) are disjoint edge types returning different, non-overlapping people (high schema score 0.99).
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T01 — How many crimes happened in area M1 around 11 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (47)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  - *Trailing 7-day window, 5-11 Aug (217)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'}) WHERE toInteger(split(c.date,'/')[0]) >= 5 AND toInteger(split(c.date,'/')[0]) <= 11 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='M1' AND toInteger(split(c.date,'/')[0])>=10 AND toInteger(split(c.date,'/')[0])<=12 RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE toInteger(split(c.date,'/')[0]) = 11 AND a.areaCode='M1' RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 11 August' does not fix a window: same-day-only (10 crimes) and the trailing 7-day window 05-11 Aug (64 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T05 — When did phone 9-(776)276-2772 last contact phone 0-(377)507-0388?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 16/08/2017 14:14*: `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 23:30, 02/08 22:02, 03/08 21:00, 11/08 16:27, 13/08 04:37, 16/08 14:14*: `MATCH (p1:Phone {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall)-[:CALLER]->(p1:Phone {phoneNo:'9-(776)276-2772'}), (p2:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(377)507-0388'}) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1 {phoneNo:'9-(776)276-2772'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2 {phoneNo:'0-(377)507-0388'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T06 — When did phone 9-(488)105-0765 last contact phone 0-(711)302-8090?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 26/08/2017 13:45*: `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 02/08 22:45, 03/08 21:31, 04/08 20:29, 18/08 14:16, 23/08 10:45, 26/08 13:45*: `MATCH (p1:Phone {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall {phoneNo:'9-(488)105-0765'})-[:CALLER]->(p:Phone),      (p2:PhoneCall {phoneNo:'0-(711)302-8090'})-[:CALLED]->(p:Phone) RETURN p.call_date, p.call_time ORDER BY p.call_date DESC, p.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1 {phoneNo:'9-(488)105-0765'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2 {phoneNo:'0-(711)302-8090'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T09 — When did phone 9-(494)467-2643 last contact phone 0-(649)542-7430?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 26/08/2017 12:33*: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 02/08 22:48, 03/08 21:34, 04/08 20:32, 09/08 02:34, 22/08 20:28, 26/08 12:33*: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall {phoneNo:'9-(494)467-2643'})-[:CALLER]->(p:Phone),      (p2:PhoneCall {phoneNo:'0-(649)542-7430'})-[:CALLED]->(p:Phone) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Phone {phoneNo:'9-(494)467-2643'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(649)542-7430'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T10 — When did phone 9-(601)270-8329 last contact phone 0-(521)287-3218?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(601)270-8329'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(521)287-3218'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 23/08/2017 21:11*: `MATCH (p1:Phone {phoneNo:'9-(601)270-8329'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(521)287-3218'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 07:48, 02/08 23:02, 03/08 21:39, 04/08 20:46, 07/08 20:50, 23/08 21:11*: `MATCH (p1:Phone {phoneNo:'9-(601)270-8329'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(521)287-3218'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall {phoneNo:'9-(601)270-8329'})-[:CALLER]->(p:Phone),      (p2:PhoneCall {phoneNo:'0-(521)287-3218'})-[:CALLED]->(p:Phone) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1 {phoneNo:'9-(601)270-8329'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2 {phoneNo:'0-(521)287-3218'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T11 — When did phone 9-(777)035-6240 last contact phone 0-(273)550-0236?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 21/08/2017 03:52*: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 23:32, 02/08 22:07, 03/08 21:01, 08/08 10:01, 10/08 13:39, 21/08 03:52*: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall {phoneNo:'9-(777)035-6240'})-[:CALLER]->(p:Phone),       (p2:PhoneCall {phoneNo:'0-(273)550-0236'})-[:CALLED]->(p:Phone) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Phone {phoneNo:'9-(777)035-6240'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(273)550-0236'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T12 — When did phone 9-(721)729-4724 last contact phone 0-(404)296-6252?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'9-(721)729-4724'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(404)296-6252'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 24/08/2017 14:48*: `MATCH (p1:Phone {phoneNo:'9-(721)729-4724'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(404)296-6252'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 01/08 23:20, 02/08 21:58, 03/08 20:53, 10/08 00:09, 15/08 15:24, 24/08 14:48*: `MATCH (p1:Phone {phoneNo:'9-(721)729-4724'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'0-(404)296-6252'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p1:PhoneCall {call_type:'mobile'})-[:CALLER]->(p:Phone {phoneNo:'9-(721)729-4724'}),       (p2:PhoneCall {call_type:'mobile'})-[:CALLED]->(p:Phone {phoneNo:'0-(404)296-6252'}) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1 {phoneNo:'9-(721)729-4724'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2 {phoneNo:'0-(404)296-6252'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T13 — How many calls did phone 0-(608)989-7174 make around 8 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
  - *Trailing 7-day window, 2-8 Aug (6)*: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 2 AND toInteger(split(pc.call_date,'/')[0]) <= 8 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p1:PhoneCall)-[:CALLER]->(p:Phone) WHERE p.phoneNo='0-(608)989-7174' AND toInteger(split(p1.call_date,'/')[0])=8 RETURN count(*)`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'0-(608)989-7174'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 8 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 8 August' does not fix a window: same-day-only (1 call) and the trailing 7-day window 02-08 Aug (10 calls) are both reasonable readings of PhoneCall.call_date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on PhoneCall.call_date, not edge-state.
  committed mapping: {'rel_1': 'CALLER|CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T14 — How many calls did phone 0-(807)194-4140 make around 4 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (1)*: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
  - *Trailing 7-day window, 1-4 Aug (4)*: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 1 AND toInteger(split(pc.call_date,'/')[0]) <= 4 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'0-(807)194-4140'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 4 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 4 August' does not fix a window: same-day-only (1 call) and the trailing 7-day window 29 Jul-4 Aug (10 calls) are both reasonable readings of PhoneCall.call_date and return different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on PhoneCall.call_date, not edge-state.
  committed mapping: {'rel_1': 'CALLER|CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-T15 — How many calls did phone 9-(882)417-7531 make around 17 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (ph:Phone {phoneNo:'9-(882)417-7531'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 17 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (2)*: `MATCH (ph:Phone {phoneNo:'9-(882)417-7531'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 17 RETURN count(*) AS n`
  - *Trailing 7-day window, 11-17 Aug (3)*: `MATCH (ph:Phone {phoneNo:'9-(882)417-7531'})<-[:CALLER|CALLED]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) >= 11 AND toInteger(split(pc.call_date,'/')[0]) <= 17 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (ph:Phone {phoneNo:'9-(882)417-7531'})<-[:CALLER]-(pc:PhoneCall) WHERE toInteger(split(pc.call_date,'/')[0]) = 17 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 17 August' does not fix a window: same-day-only (1 call) and the trailing 7-day window 11-17 Aug (10 calls) are both reasonable readings of PhoneCall.call_date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on PhoneCall.call_date, not edge-state.
  committed mapping: {'rel_1': 'CALLER'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T16 — How many crimes happened in area BL1 around 15 August 2017, same-day vs trailing-week?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) = 15 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (26)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) = 15 RETURN count(*) AS n`
  - *Trailing 7-day window, 09-15 Aug (182)*: `MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) >= 9 AND toInteger(split(c.date,'/')[0]) <= 15 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location), (l:Location)-[:LOCATION_IN_AREA]->(a:Area) WHERE a.areaCode='BL1' AND toInteger(split(c.date,'/')[0])>=15 AND toInteger(split(c.date,'/')[0])<=21 AND toInteger(split(c.date,'/')[1])=8 RETURN count(*)`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL1'}) WHERE toInteger(split(c.date,'/')[0]) = 15 RETURN count(*)`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 15 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 09-15 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'LOCATION_IN_AREA'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T19 — How many crimes were recorded (citywide) around 11 August 2017?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Same calendar day* — `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
- alternative gold interpretations:
  - *Same day only (930)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  - *Trailing 7-day window, 5-11 Aug (6423)*: `MATCH (c:Crime) WHERE toInteger(split(c.date,'/')[0]) >= 5 AND toInteger(split(c.date,'/')[0]) <= 11 RETURN count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS '11 Aug 2017' RETURN count(*) AS n`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location) WHERE toInteger(split(c.date,'/')[0]) = 11 RETURN count(*) AS n`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'around 11 August' does not fix a window: same-day-only (26 crimes) and the trailing 7-day window 09-15 Aug (182 crimes) are both reasonable readings of Crime.date and return very different counts. This graph has no active/from_date/to_date edge state; the ambiguity is a date-window choice on Crime.date, not edge-state.
  committed mapping: {'rel_1': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-T20 — When did phone 0-(008)297-1581 last contact 9-(984)524-5395?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Most recent single contact* — `MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
- alternative gold interpretations:
  - *Most recent only: 20/08/2017 00:05*: `MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  - *Full contact history: 04/08/2017 00:32 and 20/08/2017 00:05*: `MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p1:PhoneCall {phoneNo:'0-(008)297-1581'})-[:CALLER]->(p:Phone),      (p2:PhoneCall {phoneNo:'9-(984)524-5395'})-[:CALLED]->(p:Phone) RETURN p1.call_date, p1.call_time ORDER BY p1.call_date DESC, p1.call_time DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1 {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2 {phoneNo:'9-(984)524-5395'}) RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: 'last contact' does not fix the SCOPE of the call history, not a date window - no date is even mentioned. The single most-recent call (ORDER BY call_date DESC, call_time DESC LIMIT 1) and the full contact history (every call, no LIMIT) are both valid readings and return a different number of rows, so this is a query-shape/scope choice, distinct from the day-window mechanism in Example 4.
  committed mapping: {'rel_1': 'CALLER', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U04 — Who is Betty Kennedy related to by family?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct FAMILY_REL relationship lookup (2 people: Donna Frazier, Anne Clark)* — `MATCH (p1:Person {surname:'Kennedy', name:'Betty'})-[:FAMILY_REL]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Betty', surname:'Kennedy'})-[:FAMILY_REL]->(p:Person) RETURN p.name, p.surname`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Person {name:'Betty', surname:'Kennedy'})-[:FAMILY_REL]-(p2:Person) RETURN p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (nhs_no 856-03-3848 and 274-72-8781) share the identical full name 'Betty Kennedy' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'FAMILY_REL'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U15 — What area is postcode WN3 4NL in?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (pc:PostCode {code:'WN3 4NL'})-[:POSTCODE_IN_AREA]->(a:Area) RETURN a.areaCode`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:PostCode {code:'WN3 4NL'})-[:POSTCODE_IN_AREA]->(a:Area) RETURN a.areaCode`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: There is no ambiguity in this question. The schema candidate distribution clearly indicates that the relationship type is 'POSTCODE_IN_AREA' and the node types are 'PostCode' and 'Area'. The entity lookup results also show that there is no ambiguity in the entity mentioned in the question. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'POSTCODE_IN_AREA', 'node_1': 'PostCode', 'node_2': 'Area'} | resolution_mode: automated | n_mappings_tried: 1

## Case studies — regressed (C2 right, C3 wrong)

*(none)*

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 12 of 47 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

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
  AD rationale: The question is ambiguous because the mention 'Hughes' matches multiple entities (Location: 179 Hughes Close, and four different Persons: Stephanie, Maria, Nancy, and Louis). The question does not provide enough context to determine which entity is being referred to, leading to ambiguity in the results.
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
  AD rationale: The question does not specify which Jackson location is being referred to, and there are multiple locations with the name 'Jackson' (high entity score 1.00).
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
  AD rationale: The question does not specify which Knight is being referred to, as there are multiple entities with the name 'Knight' (Location, Person).
  committed mapping: {'rel_1': 'CURRENT_ADDRESS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-I01 — Which Inspector has investigated the most crimes, aside from Nettles Worthy?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Inspector'}) WHERE NOT (o.surname='Nettles' AND o.name='Worthy') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Winonah Skynner (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN o.surname, o.name, count(*) AS n`
  - *Ricca Miskimmon (n=44)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Miskimmon', name:'Ricca'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {nhs_no:'9500100000'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS cnt, p.name, p.surname ORDER BY cnt DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {nhs_no:'950010000I'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS n, p.name, p.surname ORDER BY n DESC LIMIT 1`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution indicates that the question is not ambiguous with respect to the graph schema. The highest scoring relationship types are (Person)-[:KNOWS]->(Person) and (Person)-[:INVESTIGATED_BY]->(Crime), which are both relevant to the question. The entity lookup results also indicate that there is no ambiguity with respect to the entities mentioned in the question. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'KNOWS', 'rel_2': 'KNOWS', 'rel_3': 'INVESTIGATED_BY', 'node_3': 'Crime', 'node_4': 'Crime'} | resolution_mode: automated | n_mappings_tried: 4

### Q-POLE-I02 — Which Police Constable has investigated the most crimes, aside from Ings Cloe?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Police Constable'}) WHERE NOT (o.surname='Ings' AND o.name='Cloe') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Hedy Vinson (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN o.surname, o.name, count(*) AS n`
  - *Simmonds Greensall (n=43)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Greensall', name:'Simmonds'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {name:'Ings', surname:'Cloe'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS cnt, p.name, p.surname ORDER BY cnt DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {title:'Police Constable'})-[:KNOWS]->(p:Person), (p:Person {name:'Ings', surname:'Cloe'})-[:INVESTIGATED_BY]->(c:Crime) WITH p, count(c) AS n ORDER BY n DESC LIMIT 1 RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['intent']
  AD rationale: Excluding Ings Cloe (the outright leader) leaves a genuine tie for the remainder (Winonah Skynner and Ricca Miskimmon both n=44); 'aside from X' doesn't say whether to return a single arbitrary top result, a count, or all tied records, and each reading returns a different answer.
  committed mapping: {'rel_1': 'INVESTIGATED_BY'} | resolution_mode: automated | n_mappings_tried: 4

### Q-POLE-I03 — Which Chief Inspector has investigated the most crimes, aside from the top three (Monelli Kort, Stave Urban, Febry Roberto)?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Single top of the remainder (arbitrary tiebreak)* — `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {rank:'Chief Inspector'}) WHERE NOT (o.surname='Monelli' AND o.name='Kort') AND NOT (o.surname='Stave' AND o.name='Urban') AND NOT (o.surname='Febry' AND o.name='Roberto') WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1`
- alternative gold interpretations:
  - *Whitney Jeandot (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Jeandot', name:'Whitney'}) RETURN o.surname, o.name, count(*) AS n`
  - *Esma Gorrie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Gorrie', name:'Esma'}) RETURN o.surname, o.name, count(*) AS n`
  - *Evey Rahlof (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Rahlof', name:'Evey'}) RETURN o.surname, o.name, count(*) AS n`
  - *Dottie Syddie (n=37)*: `MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Syddie', name:'Dottie'}) RETURN o.surname, o.name, count(*) AS n`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {name:'Monelli', surname:'Kort'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS n, p.name, p.surname ORDER BY n DESC LIMIT 1 UNION ALL MATCH (p:Person {name:'Stave', surname:'Urban'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS n, p.name, p.surname ORDER BY n DESC LIMIT 1 UNION ALL MATCH (p:Person {name:'Febry', surname:'Roberto'})-[:KNOWS]->(p:Person), (p:Person)-[:INVESTIGATED_BY]->(c:Crime) RETURN count(*) AS n, p.name, p.surname ORDER BY n DESC LIMIT 1`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `WITH 'Chief Inspector' AS title RETURN title, collect(name) AS top_three WITH title, apoc.list.slice(top_three, 0, 3) AS top_three CALL { WITH title RETURN title, collect(name) AS all_inspectors WITH title, apoc.list.slice(all_inspectors, 0, 3) AS top_three RETURN title, top_three } UNION ALL (p:Person)-[:INVESTIGATED_BY]->(c:Crime) WHERE p.title = title AND p.name NOT IN top_three RETURN p.name, COUNT(c) AS crime_count ORDER BY crime_count DESC LIMIT 1`
  AD predicted ambiguous: True | detected_types: ['intent']
  AD rationale: Excluding the top three (Monelli Kort, Stave Urban, Febry Roberto) leaves a genuine tie for the remainder (Winonah Skynner and Ricca Miskimmon both n=44); 'aside from X' doesn't say whether to return a single arbitrary top result, a count, or all tied records, and each reading returns a different answer.
  committed mapping: {'rel_1': 'INVESTIGATED_BY', 'node_1': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S01 — Who has Alan Hicks communicated with digitally?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 8 people* — `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Cynthia Knight)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (7 people)*: `MATCH (p1:Person {surname:'Hicks', name:'Alan'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: ``

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {nhs_no:'852-52-0933'})-[:KNOWS_SN]-(p2:Person) RETURN p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (nhs_no 881-20-2396 and 852-52-0933) share the identical full name 'Alan' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-S02 — Who has Ann Fox been in digital contact with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE) — 10 people* — `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE (1 person: Jessica Kelly)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN (9 people)*: `MATCH (p1:Person {surname:'Fox', name:'Ann'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ann', surname:'Fox'})-[:KNOWS_SN]->(p:Person) RETURN p.name, p.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {name:'Ann', surname:'Fox'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Three distinct Person nodes (nhs_no 576-99-9244, 641-52-2437, and 255-89-9885) share the identical full name 'Ann Fox' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-S03 — Who has Benjamin Hamilton had digital communication with?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any digital communication relationship type (KNOWS_SN or KNOWS_PHONE)* — `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN|KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
- alternative gold interpretations:
  - *Only KNOWS_PHONE*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_PHONE]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  - *Only KNOWS_SN*: `MATCH (p1:Person {surname:'Hamilton', name:'Benjamin'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_SN]->(p:Person) RETURN p.name, p.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p1:Person {name:'Benjamin', surname:'Hamilton'})-[:KNOWS_SN]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity', 'schema']
  AD rationale: Four distinct Person nodes (nhs_no 117-66-8129, 991-70-5333, 903-87-6930, 305-25-0352) share the identical full name 'Benjamin Hamilton' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant. 'digital communication' does not say which digital channel: KNOWS_SN (social-network contact, 7 people) and KNOWS_PHONE (phone contact, 1 person) are disjoint edge types returning different, non-overlapping people (high schema score 0.99).
  committed mapping: {'rel_1': 'KNOWS_SN'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U05 — Who does Denise Rodriguez know?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct generic KNOWS relationship lookup (1 person: Alice Mcdonald)* — `MATCH (p1:Person {surname:'Rodriguez', name:'Denise'})-[:KNOWS]-(p2:Person) RETURN DISTINCT p2.name, p2.surname`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p:Person) RETURN p.name, p.surname`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p1:Person {name:'Denise', surname:'Rodriguez'})-[:KNOWS]->(p2:Person) RETURN p2.name, p2.surname`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Five distinct Person nodes (nhs_no 801-38-9691, 529-97-6193, 507-22-5331, 694-81-0546, and 335-36-7489) share the identical full name 'Denise Rodriguez' (high entity score 1.00), and the question gives nothing to tell them apart, so the result depends on which one is meant.
  committed mapping: {'rel_1': 'KNOWS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-POLE-U08 — What year was the vehicle with registration LW72 POF made?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (v:Vehicle {reg:'LW72 POF'}) RETURN v.year`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (v:Vehicle {reg:'LW72POF'}) RETURN v.year`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (v:Vehicle {reg:'LW72POF'}) RETURN v.year`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: There is no ambiguity in this question. The schema candidate distribution clearly indicates that the relationship type is (Vehicle)-[:INVOLVED_IN]->(Crime) and the node types are Vehicle and Crime. The entity lookup results also indicate that there is no ambiguity in the entity mentioned in the question. The question is asking for the year the vehicle with registration LW72 POF was made, and the schema candidate distribution and entity lookup results provide enough information to answer the question without any ambiguity.
  committed mapping: {'rel_1': 'INVOLVED_IN', 'node_1': 'Vehicle', 'node_2': 'Crime'} | resolution_mode: automated | n_mappings_tried: 1

### Q-POLE-U17 — On what date did crime 8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4 occur?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Direct/keyed property lookup* — `MATCH (c:Crime {id:'8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4'}) RETURN c.date`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (c:Crime {id:'8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4'})-[:OCCURRED_AT]->(l:Location) RETURN l.date`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (c:Crime {id:'8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4'})-[:OCCURRED_AT]->(l:Location) RETURN l.date`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution clearly indicates that the relationship type is (Crime)-[:OCCURRED_AT]->(Location), and the node candidates are Crime and Location. The entity lookup results show that there is no entity ambiguity. The schema ambiguity score and entity ambiguity score are both 0.00, indicating that there is no ambiguity in the schema or entities. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'node_1': 'Crime', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 1
