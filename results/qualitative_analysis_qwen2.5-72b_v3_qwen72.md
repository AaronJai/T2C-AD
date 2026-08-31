# Qualitative C2 vs C3 comparison

n_total joined = 120

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 20 | 16.7% |
| both_wrong | 92 | 76.7% |
| fixed | 5 | 4.2% |
| regressed | 3 | 2.5% |

`fixed` = C2 wrong -> C3 right (candidate evidence the module helps).
`regressed` = C2 right -> C3 wrong (candidate evidence the module hurts).
Net lift should roughly match `ex(C3) - ex(C2)` from metrics_*.json; if it
doesn't, something in this join is off — check the question_id mismatch warning.

## Stratified by ambiguity_type

All four buckets, so "handled well" vs "still struggling" is visible per type,
not just the fixed/regressed pair below:

| ambiguity_type | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| entity | 4 | 16 | 0 | 0 |
| intent | 4 | 15 | 0 | 1 |
| schema | 0 | 20 | 0 | 0 |
| temporal | 0 | 20 | 0 | 0 |
| unambiguous | 12 | 21 | 5 | 2 |

**fixed** by type: {'unambiguous': 5}
**regressed** by type: {'unambiguous': 2, 'intent': 1}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 3/5
- regressed: AD's is_ambiguous call matched gold for 1/3

## Case studies — fixed (C2 wrong, C3 right)

