# Qualitative C2 vs C3 comparison

n_total joined = 120

## Overall (EX: matches default interpretation)

| bucket | count | % of n |
|---|---|---|
| both_correct | 47 | 39.2% |
| both_wrong | 55 | 45.8% |
| fixed | 18 | 15.0% |
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
| entity | 6 | 13 | 1 | 0 |
| intent | 7 | 13 | 0 | 0 |
| schema | 3 | 13 | 4 | 0 |
| temporal | 1 | 6 | 13 | 0 |
| unambiguous | 30 | 10 | 0 | 0 |

**fixed** by type: {'schema': 4, 'entity': 1, 'temporal': 13}
**regressed** by type: {}

If `fixed` concentrates in ambiguous types (schema/entity/intent/temporal) and
`regressed` is flat/rare, that's consistent with the module resolving real
ambiguity. If `fixed` is spread evenly across ambiguous AND unambiguous questions
at similar rates, that points to retry-budget luck (C3 gets more regeneration
attempts than C2) rather than disambiguation actually working. A type with a high
`both_wrong` count and low `fixed` count (relative to its total ambiguous n) is
where the module is still struggling — see the both_wrong sample below.

## Detection sanity check (fixed + regressed only)

- fixed: AD's is_ambiguous call matched gold for 18/18
- regressed: AD's is_ambiguous call matched gold for 0/0

## Case studies — fixed (C2 wrong, C3 right)

