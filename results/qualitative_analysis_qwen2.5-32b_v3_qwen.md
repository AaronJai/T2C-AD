# Qualitative C2 vs C3 comparison

n_total joined = 120

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 22 | 18.3% |
| both_wrong | 88 | 73.3% |
| fixed | 8 | 6.7% |
| regressed | 2 | 1.7% |

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
| intent | 6 | 14 | 0 | 0 |
| schema | 0 | 20 | 0 | 0 |
| temporal | 0 | 18 | 2 | 0 |
| unambiguous | 12 | 20 | 6 | 2 |

**fixed** by type: {'unambiguous': 6, 'temporal': 2}
**regressed** by type: {'unambiguous': 2}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 6/8
- regressed: AD's is_ambiguous call matched gold for 1/2

## Case studies — fixed (C2 wrong, C3 right)

### Q-009 — Who are the current associates of Anton Maric?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Persons on Anton Maric's active ASSOCIATED_WITH edges.* — `MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH]->(p:Person) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p1:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]->(p2:Person) RETURN p2.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: ASSOCIATED_WITH carries active/from_date/to_date, and the candidates split between the current associates ({active:true}) and all past associates; 'current associates' does not say which, so the two readings return different people.
  committed mapping: {'rel_1': 'ASSOCIATED_WITH'} | resolution_mode: automated | n_mappings_tried: 1