### Q-007 — Which vehicle does James Whitfield currently own?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The vehicle on James Whitfield's active OWNS edge.* — `MATCH (:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:OWNS]->(v:Vehicle) RETURN v.plate`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:OWNS]->(v:Vehicle) RETURN v.vehicle_id`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The phrase 'James Whitfield' matches two distinct Person nodes (PER-007 and PER-015) with a perfect match score of 1.00, and the question does not provide any additional information to disambiguate between the two entities.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-010 — Which phones did phone number 0412 345 678 call?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Phones on the outgoing CALLED edges from DEV-001.* — `MATCH (:Phone {phone_number:'0412 345 678'})-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Phone {phone_number:'0412 345 678'})-[:CALLED]->(p:Phone) RETURN p.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Phone {phone_number:'0412 345 678'})-[:CALLED]->(p2:Phone) RETURN p2.phone_number`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a single relationship type (CALLED) and node label (Phone) for both nodes, with a perfect score of 1.00. There is no entity ambiguity detected, and the schema and entity ambiguity scores are both 0.00, indicating no ambiguity.
  committed mapping: {'rel_1': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-019 — Which phones did phone 0478 444 555 call?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Phones on the outgoing CALLED edges from DEV-008.* — `MATCH (:Phone {phone_number:'0478 444 555'})-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Phone {phone_number:'0478 444 555'})-[:CALLED]->(p:Phone) RETURN p.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Phone {phone_number:'0478 444 555'})-[:CALLED]->(p2:Phone) RETURN p2.phone_number`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a clear mapping to the (Phone)-[:CALLED]->(Phone) relationship, and there is no entity ambiguity detected. The schema ambiguity score is 0.00, indicating no spread across candidates, and the entity ambiguity score is also 0.00, indicating no matching instances. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 2

### Q-024 — What phone numbers did James Whitfield's phone call?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Phones called by the phone James Whitfield actively uses.* — `MATCH (:Person {name:'James Whitfield'})-[:USES_PHONE {active:true}]->(:Phone)-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:USES_PHONE]->(p:Phone), (p:Phone)-[:CALLED]->(p:Phone) RETURN p.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:USES_PHONE]->(phone1:Phone)-[:CALLED]->(phone2:Phone) RETURN phone2.phone_number`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (PER-007, PER-015) match 'James Whitfield' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which James Whitfield is meant.
  committed mapping: {'rel_1': 'USES_PHONE', 'rel_2': 'CALLED'} | resolution_mode: automated | n_mappings_tried: 1

### Q-038 — Who currently owns the black Holden Commodore?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The person on the active OWNS edge to VEH-001.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle) WHERE v.make = 'Holden' AND v.model = 'Commodore' AND v.colour = 'black' RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Holden', model:'Commodore', colour:'black'}) RETURN p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question specifies 'currently owns', which clearly indicates the current owner ({active:true}) and not all past owners. The schema candidate distribution shows a single candidate for the relationship type (OWNS), and there is no entity ambiguity detected. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — regressed (C2 right, C3 wrong)

### Q-004 — Which incidents are part of Operation Ironside?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Incidents contained in CASE-001.* — `MATCH (:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The phrase 'Operation Ironside' matches two distinct Case nodes (CASE-001 and CASE-002) with high match scores, and the question does not provide any additional context to disambiguate between them. Therefore, the result depends on which 'Operation Ironside' is meant.
  committed mapping: {'rel_1': 'CONTAINS', 'node_1': 'Case', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 2

### Q-011 — List all incidents that occurred in Northbridge.

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Incidents with an OCCURRED_AT edge to a Northbridge location.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.suburb = 'Northbridge' RETURN DISTINCT i.incident_id`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (l:Location {suburb:'Northbridge'}), (i:Incident) RETURN DISTINCT i.crime_type`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to the entity 'Northbridge' matching three distinct Location nodes (LOC-001, LOC-002, LOC-006) with perfect match scores. The question does not provide any additional context to disambiguate which Northbridge location is meant, leading to different results depending on the intended location.
  committed mapping: {'node_1': 'Location', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 2

### Q-096 — List the incidents in Operation Ironside.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Incidents contained in CASE-001.* — `MATCH (:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id`
- alternative gold interpretations:
  - *Return the count of incidents*: `MATCH (:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident) RETURN count(i) AS n`
  - *Return the list of incident details*: `MATCH (:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id, i.crime_type`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The phrase 'Operation Ironside' matches two distinct Case nodes (CASE-001 and CASE-002) with high match scores, and the question does not provide any additional context to disambiguate between them. Therefore, the result depends on which 'Operation Ironside' is meant.
  committed mapping: {'rel_1': 'CONTAINS', 'node_1': 'Case', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 2

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 15 of 92 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

### Q-061 — What is Tran's current address?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The current address of the person surnamed Tran — ambiguous.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Tran' RETURN l.address`
- alternative gold interpretations:
  - *Megan Tran (PER-002)*: `MATCH (:Person {name:'Megan Tran'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Kevin Tran (PER-031)*: `MATCH (:Person {name:'Kevin Tran'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Tran'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Megan Tran'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Tran's current address, but there are two distinct Person nodes (PER-002, PER-031) that match 'Tran'. The question does not provide any additional information to disambiguate between the two, so the result depends on which Tran is meant.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-062 — Where does Kim currently live?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The current address of the person surnamed Kim — ambiguous.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Kim' RETURN l.address`
- alternative gold interpretations:
  - *Rachel Kim (PER-006)*: `MATCH (:Person {name:'Rachel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Daniel Kim (PER-009)*: `MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Kim'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Rachel Kim'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for the current location of 'Kim', but there are two distinct Person nodes (PER-006, PER-009) that match 'Kim'. The question does not provide any additional information to disambiguate between the two entities, so the result depends on which 'Kim' is meant.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-063 — What is Nguyen's phone number?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The active phone number of the person surnamed Nguyen — ambiguous.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone) WHERE p.name ENDS WITH ' Nguyen' RETURN ph.phone_number`
- alternative gold interpretations:
  - *Michael Nguyen (PER-015)*: `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  - *Sarah Nguyen (PER-019)*: `MATCH (:Person {name:'Sarah Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Nguyen'})-[:USES_PHONE]->(phone:Phone) RETURN phone.phone_number`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Sarah Nguyen'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks for Nguyen's phone number, but there are two distinct Person nodes (PER-015, PER-019) that match 'Nguyen'. The question does not provide any additional information to disambiguate between the two, so the result depends on which Nguyen is meant.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 2

### Q-081 — Tell me about the suspects in the Lake Street drug offence.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about INC-007's suspects.* — `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`
- alternative gold interpretations:
  - *Return the count of suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN count(p) AS n`
  - *Return the list of suspects' names*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'drug offence'}) WHERE i.location_id = 'Lake Street' RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'drug offence', location_id:'Lake Street'}) RETURN p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The phrase 'suspects in' maps directly to the relationship (Person)-[:SUSPECTED_OF]->(Incident) with a score of 1.00, indicating no schema ambiguity. There are no entity ambiguities detected, and the schema and entity ambiguity scores are both 0.00, confirming the lack of ambiguity.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'node_1': 'Incident', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 1

### Q-082 — What about the incidents in Northbridge?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about the Northbridge incidents.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`
- alternative gold interpretations:
  - *Return the count of incidents*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN count(i) AS n`
  - *Return the list of incident details*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN i.crime_type`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident), (l:Location) WHERE i.crime_type = 'burglary' AND l.suburb = 'Northbridge' RETURN i`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question asks about incidents in Northbridge, but there are three distinct Location nodes (LOC-001, LOC-002, LOC-006) that match 'Northbridge'. The question does not provide any additional information to disambiguate which Northbridge location is meant, leading to potential different results depending on the intended location.
  committed mapping: {'node_1': 'Incident', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 4

### Q-084 — Show incidents in Perth.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Incidents associated with Perth.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
- alternative gold interpretations:
  - *Only incidents whose suburb is exactly 'Perth'*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
  - *All incidents in the Perth metro area (any suburb)*: `MATCH (i:Incident) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.suburb = 'Perth' RETURN i`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident), (l:Location) WHERE i.status = 'open' AND l.suburb = 'Perth' RETURN i.incident_id`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The entity 'Perth' matches multiple locations (West Perth, Perth, Perth, Perth) with perfect match scores, making it unclear which specific location is being referred to in the context of the question.
  committed mapping: {'node_1': 'Incident', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 2

### Q-041 — Show people connected to the Northbridge robbery.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-001.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'robbery'}) WHERE i.location_id = 'Northbridge' RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The phrase 'connected to' is resolved to the SUSPECTED_OF edge with a score of 1.00, indicating no schema ambiguity. There is no entity ambiguity detected, and the schema and entity ambiguity scores are both 0.00, indicating no ambiguity in the question.
  committed mapping: {'rel_1': 'INVESTIGATES'} | resolution_mode: automated | n_mappings_tried: 3

### Q-042 — Who is involved in the Cannington homicide?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-006.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'homicide'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'homicide'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution shows that the relationship type (Person)-[:SUSPECTED_OF]->(Incident) has a score of 1.00, indicating that it is the only valid relationship type for the question. There is no entity ambiguity detected, and the schema ambiguity score is 0.00, indicating that there is no ambiguity in the schema. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'SUSPECTED_OF'} | resolution_mode: automated | n_mappings_tried: 1

### Q-043 — List everyone linked to the fraud on St Georges Terrace.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-005.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'fraud'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:VICTIM_OF]->(i:Incident {crime_type:'fraud'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution shows that the relationship type (Person)-[:INVESTIGATES]->(Incident) has a score of 1.00, indicating that it is the only valid relationship type for the given question. There is no entity ambiguity detected, and the schema ambiguity score is 0.00, indicating that there is no ambiguity in the schema. Therefore, the question is not ambiguous.
  committed mapping: {'rel_1': 'VICTIM_OF'} | resolution_mode: automated | n_mappings_tried: 2

### Q-101 — Where does James Whitfield live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *James Whitfield's residence.* — `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The entity lookup results show that 'James Whitfield' matches two distinct Person nodes (PER-007 and PER-015) with a perfect match score of 1.00. The question does not provide any additional information to disambiguate between these two entities, leading to different results depending on which 'James Whitfield' is meant.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-102 — Where does Lina Petrova live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Lina Petrova's residence.* — `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a single relationship type (LIVES_AT) and node labels (Person and Location) with a score of 1.00, indicating no ambiguity in the schema. The entity lookup results show a single match for 'Lina Petrova' with a perfect match score of 1.00, indicating no entity ambiguity. The question is clear in its intent to find the location where Lina Petrova lives, and there is no temporal ambiguity as the question does not specify a time frame.
  committed mapping: {'rel_1': 'LIVES_AT', 'node_1': 'Person', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 1

### Q-103 — What vehicle does Ricky Santos own?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Ricky Santos's vehicle ownership.* — `MATCH (:Person {name:'Ricky Santos'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`
- alternative gold interpretations:
  - *Currently owned vehicles only*: `MATCH (:Person {name:'Ricky Santos'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`
  - *Including vehicles previously owned*: `MATCH (:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v.vehicle_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a single relationship type (OWNS) and node labels (Person and Vehicle) with a score of 1.00, indicating no schema ambiguity. The entity lookup results show a single match for 'Ricky Santos' with a perfect match score of 1.00, indicating no entity ambiguity. The question clearly asks for the vehicle owned by Ricky Santos, and there is no underspecification or temporal ambiguity.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-005 — Which case contains the Cannington homicide?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The Case with a CONTAINS edge to INC-006.* — `MATCH (c:Case)-[:CONTAINS]->(:Incident {crime_type:'homicide'}) RETURN c.case_name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (c:Case)-[:CONTAINS]->(i:Incident) WHERE i.crime_type = 'homicide' AND i.address CONTAINS 'Cannington' RETURN c.case_name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (c:Case)-[:CONTAINS]->(i:Incident) WHERE i.crime_type = 'homicide' AND i.location.suburb = 'Cannington' RETURN c.case_name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a clear mapping to the relationship (Case)-[:CONTAINS]->(Incident) and the entities are not ambiguous. The schema ambiguity score is 0.00, indicating no spread across candidates, and the entity ambiguity score is also 0.00, indicating no matching instances that could cause ambiguity.
  committed mapping: {'rel_1': 'CONTAINS', 'node_1': 'Incident', 'node_2': 'Case'} | resolution_mode: automated | n_mappings_tried: 1

### Q-006 — What phone number does Daniel Kim currently use?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The phone on Daniel Kim's active USES_PHONE edge.* — `MATCH (:Person {name:'Daniel Kim'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {name:'Daniel Kim'})-[:USES_PHONE]->(p:Phone) RETURN p.phone_number`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person {name:'Daniel Kim'})-[:USES_PHONE]->(p:Phone) RETURN p.phone_number`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is unambiguous. The schema candidate distribution shows a single relationship type (USES_PHONE) and node labels (Person and Phone) with a score of 1.00, indicating no schema ambiguity. The entity lookup results show a single match for 'Daniel Kim' with a perfect match score of 1.00, indicating no entity ambiguity. The question specifies 'currently use', which aligns with the active state implied by the schema, so there is no temporal ambiguity. The intent is clear: to find the phone number associated with Daniel Kim via the USES_PHONE relationship.
  committed mapping: {'rel_1': 'USES_PHONE', 'node_1': 'Person', 'node_2': 'Phone'} | resolution_mode: automated | n_mappings_tried: 1

### Q-009 — Who are the current associates of Anton Maric?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Persons on Anton Maric's active ASSOCIATED_WITH edges.* — `MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH]->(p:Person) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH]->(p:Person) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question specifies 'current associates', which aligns with the active state of the ASSOCIATED_WITH relationship. The schema candidate distribution is focused on the ASSOCIATED_WITH relationship between two Person nodes, and the entity lookup uniquely identifies Anton Maric. There is no ambiguity in the schema, entity, intent, or temporal aspects of the question.
  committed mapping: {'rel_1': 'ASSOCIATED_WITH', 'node_1': 'Person', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 1
