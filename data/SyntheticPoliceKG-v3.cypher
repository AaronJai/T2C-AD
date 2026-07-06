// ============================================================
// KG Schema v3 — Concise POLE Synthetic Dataset
// Policing Knowledge Graph (POLE-inspired)
// Honours Research: Ambiguity-Aware Text-to-Cypher
//
// Rationale (spec 7.1): v2's 28 relationship types included accidental
// near-synonyms (RELATES_TO/RELATED_TO/LINKED_TO; seven *_AT edges;
// PARTICIPATED_IN/INVOLVED_IN) that deflated schema-linking coverage without
// testing disambiguation. v3 keeps ONLY designed ambiguity:
//   - the four Person->Incident role edges (schema ambiguity)
//   - duplicate surnames / shared given names / alias collisions (entity)
//   - dated LIVES_AT / OWNS / USES_PHONE / ASSOCIATED_WITH edges (temporal)
// v2 stays frozen as the recorded baseline (job 957276).
//
// Target volumes:
//   40 Persons, 12 Incidents, 4 Cases, 16 Locations,
//   10 Vehicles, 14 Phones  =>  96 nodes
//
// Inventory:
//   6 node labels    : Person, Incident, Case, Location, Vehicle, Phone
//   11 relationship types :
//     SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES,      (role — schema ambiguity)
//     CONTAINS, OCCURRED_AT,                                 (structural)
//     LIVES_AT, OWNS, USES_PHONE, ASSOCIATED_WITH,           (dated — temporal ambiguity)
//     CALLED                                                 (Phone->Phone)
//
// Design principles retained from v2:
//   - Cross-role persons (suspect in one incident, witness in another)
//   - Historical temporal edges (LIVES_AT, OWNS, USES_PHONE, ASSOCIATED_WITH)
//   - Realistic Perth metro geography
//   - NO Person.role property: roles are expressed only by the four role
//     edges, so there is exactly one query path per role question.
// ============================================================


// ────────────────────────────────────────────────────────────
// 1. CONSTRAINTS & INDEXES
// ────────────────────────────────────────────────────────────

CREATE CONSTRAINT person_id_unique   IF NOT EXISTS FOR (p:Person)   REQUIRE p.person_id IS UNIQUE;
CREATE CONSTRAINT incident_id_unique IF NOT EXISTS FOR (i:Incident) REQUIRE i.incident_id IS UNIQUE;
CREATE CONSTRAINT case_id_unique     IF NOT EXISTS FOR (c:Case)     REQUIRE c.case_id IS UNIQUE;
CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE;
CREATE CONSTRAINT vehicle_id_unique  IF NOT EXISTS FOR (v:Vehicle)  REQUIRE v.vehicle_id IS UNIQUE;
CREATE CONSTRAINT device_id_unique   IF NOT EXISTS FOR (d:Phone)    REQUIRE d.device_id IS UNIQUE;

CREATE INDEX person_name_idx     IF NOT EXISTS FOR (p:Person)   ON (p.name);
CREATE INDEX person_alias_idx    IF NOT EXISTS FOR (p:Person)   ON (p.alias);
CREATE INDEX incident_type_idx   IF NOT EXISTS FOR (i:Incident) ON (i.crime_type);
CREATE INDEX incident_status_idx IF NOT EXISTS FOR (i:Incident) ON (i.status);
CREATE INDEX case_status_idx     IF NOT EXISTS FOR (c:Case)     ON (c.status);
CREATE INDEX location_suburb_idx IF NOT EXISTS FOR (l:Location) ON (l.suburb);
CREATE INDEX vehicle_plate_idx   IF NOT EXISTS FOR (v:Vehicle)  ON (v.plate);


// ────────────────────────────────────────────────────────────
// 2. NODES — Person (40)
//   Properties: person_id, name, alias, date_of_birth, gender
//   Entity-ambiguity seeds baked in:
//     - Duplicate surnames (6 clusters): Chen {001,012}, Tran {002,031},
//       Kim {006,009}, Nguyen {015,019}, Smith {016,032}, Bennett {024,025}
//     - Shared given names: James {004,007,016}, Sarah {019,025}
//     - Alias collisions (alias == another person's given name):
//       012 Wei Chen alias 'David' (== 001 David Chen); 015 Michael Nguyen
//       alias 'James' (== 004/007/016)
// ────────────────────────────────────────────────────────────