### Q-013 — Where did the Fremantle burglary occur?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The location on the OCCURRED_AT edge of the Fremantle burglary (INC-004).* — `MATCH (i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(l:Location {suburb:'Fremantle'}) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:VICTIM_OF]->(i:Incident), (l:Location) WHERE i.crime_type = 'burglary' AND l.suburb = 'Fremantle' RETURN l.address`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution clearly indicates that the relationship between the incident and the location is 'OCCURRED_AT', and the entity lookup results show that 'Fremantle' matches a single location. Therefore, the question can be answered unambiguously by finding the location where the Fremantle burglary occurred.
  committed mapping: {'rel_1': 'VICTIM_OF', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 2

### Q-018 — Who currently uses phone number 0423 987 654?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The person on the active USES_PHONE edge to DEV-002.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0423 987 654'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:USES_PHONE]->(ph:Phone {phone_number:'0423 987 654'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (person:Person)-[:USES_PHONE {active:true}]->(phone:Phone {phone_number:'0423 987 654'}) RETURN person.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution clearly indicates that the question is asking for the current user of the phone number 0423 987 654, as the candidate with the highest score is (Person)-[:USES_PHONE {active:true}]->(Phone). The question is specific and unambiguous, and there is no need for further clarification or disambiguation.
  committed mapping: {'rel_1': 'USES_PHONE', 'node_1': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-020 — List the current residents of 35 Walcott Street.

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Persons with an active LIVES_AT edge to LOC-016.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(:Location {address:'35 Walcott Street'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:LIVES_AT]->(l:Location {address:'35 Walcott Street'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {address:'35 Walcott Street'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: LIVES_AT carries active/from_date/to_date, and the candidates split between the current residents ({active:true}) and all past residents; 'residents' does not say which, so the two readings return different people.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-032 — Who is the victim of the burglary in Fremantle?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Victim of the burglary that OCCURRED_AT a Fremantle location (INC-004).* — `MATCH (p:Person)-[:VICTIM_OF]->(i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(:Location {suburb:'Fremantle'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(l:Location {suburb:'Fremantle'}) RETURN i.victim_id`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(l:Location {suburb:'Fremantle'}), (p:Person)-[:VICTIM_OF]->(i) RETURN p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is highly concentrated on a single interpretation, and there is no entity ambiguity detected. The question is clear and unambiguous with respect to the graph schema.
  committed mapping: {'rel_1': 'OCCURRED_AT', 'rel_2': 'VICTIM_OF', 'node_1': 'Incident', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 1

### Q-038 — Who currently owns the black Holden Commodore?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The person on the active OWNS edge to VEH-001.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Holden', colour:'black'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Holden', colour:'black'}) RETURN p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is concentrated on a single candidate, and the question specifies 'currently', which disambiguates the temporal aspect of the query.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-105 — Who owns the Ford Ranger?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-003.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: OWNS carries active/from_date/to_date, and the candidates split between the current owner ({active:true}) and all past owners; 'owns' does not say which, so the two readings return different people.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-117 — Who owns the Nissan Navara?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-005.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: OWNS carries active/from_date/to_date, and the candidates split between the current owner ({active:true}) and all past owners; 'owns' does not say which, so the two readings return different people.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

## Case studies — regressed (C2 right, C3 wrong)

### Q-005 — Which case contains the Cannington homicide?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The Case with a CONTAINS edge to INC-006.* — `MATCH (c:Case)-[:CONTAINS]->(:Incident {crime_type:'homicide'}) RETURN c.case_name`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (c:Case)-[:CONTAINS]->(i:Incident {crime_type:'homicide'}) RETURN c.case_name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (i:Incident {crime_type:'homicide'})-[:OCCURRED_AT]->(l:Location {suburb:'Cannington'}) RETURN c.case_name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is clear (high score 1.00), and the question is unambiguous with respect to the graph schema. The question asks for the case that contains the Cannington homicide, and the schema candidate distribution indicates that the correct relationship type is (Case)-[:CONTAINS]->(Incident). There is no ambiguity in the question, as it clearly specifies the relationship type and the incident in question.
  committed mapping: {'rel_1': 'CONTAINS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-030 — Who currently lives on Albany Highway in Cannington?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Persons with an active LIVES_AT edge to LOC-009.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {suburb:'Cannington'}) WHERE l.address CONTAINS 'Albany Highway' RETURN p.name`

**C2 (schema_grounded)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:LIVES_AT]->(l:Location {suburb:'Cannington'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {suburb:'Cannington', address:'Albany Highway'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is ambiguous due to entity ambiguity. The phrase 'Albany Highway' matches two distinct Location nodes (Cannington and Victoria Park), and the question does not provide enough context to disambiguate between them. The high entity ambiguity score (1.00) indicates that the question is ambiguous with respect to the entity 'Albany Highway'.
  committed mapping: {'node_1': 'Location', 'node_2': 'Location'} | resolution_mode: automated | n_mappings_tried: 4

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 15 of 88 total)

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

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Tran'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (PER-002, PER-031) match 'Tran' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which Tran is meant.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-062 — Where does Kim currently live?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The current address of the person surnamed Kim — ambiguous.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Kim' RETURN l.address`
- alternative gold interpretations:
  - *Rachel Kim (PER-006)*: `MATCH (:Person {name:'Rachel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Daniel Kim (PER-009)*: `MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Kim'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Kim'})-[:LIVES_AT]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (PER-006, PER-009) match 'Kim' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which Kim is meant.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-063 — What is Nguyen's phone number?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The active phone number of the person surnamed Nguyen — ambiguous.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone) WHERE p.name ENDS WITH ' Nguyen' RETURN ph.phone_number`
- alternative gold interpretations:
  - *Michael Nguyen (PER-015)*: `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  - *Sarah Nguyen (PER-019)*: `MATCH (:Person {name:'Sarah Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Nguyen'})-[:USES_PHONE]->(q:Phone) RETURN q.phone_number`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Nguyen'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (PER-015, PER-019) match 'Nguyen' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which Nguyen is meant.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 2

### Q-081 — Tell me about the suspects in the Lake Street drug offence.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about INC-007's suspects.* — `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`
- alternative gold interpretations:
  - *Return the count of suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN count(p) AS n`
  - *Return the list of suspects' names*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=invalid_query
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) WHERE i.crime_type='drug offence' AND p.address='Lake Street' RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident), (l:Location) WHERE i.crime_type='drug offence' AND l.address='Lake Street' RETURN p.name, p.alias`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution clearly indicates that the relationship type is 'SUSPECTED_OF' and the node types are 'Person' and 'Incident'. The entity lookup results also indicate that 'Lake Street' matches a single location, 'Northbridge'. Therefore, the question can be mapped to a single structurally different Cypher query, and it is not ambiguous with respect to the graph schema.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'node_1': 'Location', 'node_2': 'Person'} | resolution_mode: automated | n_mappings_tried: 4

### Q-082 — What about the incidents in Northbridge?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about the Northbridge incidents.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`
- alternative gold interpretations:
  - *Return the count of incidents*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN count(i) AS n`
  - *Return the list of incident details*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN i`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN i`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The question is underspecified with respect to the entity 'Northbridge', as it matches multiple locations (LOC-001, LOC-002, LOC-006). The question does not provide any additional information to disambiguate between these locations, so the result depends on which Northbridge is meant.
  committed mapping: {'rel_1': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-084 — Show incidents in Perth.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Incidents associated with Perth.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
- alternative gold interpretations:
  - *Only incidents whose suburb is exactly 'Perth'*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
  - *All incidents in the Perth metro area (any suburb)*: `MATCH (i:Incident) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.suburb = 'Perth' RETURN i`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident) RETURN i`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Four distinct Location nodes (LOC-003, LOC-005, LOC-008, LOC-014) match 'Perth' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which Perth is meant.
  committed mapping: {'node_1': 'Incident', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 4

### Q-041 — Show people connected to the Northbridge robbery.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-001.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[r]->(i:Incident {crime_type:'robbery'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: The phrase 'connected to' spreads almost evenly across the four Person->Incident role edges (high schema score 0.91); the Northbridge robbery has distinct suspects, witnesses and investigators, so each edge returns a different set of people.
  committed mapping: {'node_1': 'Person', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 2

### Q-042 — Who is involved in the Cannington homicide?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-006.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-006'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'homicide'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'homicide'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: The phrase 'involved in' spreads across the four Person->Incident role edges (high schema score 0.91); the Cannington homicide has distinct suspects, witnesses and investigators, so each edge returns a different set of people.
  committed mapping: {'rel_1': 'SUSPECTED_OF'} | resolution_mode: automated | n_mappings_tried: 2

### Q-043 — List everyone linked to the fraud on St Georges Terrace.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-005.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'fraud'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'fraud'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: The phrase 'linked to' spreads across the four Person->Incident role edges (high schema score 0.91); the fraud on St Georges Terrace has distinct suspects, witnesses and investigators, so each edge returns a different set of people.
  committed mapping: {'rel_1': 'WITNESSED'} | resolution_mode: automated | n_mappings_tried: 1

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
  AD rationale: Two distinct Person nodes (PER-007, PER-015) match 'James Whitfield' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which James Whitfield is meant.
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
  AD rationale: The question is unambiguous with respect to the graph schema. The schema candidate distribution clearly indicates that the question is asking about the location where Lina Petrova lives, and there is only one possible interpretation of the question. The entity lookup results also confirm that there is no ambiguity in the mention of Lina Petrova, as there is only one matching instance in the knowledge graph. Therefore, the question is not ambiguous and does not require any further clarification or disambiguation.
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
  cypher: `MATCH (p:Person {name: 'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v.make, v.model`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is concentrated on a single relationship type (OWNS) and node labels (Person, Vehicle), and the entity lookup results are unambiguous. Therefore, the question is not ambiguous with respect to the graph schema.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-004 — Which incidents are part of Operation Ironside?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Incidents contained in CASE-001.* — `MATCH (:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i.crime_type`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (c:Case {case_name:'Operation Ironside'})-[:CONTAINS]->(i:Incident) RETURN i.crime_type`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Case nodes (CASE-001, CASE-002) match 'Operation Ironside' and the question gives nothing to disambiguate them (high entity score 0.99), so the result depends on which case is meant.
  committed mapping: {'rel_1': 'CONTAINS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-007 — Which vehicle does James Whitfield currently own?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The vehicle on James Whitfield's active OWNS edge.* — `MATCH (:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.plate`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name: 'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.plate`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes (PER-007, PER-015) match 'James Whitfield' and the question gives nothing to disambiguate them (high entity score 1.00), so the result depends on which James Whitfield is meant.
  committed mapping: {'rel_1': 'OWNS', 'node_1': 'Person', 'node_2': 'Vehicle'} | resolution_mode: automated | n_mappings_tried: 2

### Q-010 — Which phones did phone number 0412 345 678 call?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Phones on the outgoing CALLED edges from DEV-001.* — `MATCH (:Phone {phone_number:'0412 345 678'})-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Phone {phone_number:'0412 345 678'})-[:CALLED]->(p:Phone) RETURN p.phone_number`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Phone {phone_number:'0412 345 678'})-[:CALLED]->(p:Phone) RETURN p.phone_number`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question is not ambiguous. The schema candidate distribution clearly indicates that the relationship type is 'CALLED' and both nodes are of type 'Phone'. The entity lookup results also show that there is no ambiguity in the entities mentioned in the question. Therefore, the question can be mapped to a single structurally different Cypher query, and it is not ambiguous with respect to the graph schema.
  committed mapping: {'rel_1': 'CALLED', 'node_1': 'Phone', 'node_2': 'Phone'} | resolution_mode: automated | n_mappings_tried: 1