### Q-041 — Show people connected to the Northbridge robbery.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-001.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-001'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (loc:Location {suburb:'Northbridge'})<-[:OCCURRED_AT]-(i:Incident {crime_type:'robbery'})<-[:SUSPECTED_OF]-(p:Person)-[:ASSOCIATED_WITH]->(p2:Person) RETURN DISTINCT p2.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[r]->(i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) WHERE i.crime_type = 'robbery' RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: Despite the schema linker returning low entropy scores, the phrase 'connected to' is inherently ambiguous across the four Person->Incident relationship types (SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES). The linker has collapsed onto one interpretation (SUSPECTED_OF via ASSOCIATED_WITH chain), but 'connected to' reasonably maps to any of the four role edges, each returning a structurally different query and a different set of people. The schema linker's confident score here reflects a single candidate selection, not the true semantic breadth of 'connected to'.
  committed mapping: {'node_1': 'Person', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 1

### Q-046 — Who is connected to the Midland robbery?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-008.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-008'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only the suspect*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-008'}) RETURN DISTINCT p.name`
  - *Only the witness*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-008'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-008'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(l:Location {suburb:'Midland'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (l:Location {suburb:'Midland'})<-[:OCCURRED_AT]-(i:Incident {crime_type:'robbery'})<-[r]-(p:Person) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: Despite the schema linker collapsing to a single candidate (SUSPECTED_OF), the natural-language phrase 'connected to' is inherently ambiguous across all four Person->Incident relationship types (SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES). The linker's score of 1.00 on SUSPECTED_OF reflects a training bias rather than a genuine disambiguation; a person who witnessed or was a victim of the Midland robbery is equally 'connected to' it, and each edge would return a different set of people.
  committed mapping: {'node_1': 'Person', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 1

### Q-049 — Show all parties to the fraud at 100 Hay Street.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-012.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-012'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-012'}) RETURN DISTINCT p.name`
  - *Only the witness*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-012'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-012'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location {address:'100 Hay Street'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (l:Location {address:'100 Hay Street'})<-[:OCCURRED_AT]-(i:Incident {crime_type:'fraud'})<-[:SUSPECTED_OF|WITNESSED|VICTIM_OF|INVESTIGATES]-(p:Person) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema', 'entity']
  AD rationale: Two ambiguities are present. First, 'parties' is schema-ambiguous: while the schema linker scores SUSPECTED_OF at 1.00, 'parties to a fraud' could reasonably include victims (VICTIM_OF), witnesses (WITNESSED), and investigators (INVESTIGATES) — all four Person->Incident edges are plausible interpretations of 'parties'. Second, '100 Hay Street' matches six distinct Location nodes (entity ambiguity score 1.00), and the question provides no further disambiguation to determine which specific location node is intended, so the query result depends on which location is selected.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'rel_2': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-052 — Who is connected to the traffic incident?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-010.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-010'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only the suspect*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-010'}) RETURN DISTINCT p.name`
  - *Only the witness*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-010'}) RETURN DISTINCT p.name`
  - *Only the investigating officer*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-010'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'traffic'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[r]->(i:Incident {crime_type:'traffic'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['schema']
  AD rationale: The phrase 'connected to' is inherently ambiguous across the four Person->Incident relationship types (SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES). Although the schema linker assigned all weight to SUSPECTED_OF (score 1.00), this likely reflects a bias in the candidate distribution rather than a genuine disambiguation — 'connected to' does not semantically restrict to suspects only. A person could be connected to a traffic incident as a witness, victim, or investigator, each returning a different set of people via structurally different queries.
  committed mapping: {'node_1': 'Person', 'node_2': 'Incident'} | resolution_mode: automated | n_mappings_tried: 1

### Q-063 — What is Nguyen's phone number?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The active phone number of the person surnamed Nguyen — ambiguous.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone) WHERE p.name ENDS WITH ' Nguyen' RETURN ph.phone_number`
- alternative gold interpretations:
  - *Michael Nguyen (PER-015)*: `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  - *Sarah Nguyen (PER-019)*: `MATCH (:Person {name:'Sarah Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:USES_PHONE]->(ph:Phone)
WHERE p.name CONTAINS 'Nguyen'
RETURN DISTINCT ph.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:USES_PHONE {active: true}]->(ph:Phone)
WHERE p.name CONTAINS 'Nguyen'
RETURN DISTINCT ph.phone_number`
  AD predicted ambiguous: True | detected_types: ['entity', 'temporal']
  AD rationale: Two distinct Person nodes (PER-015 Michael Nguyen and PER-019 Sarah Nguyen) both match 'Nguyen' with equal confidence (entity ambiguity score 1.00), so the question cannot be resolved without disambiguation. Additionally, USES_PHONE carries active/from_date/to_date properties, meaning the question could refer to the currently active phone number or all historical phone numbers used, introducing a temporal ambiguity.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 1

### Q-101 — Where does James Whitfield live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *James Whitfield's residence.* — `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity', 'temporal']
  AD rationale: Two distinct Person nodes match the query: 'James Whitfield' (PER-007) and 'Michael Nguyen' (PER-015) both score 1.00, making it unclear which person is intended (entity ambiguity). Additionally, LIVES_AT carries active/from_date/to_date properties, so 'where does X live' is ambiguous between current residence (active:true) and all historical addresses (temporal ambiguity).
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-102 — Where does Lina Petrova live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Lina Petrova's residence.* — `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Lina Petrova'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The LIVES_AT relationship carries active/from_date/to_date properties, so 'where does Lina Petrova live' could mean her current address (active:true) or all addresses she has ever lived at. These two readings return different results, introducing temporal ambiguity despite the schema and entity scores both being 0.00.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-105 — Who owns the Ford Ranger?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-003.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Ford', model:'Ranger'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The OWNS relationship carries active/from_date/to_date properties, meaning there could be both current and historical owners. 'Who owns' could reasonably mean the current owner (active:true) or all past and present owners. Despite the schema linker returning a single candidate with score 1.00 (not distinguishing between filtered and unfiltered), this temporal ambiguity is inherent in the schema and the question does not specify whether current or historical ownership is intended.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-106 — What phone does Lina Petrova use?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Lina Petrova's phone usage.* — `MATCH (:Person {name:'Lina Petrova'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
- alternative gold interpretations:
  - *Current phone only*: `MATCH (:Person {name:'Lina Petrova'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  - *Including previous phone*: `MATCH (:Person {name:'Lina Petrova'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Lina Petrova'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The USES_PHONE relationship carries active/from_date/to_date properties, so 'does use' could mean the currently active phone ({active:true}) or all phones ever used historically. These two interpretations return different results, making the question temporally ambiguous despite the schema and entity scores being unambiguous.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 1

### Q-107 — Who uses phone number 0412 345 678?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *User of DEV-001.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0412 345 678'}) RETURN p.name`
- alternative gold interpretations:
  - *Current user only*: `MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0412 345 678'}) RETURN p.name`
  - *Including the previous user*: `MATCH (p:Person)-[:USES_PHONE]->(:Phone {phone_number:'0412 345 678'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:USES_PHONE]->(ph:Phone {phone_number:'0412 345 678'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone {phone_number: '0412 345 678'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The USES_PHONE relationship carries active/from_date/to_date properties, meaning the phone could have been used by multiple people over time. 'Who uses' is ambiguous between the current active user ({active:true}) and all historical users, which would return different results. The schema candidate distribution does not distinguish between these two temporal readings.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 1

### Q-108 — Who uses the phone 0478 444 555?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *User of DEV-008.* — `MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0478 444 555'}) RETURN p.name`
- alternative gold interpretations:
  - *Current user only*: `MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0478 444 555'}) RETURN p.name`
  - *Including the previous user*: `MATCH (p:Person)-[:USES_PHONE]->(:Phone {phone_number:'0478 444 555'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:USES_PHONE]->(ph:Phone {phone_number:'0478 444 555'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone {phone_number: '0478 444 555'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The USES_PHONE relationship carries active/from_date/to_date properties, meaning the phone could have been used by multiple people over time. 'Who uses' is ambiguous between the current user ({active:true}) and all historical users, which would return different results. Despite the schema and entity scores being 0.00, this temporal ambiguity is inherent in the schema design.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 1

### Q-112 — Where does Amir Hassan live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Amir Hassan's residence.* — `MATCH (:Person {name:'Amir Hassan'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Amir Hassan'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Amir Hassan'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Amir Hassan'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Amir Hassan'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The schema is unambiguous (LIVES_AT is the only relevant relationship, score 1.00) and the entity 'Amir Hassan' has a strong unique match (PER-011, score 1.00). However, LIVES_AT carries active/from_date/to_date properties, so 'where does Amir Hassan live' is temporally ambiguous: it could mean the current address ({active:true}) or all historical addresses. These two readings return different results. The secondary entity match (Hassan Ali, PER-022, score 0.86) is weak enough not to constitute genuine entity ambiguity given the exact name match on PER-011.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-113 — Where does Tyler Birch live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Tyler Birch's residence.* — `MATCH (:Person {name:'Tyler Birch'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Tyler Birch'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Tyler Birch'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Tyler Birch'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Tyler Birch'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The LIVES_AT relationship carries active/from_date/to_date properties, meaning Tyler Birch may have lived at multiple locations over time. 'Where does Tyler Birch live?' could mean their current residence (active:true) or all past and present addresses, and these two interpretations return different results. Despite the schema and entity scores both being 0.00, this temporal ambiguity is inherent in the schema design.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-114 — Where does Connor Doyle live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Connor Doyle's residence.* — `MATCH (:Person {name:'Connor Doyle'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Connor Doyle'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Connor Doyle'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Connor Doyle'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Connor Doyle'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The LIVES_AT relationship carries active/from_date/to_date properties, meaning Connor Doyle may have lived at multiple locations over time. 'Where does Connor Doyle live?' could mean their current residence (active:true) or all past and present addresses, which would return different results. Despite the schema and entity scores both being 0.00, the temporal dimension of LIVES_AT introduces ambiguity not captured by those signals.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-115 — Where does Sarah Nguyen live?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Sarah Nguyen's residence.* — `MATCH (:Person {name:'Sarah Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
- alternative gold interpretations:
  - *Current address only*: `MATCH (:Person {name:'Sarah Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Including historical addresses*: `MATCH (:Person {name:'Sarah Nguyen'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Sarah Nguyen'})-[:LIVES_AT]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Sarah Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The LIVES_AT relationship carries active/from_date/to_date properties, meaning Sarah Nguyen may have lived at multiple locations over time. 'Where does Sarah Nguyen live?' could mean her current residence (active:true) or all past and present addresses, and these two interpretations return different results. Despite the schema and entity scores being unambiguous, the temporal dimension of LIVES_AT introduces this ambiguity.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 1

### Q-117 — Who owns the Nissan Navara?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-005.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Nissan', model:'Navara'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'Nissan', model:'Navara'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The OWNS relationship carries active/from_date/to_date properties, meaning there could be both current and historical owners. 'Who owns' could reasonably mean the current owner (active:true) or all past and present owners, and these two interpretations return different results. Despite the schema linker returning a single unqualified OWNS edge (no temporal filter specified), the schema supports both readings and the question does not disambiguate between them.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-118 — Who owns the BMW 3 Series?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-009.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'BMW', model:'3 Series'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'BMW', model:'3 Series'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'BMW', model:'3 Series'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'BMW', model:'3 Series'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person)-[:OWNS {active:true}]->(v:Vehicle {make:'BMW', model:'3 Series'}) RETURN p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: Although the schema linker returns a single OWNS relationship with score 1.00, the OWNS relationship carries active/from_date/to_date properties, meaning 'who owns' could refer to the current owner (active:true) or all historical owners. The question does not specify whether it is asking about present or past ownership, making it temporally ambiguous despite the low schema ambiguity score.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 1

### Q-119 — What phone does Michael Nguyen use?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Michael Nguyen's phone usage.* — `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
- alternative gold interpretations:
  - *Current phone only*: `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  - *Including previous phone*: `MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Michael Nguyen'})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number`

**C3 (disambiguation_enhanced)** — correct=True, matches_any=True, failure_mode=None
  cypher: `MATCH (p:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The USES_PHONE relationship carries active/from_date/to_date properties, so 'does use' could mean the currently active phone ({active:true}) or all phones ever used historically. These two interpretations return different results. Schema and entity scores are both 0.00, but the temporal ambiguity is inherent in the question phrasing.
  committed mapping: {'rel_1': 'USES_PHONE'} | resolution_mode: automated | n_mappings_tried: 1

## Case studies — regressed (C2 right, C3 wrong)

*(none)*

## Case studies — both_wrong sample (up to 3 per ambiguity_type, 15 of 55 total)

Both conditions fail these — the module neither helps nor hurts, so this is where
the pipeline's remaining ceiling lives (QG/schema-linking capability, not
disambiguation). Sampled deterministically by sorted question_id, grouped by type.

### Q-062 — Where does Kim currently live?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *The current address of the person surnamed Kim — ambiguous.* — `MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Kim' RETURN l.address`
- alternative gold interpretations:
  - *Rachel Kim (PER-006)*: `MATCH (:Person {name:'Rachel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  - *Daniel Kim (PER-009)*: `MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes match 'Kim' with equal confidence (Rachel Kim PER-006 and Daniel Kim PER-009, both at 1.00), and the question provides no further context to disambiguate which Kim is intended. The schema is unambiguous (LIVES_AT is the only relevant relationship), and 'currently' clearly resolves the temporal aspect to active=true, but the entity ambiguity means the query would return different locations depending on which Kim is selected.
  committed mapping: {'rel_1': 'LIVES_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-064 — Which incidents is Chen connected to?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *Incidents linked to the person surnamed Chen — ambiguous.* — `MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Chen' RETURN DISTINCT i.incident_id`
- alternative gold interpretations:
  - *David Chen (PER-001, investigating officer)*: `MATCH (:Person {name:'David Chen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id`
  - *Wei Chen (PER-012, suspect)*: `MATCH (:Person {name:'Wei Chen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) WHERE p.name CONTAINS 'Chen' RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Chen'})-[:SUSPECTED_OF]->(i:Incident) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes match 'Chen' with equal confidence (David Chen PER-001 and Wei Chen PER-012, both at 1.00), and the question provides no further information to disambiguate between them. Each would return a different set of incidents, making the result dependent on which Chen is intended.
  committed mapping: {'rel_1': 'SUSPECTED_OF'} | resolution_mode: automated | n_mappings_tried: 2

### Q-065 — Which incidents is Smith connected to?

- ambiguity_type (gold): **entity** | is_ambiguous (gold): True
- default_interp: *Incidents linked to the person surnamed Smith — ambiguous.* — `MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Smith' RETURN DISTINCT i.incident_id`
- alternative gold interpretations:
  - *James Smith (PER-016, suspect)*: `MATCH (:Person {name:'James Smith'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id`
  - *Laura Smith (PER-032, witness)*: `MATCH (:Person {name:'Laura Smith'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)
WHERE p.name CONTAINS 'Smith'
RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Smith'})-[:SUSPECTED_OF]->(i:Incident) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Two distinct Person nodes match 'Smith' with equal confidence (James Smith PER-016 and Laura Smith PER-032, both at 1.00), and the question provides no additional context to disambiguate between them. Each would return a different set of incidents, making the result dependent on which Smith is intended.
  committed mapping: {'rel_1': 'SUSPECTED_OF'} | resolution_mode: automated | n_mappings_tried: 2

### Q-081 — Tell me about the suspects in the Lake Street drug offence.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about INC-007's suspects.* — `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`
- alternative gold interpretations:
  - *Return the count of suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN count(p) AS n`
  - *Return the list of suspects' names*: `MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-007'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (l:Location {address:'Lake Street'})<-[:OCCURRED_AT]-(i:Incident {crime_type:'drug_offence'})<-[:SUSPECTED_OF]-(p:Person) RETURN DISTINCT p.name, p.alias, p.date_of_birth, p.gender`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'drug_offence'})-[:OCCURRED_AT]->(l:Location {address:'Lake Street'}) RETURN DISTINCT p.person_id, p.name, p.alias, p.date_of_birth, p.gender`
  AD predicted ambiguous: True | detected_types: ['intent']
  AD rationale: 'Tell me about' is underspecified in terms of what to return: valid readings could include returning just the suspects' names, all their properties, their associated incidents, their addresses, their vehicles, or all paths connecting them to the incident. Each interpretation requires a different RETURN clause, making this an intent ambiguity despite the schema and entity being unambiguous.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'rel_2': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-082 — What about the incidents in Northbridge?

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Information about the Northbridge incidents.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`
- alternative gold interpretations:
  - *Return the count of incidents*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN count(i) AS n`
  - *Return the list of incident details*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Three distinct Location nodes (LOC-001, LOC-002, LOC-006) all match 'Northbridge' with perfect scores, and the question provides no further context to disambiguate which Northbridge is meant. Each node may be associated with different incidents, so the query result depends entirely on which location is selected. The schema mapping is unambiguous (OCCURRED_AT with score 1.00).
  committed mapping: {'rel_1': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-084 — Show incidents in Perth.

- ambiguity_type (gold): **intent** | is_ambiguous (gold): True
- default_interp: *Incidents associated with Perth.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
- alternative gold interpretations:
  - *Only incidents whose suburb is exactly 'Perth'*: `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id`
  - *All incidents in the Perth metro area (any suburb)*: `MATCH (i:Incident) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Perth'}) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.location_id IN ['LOC-005', 'LOC-008', 'LOC-014'] RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The schema mapping is unambiguous (all candidates score 1.00 on a single relationship and node types), but 'Perth' matches four distinct Location nodes (LOC-003, LOC-005, LOC-008, LOC-014), including 'West Perth' and three separate 'Perth' entries. The question does not disambiguate which location is intended, so the query result depends on which node(s) are used, yielding potentially different sets of incidents.
  committed mapping: {'rel_1': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-043 — List everyone linked to the fraud on St Georges Terrace.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-005.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-005'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location {address:'St Georges Terrace'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[r]->(i:Incident)-[:OCCURRED_AT]->(l:Location {address:'St Georges Terrace'}) WHERE i.crime_type = 'fraud' RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is entirely concentrated on SUSPECTED_OF and OCCURRED_AT (both at score 1.00), with no spread across alternative relationship types. The entity 'St Georges Terrace' resolves unambiguously to a single Location node (LOC-008, score 1.00). The phrase 'linked to' in this context, combined with the fraud incident type, maps cleanly to SUSPECTED_OF without meaningful competition from WITNESSED, VICTIM_OF, or INVESTIGATES. All reasonable interpretations lead to the same query structure and result.
  committed mapping: {'rel_2': 'OCCURRED_AT', 'node_1': 'Person'} | resolution_mode: automated | n_mappings_tried: 2

### Q-044 — Who took part in the assault in Scarborough?

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-009.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-009'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only the suspect*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-009'}) RETURN DISTINCT p.name`
  - *Only the witness*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-009'}) RETURN DISTINCT p.name`
  - *Only the investigating officer*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-009'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(l:Location {suburb:'Scarborough'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(l:Location {suburb:'Scarborough'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is entirely concentrated on SUSPECTED_OF and OCCURRED_AT (both at 1.00), the entity 'Scarborough' resolves uniquely to LOC-011, and 'took part in' maps cleanly to the suspect role. All reasonable interpretations lead to the same query: find Persons SUSPECTED_OF an Incident that OCCURRED_AT Scarborough. No schema, entity, intent, or temporal ambiguity is present.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'rel_2': 'OCCURRED_AT', 'node_1': 'Person', 'node_2': 'Incident', 'node_3': 'Location'} | resolution_mode: automated | n_mappings_tried: 1

### Q-045 — Show the people associated with the drug offence on Lake Street.

- ambiguity_type (gold): **schema** | is_ambiguous (gold): True
- default_interp: *Any role edge (suspect, witness, victim, or investigator) from a Person to INC-007.* — `MATCH (p:Person)-[r]->(i:Incident {incident_id:'INC-007'}) RETURN DISTINCT p.name`
- alternative gold interpretations:
  - *Only suspects*: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id:'INC-007'}) RETURN DISTINCT p.name`
  - *Only witnesses*: `MATCH (p:Person)-[:WITNESSED]->(i:Incident {incident_id:'INC-007'}) RETURN DISTINCT p.name`
  - *Only investigating officers*: `MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {incident_id:'INC-007'}) RETURN DISTINCT p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (l:Location {address:'Lake Street'})<-[:OCCURRED_AT]-(i:Incident {crime_type:'drug_offence'})<-[:SUSPECTED_OF]-(p:Person) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'drug_offence'})-[:OCCURRED_AT]->(l:Location {address:'Lake Street'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The schema candidate distribution is unambiguous: all candidates score 1.00 with no spread. The entity lookup uniquely resolves 'Lake Street' to LOC-006. The phrase 'associated with the drug offence' maps cleanly to (Person)-[:SUSPECTED_OF]->(Incident) in context (the schema linker confirms this), and 'people associated with' in this phrasing refers to suspects of the incident rather than the ASSOCIATED_WITH person-to-person relationship (which the schema linker also scores at 1.00 but as a chained path pattern). However, on reflection, 'associated with' could map to either the (Person)-[:ASSOCIATED_WITH]->(Person) edge or the (Person)-[:SUSPECTED_OF]->(Incident) edge, but the schema linker has resolved this into a single coherent query pattern (chaining both), and both scores are 1.00 with no ambiguity signal. All reasonable interpretations converge on the same result set.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'rel_2': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-103 — What vehicle does Ricky Santos own?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Ricky Santos's vehicle ownership.* — `MATCH (:Person {name:'Ricky Santos'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`
- alternative gold interpretations:
  - *Currently owned vehicles only*: `MATCH (:Person {name:'Ricky Santos'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`
  - *Including vehicles previously owned*: `MATCH (:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v.vehicle_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v.make, v.model, v.plate, v.colour`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Ricky Santos'})-[:OWNS]->(v:Vehicle) RETURN v.make, v.model, v.plate, v.colour`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The OWNS relationship carries active/from_date/to_date properties, so 'does own' could mean currently active ownership only or all vehicles ever owned. The schema linker returned a single OWNS edge without specifying {active:true}, leaving the temporal scope unresolved. These two readings would return different results if Ricky Santos has previously owned vehicles he no longer owns.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-104 — Who owns the Holden Commodore?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Owner of VEH-001.* — `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`
- alternative gold interpretations:
  - *Current owner only*: `MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`
  - *Including the previous owner*: `MATCH (p:Person)-[:OWNS]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:OWNS]->(v:Vehicle {model:'Holden Commodore'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The OWNS relationship carries active/from_date/to_date properties, meaning there could be both current and historical owners. 'Who owns' could reasonably mean the current active owner only ({active:true}) or all persons who have ever owned the vehicle, returning different results. Despite the schema linker scoring OWNS at 1.00 without temporal filtering, this temporal ambiguity is inherent in the schema design.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-109 — Who is Tyler Birch associated with?

- ambiguity_type (gold): **temporal** | is_ambiguous (gold): True
- default_interp: *Tyler Birch's associations.* — `MATCH (:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name`
- alternative gold interpretations:
  - *Current associates only*: `MATCH (:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name`
  - *Including former associates*: `MATCH (:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH]-(o:Person) RETURN o.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH]->(p2:Person) RETURN DISTINCT p2.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=True, failure_mode=valid_non_default
  cypher: `MATCH (p:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH]-(p2:Person) RETURN DISTINCT p2.name`
  AD predicted ambiguous: True | detected_types: ['temporal']
  AD rationale: The ASSOCIATED_WITH relationship carries active/from_date/to_date properties, meaning the question could refer to current associations (active:true) or all historical associations. The schema and entity are unambiguous (perfect scores for both), but 'associated with' does not specify whether current or past associations are intended, and these two readings would return different sets of people.
  committed mapping: {'rel_1': 'ASSOCIATED_WITH'} | resolution_mode: automated | n_mappings_tried: 1

### Q-007 — Which vehicle does James Whitfield currently own?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *The vehicle on James Whitfield's active OWNS edge.* — `MATCH (:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN DISTINCT v.plate, v.make, v.model, v.colour`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.make, v.model, v.plate, v.colour`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: The entity lookup returns two distinct Person nodes matching 'James Whitfield' with equal confidence (PER-007 and PER-015), making it impossible to determine which person the question refers to. The schema is unambiguous (OWNS relationship, score 1.00), and 'currently' clearly specifies active ownership, but the entity ambiguity means the query would return different vehicles depending on which node is selected.
  committed mapping: {'rel_1': 'OWNS'} | resolution_mode: automated | n_mappings_tried: 2

### Q-011 — List all incidents that occurred in Northbridge.

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Incidents with an OCCURRED_AT edge to a Northbridge location.* — `MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN DISTINCT i.incident_id, i.crime_type, i.date, i.status`
  AD predicted ambiguous: True | detected_types: ['entity']
  AD rationale: Three distinct Location nodes (LOC-001, LOC-002, LOC-006) all match 'Northbridge' with perfect scores, and the question provides no further detail to disambiguate between them. Each location may have different incidents linked via OCCURRED_AT, so the query result depends on which Northbridge node is intended.
  committed mapping: {'rel_1': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2

### Q-012 — Who is suspected of the robbery on William Street?

- ambiguity_type (gold): **none** | is_ambiguous (gold): False
- default_interp: *Suspects of the robbery that OCCURRED_AT 142 William Street (INC-001).* — `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'William Street' RETURN p.name`

**C2 (schema_grounded)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(l:Location {address:'William Street'}) RETURN DISTINCT p.name`

**C3 (disambiguation_enhanced)** — correct=False, matches_any=False, failure_mode=wrong_result
  cypher: `MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(l:Location {address:'William Street'}) RETURN DISTINCT p.name`
  AD predicted ambiguous: False | detected_types: []
  AD rationale: The question maps cleanly to a single Cypher pattern: (Person)-[:SUSPECTED_OF]->(Incident)-[:OCCURRED_AT]->(Location). All schema candidates score 1.00 with no spread, 'William Street' resolves unambiguously to a single Location node (LOC-001), and the intent is clearly to return the Person nodes. No temporal, schema, entity, or intent ambiguity is present.
  committed mapping: {'rel_1': 'SUSPECTED_OF', 'rel_2': 'OCCURRED_AT'} | resolution_mode: automated | n_mappings_tried: 2