// Investigating officers (6)
CREATE (:Person {person_id:'PER-V3-001', name:'David Chen',      alias:null,          date_of_birth:date('1978-11-03'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-002', name:'Megan Tran',      alias:null,          date_of_birth:date('1986-07-12'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-003', name:'Priya Sharma',    alias:null,          date_of_birth:date('1990-10-05'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-004', name:'James Kowalski',  alias:null,          date_of_birth:date('1975-02-18'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-005', name:'Tom Elliot',      alias:null,          date_of_birth:date('1983-12-20'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-006', name:'Rachel Kim',      alias:null,          date_of_birth:date('1988-04-17'), gender:'female'});

// Suspects (12)
CREATE (:Person {person_id:'PER-V3-007', name:'James Whitfield', alias:'Jimmy',       date_of_birth:date('1985-06-14'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-008', name:'Lina Petrova',    alias:null,          date_of_birth:date('1988-09-05'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-009', name:'Daniel Kim',      alias:'Danny',       date_of_birth:date('1991-03-30'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-010', name:'Tyler Birch',     alias:'Birchy',      date_of_birth:date('1995-08-22'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-011', name:'Amir Hassan',     alias:null,          date_of_birth:date('1982-01-11'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-012', name:'Wei Chen',        alias:'David',       date_of_birth:date('1989-05-17'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-013', name:'Ricky Santos',    alias:'Rico',        date_of_birth:date('1989-11-28'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-014', name:'Connor Doyle',    alias:null,          date_of_birth:date('1997-04-03'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-015', name:'Michael Nguyen',  alias:'James',       date_of_birth:date('1990-07-14'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-016', name:'James Smith',     alias:null,          date_of_birth:date('1984-02-09'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-017', name:'Jade Wu',         alias:null,          date_of_birth:date('1993-05-17'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-018', name:'Nina Orlov',      alias:null,          date_of_birth:date('1992-11-08'), gender:'female'});

// Victims (8)
CREATE (:Person {person_id:'PER-V3-019', name:'Sarah Nguyen',    alias:null,          date_of_birth:date('1990-03-22'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-020', name:'Marcus Webb',     alias:null,          date_of_birth:date('1972-09-15'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-021', name:'Emily Ford',      alias:null,          date_of_birth:date('1998-12-01'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-022', name:'Hassan Ali',      alias:null,          date_of_birth:date('1965-06-30'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-023', name:'Thomas Grant',    alias:null,          date_of_birth:date('1987-07-08'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-024', name:'Sophie Bennett',  alias:null,          date_of_birth:date('1999-11-30'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-025', name:'Sarah Bennett',   alias:null,          date_of_birth:date('1994-02-14'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-026', name:'Omar Farah',      alias:null,          date_of_birth:date('1976-01-05'), gender:'male'});

// Witnesses (6)
CREATE (:Person {person_id:'PER-V3-027', name:'Mark Thompson',   alias:'Thommo',      date_of_birth:date('1992-01-17'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-028', name:'Karen Liu',       alias:null,          date_of_birth:date('1970-05-23'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-029', name:'Brian Walsh',     alias:null,          date_of_birth:date('1968-08-09'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-030', name:'Deepa Nair',      alias:null,          date_of_birth:date('1996-04-11'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-031', name:'Kevin Tran',      alias:null,          date_of_birth:date('1994-10-25'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-032', name:'Laura Smith',     alias:null,          date_of_birth:date('1991-06-12'), gender:'female'});

// Persons of interest / associates (8)
CREATE (:Person {person_id:'PER-V3-033', name:'Anton Maric',     alias:'The Broker',  date_of_birth:date('1979-12-02'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-034', name:'Fiona Gallagher', alias:null,          date_of_birth:date('1985-03-19'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-035', name:'Yusuf Abdi',      alias:null,          date_of_birth:date('1990-08-14'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-036', name:'Leon Park',       alias:null,          date_of_birth:date('1988-06-06'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-037', name:'Ben Murray',      alias:null,          date_of_birth:date('1991-02-28'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-038', name:'Lisa Chang',      alias:null,          date_of_birth:date('1987-08-13'), gender:'female'});
CREATE (:Person {person_id:'PER-V3-039', name:'Steven Yeo',      alias:null,          date_of_birth:date('1984-10-25'), gender:'male'});
CREATE (:Person {person_id:'PER-V3-040', name:'Michelle Torres', alias:null,          date_of_birth:date('1993-09-21'), gender:'female'});


// ────────────────────────────────────────────────────────────
// 3. NODES — Incident (12)
//   Properties: incident_id, crime_type, date, status
// ────────────────────────────────────────────────────────────

CREATE (:Incident {incident_id:'INC-V3-001', crime_type:'robbery',      date:date('2026-01-15'), status:'under_investigation'});
CREATE (:Incident {incident_id:'INC-V3-002', crime_type:'drug_offence', date:date('2026-02-03'), status:'open'});
CREATE (:Incident {incident_id:'INC-V3-003', crime_type:'assault',      date:date('2026-02-20'), status:'under_investigation'});
CREATE (:Incident {incident_id:'INC-V3-004', crime_type:'burglary',     date:date('2025-11-10'), status:'closed'});
CREATE (:Incident {incident_id:'INC-V3-005', crime_type:'fraud',        date:date('2026-01-28'), status:'open'});
CREATE (:Incident {incident_id:'INC-V3-006', crime_type:'homicide',     date:date('2026-03-01'), status:'under_investigation'});
CREATE (:Incident {incident_id:'INC-V3-007', crime_type:'drug_offence', date:date('2026-02-15'), status:'under_investigation'});
CREATE (:Incident {incident_id:'INC-V3-008', crime_type:'robbery',      date:date('2026-02-28'), status:'open'});
CREATE (:Incident {incident_id:'INC-V3-009', crime_type:'assault',      date:date('2025-12-20'), status:'closed'});
CREATE (:Incident {incident_id:'INC-V3-010', crime_type:'traffic',      date:date('2026-01-05'), status:'closed'});
CREATE (:Incident {incident_id:'INC-V3-011', crime_type:'burglary',     date:date('2025-10-15'), status:'cold'});
CREATE (:Incident {incident_id:'INC-V3-012', crime_type:'fraud',        date:date('2026-02-10'), status:'under_investigation'});


// ────────────────────────────────────────────────────────────
// 4. NODES — Case (4)
//   Properties: case_id, case_name, status, opened_date
// ────────────────────────────────────────────────────────────

CREATE (:Case {case_id:'CASE-V3-001', case_name:'Operation Ironside — Northbridge Series', status:'open', opened_date:date('2026-01-16')});
CREATE (:Case {case_id:'CASE-V3-002', case_name:'Operation Trident — Drug Network',        status:'open', opened_date:date('2026-02-05')});
CREATE (:Case {case_id:'CASE-V3-003', case_name:'Operation Cerberus — Financial Crimes',   status:'open', opened_date:date('2026-02-01')});
CREATE (:Case {case_id:'CASE-V3-004', case_name:'Operation Sentinel — Midland Taskforce',  status:'open', opened_date:date('2026-03-01')});


// ────────────────────────────────────────────────────────────
// 5. NODES — Location (16)
//   Properties: location_id, address, suburb, postcode
//   Location collision seed: 'Albany Highway' appears in TWO suburbs —
//   LOC-V3-009 (Cannington) and LOC-V3-013 (Victoria Park).
// ────────────────────────────────────────────────────────────

CREATE (:Location {location_id:'LOC-V3-001', address:'142 William Street',       suburb:'Northbridge',   postcode:'6003'});
CREATE (:Location {location_id:'LOC-V3-002', address:'27 James Street',          suburb:'Northbridge',   postcode:'6003'});
CREATE (:Location {location_id:'LOC-V3-003', address:'8 Harvest Terrace',        suburb:'West Perth',    postcode:'6005'});
CREATE (:Location {location_id:'LOC-V3-004', address:'310 Great Eastern Highway', suburb:'Midland',      postcode:'6056'});
CREATE (:Location {location_id:'LOC-V3-005', address:'55 Beaufort Street',       suburb:'Perth',         postcode:'6000'});
CREATE (:Location {location_id:'LOC-V3-006', address:'88 Lake Street',           suburb:'Northbridge',   postcode:'6003'});
CREATE (:Location {location_id:'LOC-V3-007', address:'12 South Terrace',         suburb:'Fremantle',     postcode:'6160'});
CREATE (:Location {location_id:'LOC-V3-008', address:'200 St Georges Terrace',   suburb:'Perth',         postcode:'6000'});
CREATE (:Location {location_id:'LOC-V3-009', address:'45 Albany Highway',        suburb:'Cannington',    postcode:'6107'});
CREATE (:Location {location_id:'LOC-V3-010', address:'15 Morrison Road',         suburb:'Midland',       postcode:'6056'});
CREATE (:Location {location_id:'LOC-V3-011', address:'3 Scarborough Beach Road', suburb:'Scarborough',   postcode:'6019'});
CREATE (:Location {location_id:'LOC-V3-012', address:'80 Joondalup Drive',       suburb:'Joondalup',     postcode:'6027'});
CREATE (:Location {location_id:'LOC-V3-013', address:'22 Albany Highway',        suburb:'Victoria Park', postcode:'6100'});
CREATE (:Location {location_id:'LOC-V3-014', address:'100 Hay Street',           suburb:'Perth',         postcode:'6000'});
CREATE (:Location {location_id:'LOC-V3-015', address:'7 Marine Parade',          suburb:'Cottesloe',     postcode:'6011'});
CREATE (:Location {location_id:'LOC-V3-016', address:'35 Walcott Street',        suburb:'Mt Lawley',     postcode:'6050'});


// ────────────────────────────────────────────────────────────
// 6. NODES — Vehicle (10)
//   Properties: vehicle_id, plate, make, model, colour
// ────────────────────────────────────────────────────────────

CREATE (:Vehicle {vehicle_id:'VEH-V3-001', plate:'1GBH 924', make:'Holden',     model:'Commodore', colour:'black'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-002', plate:'1DLR 337', make:'Toyota',     model:'HiLux',     colour:'white'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-003', plate:'1FRD 450', make:'Ford',       model:'Ranger',    colour:'blue'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-004', plate:'1HYN 812', make:'Hyundai',    model:'i30',       colour:'silver'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-005', plate:'1NIS 203', make:'Nissan',     model:'Navara',    colour:'red'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-006', plate:'1MAZ 667', make:'Mazda',      model:'3',         colour:'grey'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-007', plate:'1TOY 115', make:'Toyota',     model:'Camry',     colour:'white'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-008', plate:'1MIT 908', make:'Mitsubishi', model:'Triton',    colour:'black'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-009', plate:'1BMW 321', make:'BMW',        model:'3 Series',  colour:'blue'});
CREATE (:Vehicle {vehicle_id:'VEH-V3-010', plate:'1HOL 555', make:'Holden',     model:'Colorado',  colour:'white'});


// ────────────────────────────────────────────────────────────
// 7. NODES — Phone (14)
//   Properties: device_id, phone_number
// ────────────────────────────────────────────────────────────

CREATE (:Phone {device_id:'DEV-V3-001', phone_number:'0412 345 678'});
CREATE (:Phone {device_id:'DEV-V3-002', phone_number:'0423 987 654'});
CREATE (:Phone {device_id:'DEV-V3-003', phone_number:'0401 111 222'});
CREATE (:Phone {device_id:'DEV-V3-004', phone_number:'0434 555 888'});
CREATE (:Phone {device_id:'DEV-V3-005', phone_number:'0445 222 333'});
CREATE (:Phone {device_id:'DEV-V3-006', phone_number:'0456 777 999'});
CREATE (:Phone {device_id:'DEV-V3-007', phone_number:'0467 333 444'});
CREATE (:Phone {device_id:'DEV-V3-008', phone_number:'0478 444 555'});
CREATE (:Phone {device_id:'DEV-V3-009', phone_number:'0489 666 111'});
CREATE (:Phone {device_id:'DEV-V3-010', phone_number:'0490 888 777'});
CREATE (:Phone {device_id:'DEV-V3-011', phone_number:'0411 999 000'});
CREATE (:Phone {device_id:'DEV-V3-012', phone_number:'0422 000 111'});
CREATE (:Phone {device_id:'DEV-V3-013', phone_number:'0433 222 111'});
CREATE (:Phone {device_id:'DEV-V3-014', phone_number:'0455 333 222'});


// ════════════════════════════════════════════════════════════
// RELATIONSHIPS
// ════════════════════════════════════════════════════════════


// ────────────────────────────────────────────────────────────
// 8. Person → Incident role edges
//    SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES
//    Schema-ambiguity seed: for every incident, the suspect / witness /
//    investigator sets are non-empty and pairwise DIFFERENT, so the three
//    "connected/involved" interpretations return different rows.
//    Cross-role persons:
//      PER-V3-009 (Daniel Kim): SUSPECTED_OF INC-002/003/006 | WITNESSED INC-009
//      PER-V3-019 (Sarah Nguyen): VICTIM_OF INC-001 | WITNESSED INC-008
// ────────────────────────────────────────────────────────────

// INC-V3-001: robbery, Northbridge (3 suspects, 2 witnesses, 1 victim, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-007'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-012'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-015'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-027'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-028'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-019'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-001'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-003'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-002: drug_offence, Midland (2 suspects, 1 witness, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-009'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-013'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-031'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-002'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-005'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-003: assault, Northbridge (1 suspect, 2 witnesses, 1 victim, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-009'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-021'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-029'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-030'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-001'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-002'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-004: burglary, Fremantle (1 suspect, 1 witness, 1 victim, 1 investigator)
MATCH (p:Person {person_id:'PER-V3-014'}), (i:Incident {incident_id:'INC-V3-004'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-020'}), (i:Incident {incident_id:'INC-V3-004'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-029'}), (i:Incident {incident_id:'INC-V3-004'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-004'}), (i:Incident {incident_id:'INC-V3-004'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-005: fraud, Perth CBD (2 suspects, 1 witness, 1 victim, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-011'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-017'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-023'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-032'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-003'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-005'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-006: homicide, Cannington (2 suspects, 1 witness, 1 victim, 3 investigators)
MATCH (p:Person {person_id:'PER-V3-009'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-010'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-022'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-029'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-004'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-003'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-005'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-007: drug_offence, Northbridge Lake St (3 suspects, 2 witnesses, 1 investigator)
MATCH (p:Person {person_id:'PER-V3-007'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-008'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-018'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-028'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-037'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-002'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-008: robbery, Midland (1 suspect, 1 witness [cross-role], 1 victim, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-010'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-024'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-019'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-002'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-003'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-009: assault, Scarborough (1 suspect, 1 witness [cross-role Kim], 1 victim, 1 investigator)
MATCH (p:Person {person_id:'PER-V3-013'}), (i:Incident {incident_id:'INC-V3-009'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-025'}), (i:Incident {incident_id:'INC-V3-009'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-009'}), (i:Incident {incident_id:'INC-V3-009'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-005'}), (i:Incident {incident_id:'INC-V3-009'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-010: traffic, Joondalup (1 suspect, 1 witness, 1 victim, 1 investigator)
MATCH (p:Person {person_id:'PER-V3-014'}), (i:Incident {incident_id:'INC-V3-010'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-026'}), (i:Incident {incident_id:'INC-V3-010'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-039'}), (i:Incident {incident_id:'INC-V3-010'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-003'}), (i:Incident {incident_id:'INC-V3-010'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-011: burglary, Victoria Park, cold (1 suspect, 1 witness, 1 victim, 1 investigator)
MATCH (p:Person {person_id:'PER-V3-016'}), (i:Incident {incident_id:'INC-V3-011'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-023'}), (i:Incident {incident_id:'INC-V3-011'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-038'}), (i:Incident {incident_id:'INC-V3-011'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-004'}), (i:Incident {incident_id:'INC-V3-011'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-V3-012: fraud, Perth CBD (2 suspects, 1 witness, 1 victim, 2 investigators)
MATCH (p:Person {person_id:'PER-V3-011'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-034'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-020'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-V3-032'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-V3-006'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-V3-001'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (p)-[:INVESTIGATES]->(i);


// ────────────────────────────────────────────────────────────
// 9. Case → Incident (CONTAINS)
// ────────────────────────────────────────────────────────────

MATCH (c:Case {case_id:'CASE-V3-001'}), (i:Incident {incident_id:'INC-V3-001'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-001'}), (i:Incident {incident_id:'INC-V3-003'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-001'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-002'}), (i:Incident {incident_id:'INC-V3-002'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-002'}), (i:Incident {incident_id:'INC-V3-007'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-003'}), (i:Incident {incident_id:'INC-V3-005'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-003'}), (i:Incident {incident_id:'INC-V3-012'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-004'}), (i:Incident {incident_id:'INC-V3-006'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-V3-004'}), (i:Incident {incident_id:'INC-V3-008'}) CREATE (c)-[:CONTAINS]->(i);


// ────────────────────────────────────────────────────────────
// 10. Incident → Location (OCCURRED_AT)
// ────────────────────────────────────────────────────────────

MATCH (i:Incident {incident_id:'INC-V3-001'}), (l:Location {location_id:'LOC-V3-001'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-002'}), (l:Location {location_id:'LOC-V3-004'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-003'}), (l:Location {location_id:'LOC-V3-002'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-004'}), (l:Location {location_id:'LOC-V3-007'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-005'}), (l:Location {location_id:'LOC-V3-008'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-006'}), (l:Location {location_id:'LOC-V3-009'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-007'}), (l:Location {location_id:'LOC-V3-006'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-008'}), (l:Location {location_id:'LOC-V3-010'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-009'}), (l:Location {location_id:'LOC-V3-011'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-010'}), (l:Location {location_id:'LOC-V3-012'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-011'}), (l:Location {location_id:'LOC-V3-013'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-V3-012'}), (l:Location {location_id:'LOC-V3-014'}) CREATE (i)-[:OCCURRED_AT]->(l);


// ────────────────────────────────────────────────────────────
// 11. Person → Location (LIVES_AT) — temporal
//     Every Person has ≥1 LIVES_AT (current, active:true).
//     9 persons moved house (a prior active:false row): temporal seed.
// ────────────────────────────────────────────────────────────

// Current residences (active:true) — all 40 persons
MATCH (p:Person {person_id:'PER-V3-001'}), (l:Location {location_id:'LOC-V3-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-05-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-002'}), (l:Location {location_id:'LOC-V3-014'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-02-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-003'}), (l:Location {location_id:'LOC-V3-008'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-09-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-004'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2019-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-005'}), (l:Location {location_id:'LOC-V3-003'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-006'}), (l:Location {location_id:'LOC-V3-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-007'}), (l:Location {location_id:'LOC-V3-003'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-008'}), (l:Location {location_id:'LOC-V3-001'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-009'}), (l:Location {location_id:'LOC-V3-009'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-07-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-010'}), (l:Location {location_id:'LOC-V3-010'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-011'}), (l:Location {location_id:'LOC-V3-015'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-012'}), (l:Location {location_id:'LOC-V3-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-09-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-013'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-02-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-014'}), (l:Location {location_id:'LOC-V3-012'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-015'}), (l:Location {location_id:'LOC-V3-006'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-05-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-016'}), (l:Location {location_id:'LOC-V3-013'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-11-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-017'}), (l:Location {location_id:'LOC-V3-008'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-04-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-018'}), (l:Location {location_id:'LOC-V3-006'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-019'}), (l:Location {location_id:'LOC-V3-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-06-15'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-020'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-11-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-021'}), (l:Location {location_id:'LOC-V3-013'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-022'}), (l:Location {location_id:'LOC-V3-009'}) CREATE (p)-[:LIVES_AT {from_date:date('2019-05-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-023'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-11-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-024'}), (l:Location {location_id:'LOC-V3-011'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-08-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-025'}), (l:Location {location_id:'LOC-V3-011'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-02-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-026'}), (l:Location {location_id:'LOC-V3-012'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-10-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-027'}), (l:Location {location_id:'LOC-V3-002'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-04-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-028'}), (l:Location {location_id:'LOC-V3-001'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-029'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-08-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-030'}), (l:Location {location_id:'LOC-V3-008'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-07-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-031'}), (l:Location {location_id:'LOC-V3-004'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-032'}), (l:Location {location_id:'LOC-V3-013'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-12-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-033'}), (l:Location {location_id:'LOC-V3-015'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-034'}), (l:Location {location_id:'LOC-V3-014'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-035'}), (l:Location {location_id:'LOC-V3-006'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-036'}), (l:Location {location_id:'LOC-V3-010'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-037'}), (l:Location {location_id:'LOC-V3-003'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-038'}), (l:Location {location_id:'LOC-V3-014'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-09-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-039'}), (l:Location {location_id:'LOC-V3-011'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-07-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-V3-040'}), (l:Location {location_id:'LOC-V3-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-10-01'), to_date:null, active:true}]->(l);

// Historical residences (active:false) — 9 persons moved house
MATCH (p:Person {person_id:'PER-V3-007'}), (l:Location {location_id:'LOC-V3-004'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-05-01'), to_date:date('2023-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-008'}), (l:Location {location_id:'LOC-V3-007'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:date('2025-02-28'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-009'}), (l:Location {location_id:'LOC-V3-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-01-01'), to_date:date('2025-06-30'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-010'}), (l:Location {location_id:'LOC-V3-004'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-06-01'), to_date:date('2024-05-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-011'}), (l:Location {location_id:'LOC-V3-013'}) CREATE (p)-[:LIVES_AT {from_date:date('2018-01-01'), to_date:date('2021-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-013'}), (l:Location {location_id:'LOC-V3-011'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-01-01'), to_date:date('2024-01-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-014'}), (l:Location {location_id:'LOC-V3-010'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:date('2024-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-019'}), (l:Location {location_id:'LOC-V3-002'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-03-01'), to_date:date('2023-05-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-V3-033'}), (l:Location {location_id:'LOC-V3-008'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-01-01'), to_date:date('2022-12-31'), active:false}]->(l);


// ────────────────────────────────────────────────────────────
// 12. Person → Vehicle (OWNS) — temporal
//     5 vehicles changed hands (prior active:false + current active:true):
//     VEH-001, VEH-003, VEH-005, VEH-006, VEH-009.
// ────────────────────────────────────────────────────────────

// Current ownership (active:true)
MATCH (p:Person {person_id:'PER-V3-007'}), (v:Vehicle {vehicle_id:'VEH-V3-001'}) CREATE (p)-[:OWNS {from_date:date('2024-03-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-008'}), (v:Vehicle {vehicle_id:'VEH-V3-002'}) CREATE (p)-[:OWNS {from_date:date('2023-08-15'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-009'}), (v:Vehicle {vehicle_id:'VEH-V3-003'}) CREATE (p)-[:OWNS {from_date:date('2023-07-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-011'}), (v:Vehicle {vehicle_id:'VEH-V3-009'}) CREATE (p)-[:OWNS {from_date:date('2023-06-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-014'}), (v:Vehicle {vehicle_id:'VEH-V3-005'}) CREATE (p)-[:OWNS {from_date:date('2024-01-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-033'}), (v:Vehicle {vehicle_id:'VEH-V3-006'}) CREATE (p)-[:OWNS {from_date:date('2022-09-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-020'}), (v:Vehicle {vehicle_id:'VEH-V3-007'}) CREATE (p)-[:OWNS {from_date:date('2020-11-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-027'}), (v:Vehicle {vehicle_id:'VEH-V3-004'}) CREATE (p)-[:OWNS {from_date:date('2021-04-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-034'}), (v:Vehicle {vehicle_id:'VEH-V3-010'}) CREATE (p)-[:OWNS {from_date:date('2023-02-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-026'}), (v:Vehicle {vehicle_id:'VEH-V3-008'}) CREATE (p)-[:OWNS {from_date:date('2022-05-01'), to_date:null, active:true}]->(v);
// Co-current owners (7.2 seed: give PER-013 Santos and PER-018 Orlov an active OWNS so their
// "current vs all ownership" temporal questions Q-V3-103/116 have a non-empty current reading).
MATCH (p:Person {person_id:'PER-V3-013'}), (v:Vehicle {vehicle_id:'VEH-V3-007'}) CREATE (p)-[:OWNS {from_date:date('2024-05-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-V3-018'}), (v:Vehicle {vehicle_id:'VEH-V3-008'}) CREATE (p)-[:OWNS {from_date:date('2024-05-01'), to_date:null, active:true}]->(v);

// Historical ownership (active:false) — vehicle changed hands
MATCH (p:Person {person_id:'PER-V3-010'}), (v:Vehicle {vehicle_id:'VEH-V3-001'}) CREATE (p)-[:OWNS {from_date:date('2020-06-01'), to_date:date('2024-02-28'), active:false}]->(v);
MATCH (p:Person {person_id:'PER-V3-015'}), (v:Vehicle {vehicle_id:'VEH-V3-003'}) CREATE (p)-[:OWNS {from_date:date('2020-01-01'), to_date:date('2023-06-30'), active:false}]->(v);
MATCH (p:Person {person_id:'PER-V3-013'}), (v:Vehicle {vehicle_id:'VEH-V3-005'}) CREATE (p)-[:OWNS {from_date:date('2021-01-01'), to_date:date('2023-12-31'), active:false}]->(v);
MATCH (p:Person {person_id:'PER-V3-018'}), (v:Vehicle {vehicle_id:'VEH-V3-006'}) CREATE (p)-[:OWNS {from_date:date('2019-01-01'), to_date:date('2022-08-31'), active:false}]->(v);
MATCH (p:Person {person_id:'PER-V3-012'}), (v:Vehicle {vehicle_id:'VEH-V3-009'}) CREATE (p)-[:OWNS {from_date:date('2020-01-01'), to_date:date('2023-05-31'), active:false}]->(v);


// ────────────────────────────────────────────────────────────
// 13. Person → Phone (USES_PHONE) — temporal
//     5 phones reassigned between persons (prior active:false):
//     DEV-001, DEV-002, DEV-003, DEV-005, DEV-008.
// ────────────────────────────────────────────────────────────

// Current usage (active:true) — all 14 phones
MATCH (p:Person {person_id:'PER-V3-007'}), (ph:Phone {device_id:'DEV-V3-001'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-034'}), (ph:Phone {device_id:'DEV-V3-002'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-009'}), (ph:Phone {device_id:'DEV-V3-003'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-09-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-010'}), (ph:Phone {device_id:'DEV-V3-004'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-008'}), (ph:Phone {device_id:'DEV-V3-005'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-02-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-011'}), (ph:Phone {device_id:'DEV-V3-006'}) CREATE (p)-[:USES_PHONE {from_date:date('2023-03-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-012'}), (ph:Phone {device_id:'DEV-V3-007'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-013'}), (ph:Phone {device_id:'DEV-V3-008'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-014'}), (ph:Phone {device_id:'DEV-V3-009'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-02-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-015'}), (ph:Phone {device_id:'DEV-V3-010'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-033'}), (ph:Phone {device_id:'DEV-V3-011'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-036'}), (ph:Phone {device_id:'DEV-V3-012'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-027'}), (ph:Phone {device_id:'DEV-V3-013'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-03-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-V3-019'}), (ph:Phone {device_id:'DEV-V3-014'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-08-01'), to_date:null, active:true}]->(ph);

// Historical usage (active:false) — phone reassigned to a different person
MATCH (p:Person {person_id:'PER-V3-010'}), (ph:Phone {device_id:'DEV-V3-001'}) CREATE (p)-[:USES_PHONE {from_date:date('2023-01-01'), to_date:date('2024-12-31'), active:false}]->(ph);
MATCH (p:Person {person_id:'PER-V3-008'}), (ph:Phone {device_id:'DEV-V3-002'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:date('2025-05-31'), active:false}]->(ph);
MATCH (p:Person {person_id:'PER-V3-015'}), (ph:Phone {device_id:'DEV-V3-003'}) CREATE (p)-[:USES_PHONE {from_date:date('2023-01-01'), to_date:date('2024-08-31'), active:false}]->(ph);
MATCH (p:Person {person_id:'PER-V3-018'}), (ph:Phone {device_id:'DEV-V3-005'}) CREATE (p)-[:USES_PHONE {from_date:date('2023-06-01'), to_date:date('2025-01-31'), active:false}]->(ph);
MATCH (p:Person {person_id:'PER-V3-014'}), (ph:Phone {device_id:'DEV-V3-008'}) CREATE (p)-[:USES_PHONE {from_date:date('2022-01-01'), to_date:date('2023-11-30'), active:false}]->(ph);


// ────────────────────────────────────────────────────────────
// 14. Phone → Phone (CALLED) {timestamp}
// ────────────────────────────────────────────────────────────

// Whitfield (DEV-001) ↔ Petrova (DEV-005)
MATCH (a:Phone {device_id:'DEV-V3-001'}), (b:Phone {device_id:'DEV-V3-005'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-01-10T19:45:00')}]->(b);
MATCH (a:Phone {device_id:'DEV-V3-001'}), (b:Phone {device_id:'DEV-V3-005'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-01-14T21:10:00')}]->(b);
// Whitfield (DEV-001) ↔ Daniel Kim (DEV-003)
MATCH (a:Phone {device_id:'DEV-V3-001'}), (b:Phone {device_id:'DEV-V3-003'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-19T23:30:00')}]->(b);
MATCH (a:Phone {device_id:'DEV-V3-003'}), (b:Phone {device_id:'DEV-V3-001'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-20T00:15:00')}]->(b);
// Maric (DEV-011) → Whitfield (DEV-001)
MATCH (a:Phone {device_id:'DEV-V3-011'}), (b:Phone {device_id:'DEV-V3-001'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-01-12T15:40:00')}]->(b);
// Daniel Kim (DEV-003) → Birch (DEV-004)
MATCH (a:Phone {device_id:'DEV-V3-003'}), (b:Phone {device_id:'DEV-V3-004'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-24T18:30:00')}]->(b);
// Hassan (DEV-006) ↔ Gallagher (DEV-002)
MATCH (a:Phone {device_id:'DEV-V3-006'}), (b:Phone {device_id:'DEV-V3-002'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-07T14:20:00')}]->(b);
MATCH (a:Phone {device_id:'DEV-V3-006'}), (b:Phone {device_id:'DEV-V3-002'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-09T10:00:00')}]->(b);
// Santos (DEV-008) ↔ Doyle (DEV-009)
MATCH (a:Phone {device_id:'DEV-V3-008'}), (b:Phone {device_id:'DEV-V3-009'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-27T22:00:00')}]->(b);
MATCH (a:Phone {device_id:'DEV-V3-009'}), (b:Phone {device_id:'DEV-V3-008'}) CREATE (a)-[:CALLED {timestamp:datetime('2025-11-09T14:00:00')}]->(b);
// Maric (DEV-011) → Santos (DEV-008) — broker connection
MATCH (a:Phone {device_id:'DEV-V3-011'}), (b:Phone {device_id:'DEV-V3-008'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-02-15T12:00:00')}]->(b);
// Leon Park (DEV-012) → Santos (DEV-008)
MATCH (a:Phone {device_id:'DEV-V3-012'}), (b:Phone {device_id:'DEV-V3-008'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-03-04T20:00:00')}]->(b);
// Whitfield (DEV-001) → Thompson (DEV-013)
MATCH (a:Phone {device_id:'DEV-V3-001'}), (b:Phone {device_id:'DEV-V3-013'}) CREATE (a)-[:CALLED {timestamp:datetime('2026-01-14T18:30:00')}]->(b);


// ────────────────────────────────────────────────────────────
// 15. Person ↔ Person (ASSOCIATED_WITH) {from_date, to_date, active}
//     Stored as a single directed edge; queried undirected (schema pattern 11).
//     Temporal seed: 2 associations are dissolved (active:false).
// ────────────────────────────────────────────────────────────

MATCH (a:Person {person_id:'PER-V3-007'}), (b:Person {person_id:'PER-V3-008'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-06-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-007'}), (b:Person {person_id:'PER-V3-009'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-03-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-008'}), (b:Person {person_id:'PER-V3-018'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2023-01-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-009'}), (b:Person {person_id:'PER-V3-010'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-01-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-011'}), (b:Person {person_id:'PER-V3-034'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-06-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-017'}), (b:Person {person_id:'PER-V3-011'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-09-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-013'}), (b:Person {person_id:'PER-V3-014'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-04-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-033'}), (b:Person {person_id:'PER-V3-007'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-01-01'), to_date:null, active:true}]->(b);
MATCH (a:Person {person_id:'PER-V3-033'}), (b:Person {person_id:'PER-V3-013'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-06-01'), to_date:null, active:true}]->(b);
// Dissolved associations (active:false) — temporal seed
MATCH (a:Person {person_id:'PER-V3-010'}), (b:Person {person_id:'PER-V3-014'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2023-01-01'), to_date:date('2025-06-30'), active:false}]->(b);
MATCH (a:Person {person_id:'PER-V3-011'}), (b:Person {person_id:'PER-V3-033'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2022-01-01'), to_date:date('2024-12-31'), active:false}]->(b);


// ────────────────────────────────────────────────────────────
// 16. VERIFICATION QUERIES (run after loading — see 7.2 harness)
// ────────────────────────────────────────────────────────────

// Node counts by label:
//   MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label;
//   Expected: Person 40, Incident 12, Case 4, Location 16, Vehicle 10, Phone 14  =>  96 nodes
//
// Relationship types (must be exactly 11):
//   MATCH ()-[r]->() RETURN type(r) AS rel_type, count(*) AS count ORDER BY rel_type;
//   Expected types: ASSOCIATED_WITH, CALLED, CONTAINS, INVESTIGATES, LIVES_AT,
//     OCCURRED_AT, OWNS, SUSPECTED_OF, USES_PHONE, VICTIM_OF, WITNESSED
//
// Labels (must be exactly 6):
//   CALL db.labels();  =>  Person, Incident, Case, Location, Vehicle, Phone
//
// Entity-ambiguity seed spot-checks:
//   Duplicate surnames:  MATCH (p:Person) WHERE p.name ENDS WITH ' Chen' RETURN p.name;   // David Chen, Wei Chen
//   Shared given name:   MATCH (p:Person) WHERE p.name STARTS WITH 'James ' RETURN p.name; // 3 Jameses
//   Alias collision:     MATCH (p:Person {alias:'James'}) RETURN p.name;                   // Michael Nguyen
//   Location collision:  MATCH (l:Location) WHERE l.address CONTAINS 'Albany Highway' RETURN l.suburb; // Cannington, Victoria Park
//
// Temporal seed spot-checks:
//   Moved house (≥8):    MATCH (p:Person)-[r:LIVES_AT]->() WITH p, count(r) AS n WHERE n>1 RETURN count(p);   // 9
//   Vehicle transfers:   MATCH (v:Vehicle)<-[r:OWNS]-() WITH v, count(r) AS n WHERE n>1 RETURN count(v);      // 5
//   Phone reassignments: MATCH (ph:Phone)<-[r:USES_PHONE]-() WITH ph, count(r) AS n WHERE n>1 RETURN count(ph);// 5
//
// Cross-role persons:
//   PER-V3-009 (Daniel Kim): SUSPECTED_OF INC-002/003/006 | WITNESSED INC-009
//   PER-V3-019 (Sarah Nguyen): VICTIM_OF INC-001 | WITNESSED INC-008
