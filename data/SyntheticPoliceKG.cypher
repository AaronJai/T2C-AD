// ============================================================
// KG Schema v2 — Full Synthetic Dataset
// Policing Knowledge Graph (POLE-inspired)
// Honours Research: Ambiguity-Aware Text-to-Cypher
// 
// Target volumes:
//   35 Persons, 12 Incidents, 4 Cases, 18 Locations,
//   10 Vehicles, 14 Phones, 10 Evidence, 5 Organisations,
//   10 Communications
//
// Design principles:
//   - Cross-role persons (suspect in one incident, witness in another)
//   - Historical temporal edges (LIVES_AT, OWNS, ASSOCIATED_WITH)
//   - Enough variety per node type to discriminate correct vs incorrect queries
//   - Realistic Perth metro geography
// ============================================================


// ────────────────────────────────────────────────────────────
// 1. CONSTRAINTS & INDEXES
// ────────────────────────────────────────────────────────────

CREATE CONSTRAINT person_id_unique   IF NOT EXISTS FOR (p:Person)         REQUIRE p.person_id IS UNIQUE;
CREATE CONSTRAINT incident_id_unique IF NOT EXISTS FOR (i:Incident)       REQUIRE i.incident_id IS UNIQUE;
CREATE CONSTRAINT case_id_unique     IF NOT EXISTS FOR (c:Case)           REQUIRE c.case_id IS UNIQUE;
CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location)       REQUIRE l.location_id IS UNIQUE;
CREATE CONSTRAINT vehicle_id_unique  IF NOT EXISTS FOR (v:Vehicle)        REQUIRE v.vehicle_id IS UNIQUE;
CREATE CONSTRAINT device_id_unique   IF NOT EXISTS FOR (d:Phone)          REQUIRE d.device_id IS UNIQUE;
CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS FOR (e:Evidence)       REQUIRE e.evidence_id IS UNIQUE;
CREATE CONSTRAINT org_id_unique      IF NOT EXISTS FOR (o:Organisation)   REQUIRE o.org_id IS UNIQUE;
CREATE CONSTRAINT comm_id_unique     IF NOT EXISTS FOR (cm:Communication) REQUIRE cm.comm_id IS UNIQUE;

CREATE INDEX person_name_idx       IF NOT EXISTS FOR (p:Person)       ON (p.name);
CREATE INDEX person_role_idx       IF NOT EXISTS FOR (p:Person)       ON (p.role);
CREATE INDEX person_status_idx     IF NOT EXISTS FOR (p:Person)       ON (p.status);
CREATE INDEX incident_type_idx     IF NOT EXISTS FOR (i:Incident)     ON (i.crime_type);
CREATE INDEX incident_date_idx     IF NOT EXISTS FOR (i:Incident)     ON (i.date);
CREATE INDEX incident_status_idx   IF NOT EXISTS FOR (i:Incident)     ON (i.status);
CREATE INDEX location_suburb_idx   IF NOT EXISTS FOR (l:Location)     ON (l.suburb);
CREATE INDEX location_district_idx IF NOT EXISTS FOR (l:Location)     ON (l.district);
CREATE INDEX case_status_idx       IF NOT EXISTS FOR (c:Case)         ON (c.status);
CREATE INDEX org_type_idx          IF NOT EXISTS FOR (o:Organisation) ON (o.type);
CREATE INDEX org_status_idx        IF NOT EXISTS FOR (o:Organisation) ON (o.status);
CREATE INDEX vehicle_plate_idx     IF NOT EXISTS FOR (v:Vehicle)      ON (v.license_plate);
CREATE INDEX evidence_type_idx     IF NOT EXISTS FOR (e:Evidence)     ON (e.type);


// ────────────────────────────────────────────────────────────
// 2. NODES — Person (35)
// ────────────────────────────────────────────────────────────
// Officers (6)
CREATE (:Person {person_id:'PER-001', name:'David Chen',       date_of_birth:date('1978-11-03'), gender:'male',   nationality:'Australian', alias:null,          role:'officer',             status:'active'});
CREATE (:Person {person_id:'PER-002', name:'Ryan Clarke',      date_of_birth:date('1980-04-29'), gender:'male',   nationality:'Australian', alias:null,          role:'officer',             status:'active'});
CREATE (:Person {person_id:'PER-003', name:'Megan Tran',       date_of_birth:date('1986-07-12'), gender:'female', nationality:'Australian', alias:null,          role:'officer',             status:'active'});
CREATE (:Person {person_id:'PER-004', name:'James Kowalski',   date_of_birth:date('1975-02-18'), gender:'male',   nationality:'Australian', alias:null,          role:'officer',             status:'active'});
CREATE (:Person {person_id:'PER-005', name:'Priya Sharma',     date_of_birth:date('1990-10-05'), gender:'female', nationality:'Australian', alias:null,          role:'officer',             status:'active'});
CREATE (:Person {person_id:'PER-006', name:'Tom Elliot',       date_of_birth:date('1983-12-20'), gender:'male',   nationality:'Australian', alias:null,          role:'officer',             status:'active'});

// Suspects (8)
CREATE (:Person {person_id:'PER-007', name:'James Whitfield',  date_of_birth:date('1985-06-14'), gender:'male',   nationality:'Australian', alias:'Jimmy White',  role:'suspect',             status:'active'});
CREATE (:Person {person_id:'PER-008', name:'Lina Petrova',     date_of_birth:date('1988-09-05'), gender:'female', nationality:'Russian',    alias:null,          role:'suspect',             status:'active'});
CREATE (:Person {person_id:'PER-009', name:'Danny Kovac',      date_of_birth:date('1991-03-30'), gender:'male',   nationality:'Australian', alias:'DK',          role:'suspect',             status:'in_custody'});
CREATE (:Person {person_id:'PER-010', name:'Tyler Birch',      date_of_birth:date('1995-08-22'), gender:'male',   nationality:'Australian', alias:'Birchy',      role:'suspect',             status:'active'});
CREATE (:Person {person_id:'PER-011', name:'Amir Hassan',      date_of_birth:date('1982-01-11'), gender:'male',   nationality:'Australian', alias:null,          role:'suspect',             status:'active'});
CREATE (:Person {person_id:'PER-012', name:'Jade Wu',          date_of_birth:date('1993-05-17'), gender:'female', nationality:'Australian', alias:null,          role:'suspect',             status:'active'});
CREATE (:Person {person_id:'PER-013', name:'Ricky Santos',     date_of_birth:date('1989-11-28'), gender:'male',   nationality:'Filipino',   alias:'Rico',        role:'suspect',             status:'missing'});
CREATE (:Person {person_id:'PER-014', name:'Connor Doyle',     date_of_birth:date('1997-04-03'), gender:'male',   nationality:'Australian', alias:null,          role:'suspect',             status:'active'});

// Victims (6)
CREATE (:Person {person_id:'PER-015', name:'Sarah Nguyen',     date_of_birth:date('1990-03-22'), gender:'female', nationality:'Australian', alias:null,          role:'victim',              status:'active'});
CREATE (:Person {person_id:'PER-016', name:'Marcus Webb',      date_of_birth:date('1972-09-15'), gender:'male',   nationality:'Australian', alias:null,          role:'victim',              status:'active'});
CREATE (:Person {person_id:'PER-017', name:'Emily Ford',       date_of_birth:date('1998-12-01'), gender:'female', nationality:'Australian', alias:null,          role:'victim',              status:'active'});
CREATE (:Person {person_id:'PER-018', name:'Hassan Ali',       date_of_birth:date('1965-06-30'), gender:'male',   nationality:'Iraqi',      alias:null,          role:'victim',              status:'deceased'});
CREATE (:Person {person_id:'PER-019', name:'Rachel Kim',       date_of_birth:date('1994-02-14'), gender:'female', nationality:'Australian', alias:null,          role:'victim',              status:'active'});
CREATE (:Person {person_id:'PER-020', name:'Thomas Grant',     date_of_birth:date('1987-07-08'), gender:'male',   nationality:'Australian', alias:null,          role:'victim',              status:'active'});

// Witnesses (5)
CREATE (:Person {person_id:'PER-021', name:'Mark Thompson',    date_of_birth:date('1992-01-17'), gender:'male',   nationality:'Australian', alias:'Thommo',      role:'witness',             status:'active'});
CREATE (:Person {person_id:'PER-022', name:'Karen Liu',        date_of_birth:date('1970-05-23'), gender:'female', nationality:'Australian', alias:null,          role:'witness',             status:'active'});
CREATE (:Person {person_id:'PER-023', name:'Brian Walsh',      date_of_birth:date('1968-08-09'), gender:'male',   nationality:'Australian', alias:null,          role:'witness',             status:'active'});
CREATE (:Person {person_id:'PER-024', name:'Deepa Nair',       date_of_birth:date('1996-04-11'), gender:'female', nationality:'Indian',     alias:null,          role:'witness',             status:'active'});
CREATE (:Person {person_id:'PER-025', name:'Steven Yeo',       date_of_birth:date('1984-10-25'), gender:'male',   nationality:'Singaporean',alias:null,          role:'witness',             status:'active'});

// Persons of Interest (4)
CREATE (:Person {person_id:'PER-026', name:'Anton Maric',      date_of_birth:date('1979-12-02'), gender:'male',   nationality:'Serbian',    alias:'The Broker',  role:'person_of_interest',  status:'active'});
CREATE (:Person {person_id:'PER-027', name:'Fiona Gallagher',  date_of_birth:date('1985-03-19'), gender:'female', nationality:'Australian', alias:null,          role:'person_of_interest',  status:'active'});
CREATE (:Person {person_id:'PER-028', name:'Yusuf Abdi',       date_of_birth:date('1990-07-14'), gender:'male',   nationality:'Somali',     alias:null,          role:'person_of_interest',  status:'active'});
CREATE (:Person {person_id:'PER-029', name:'Nina Orlov',       date_of_birth:date('1992-11-08'), gender:'female', nationality:'Russian',    alias:null,          role:'person_of_interest',  status:'active'});

// Informants (2)
CREATE (:Person {person_id:'PER-030', name:'Leon Park',        date_of_birth:date('1988-06-06'), gender:'male',   nationality:'Korean',     alias:null,          role:'informant',           status:'active'});
CREATE (:Person {person_id:'PER-031', name:'Michelle Torres',  date_of_birth:date('1993-09-21'), gender:'female', nationality:'Australian', alias:null,          role:'informant',           status:'active'});

// Civilians / additional (4) — no primary role in any incident yet, but connected socially
CREATE (:Person {person_id:'PER-032', name:'Ben Murray',       date_of_birth:date('1991-02-28'), gender:'male',   nationality:'Australian', alias:null,          role:'civilian',            status:'active'});
CREATE (:Person {person_id:'PER-033', name:'Lisa Chang',       date_of_birth:date('1987-08-13'), gender:'female', nationality:'Australian', alias:null,          role:'civilian',            status:'active'});
CREATE (:Person {person_id:'PER-034', name:'Omar Farah',       date_of_birth:date('1976-01-05'), gender:'male',   nationality:'Australian', alias:null,          role:'civilian',            status:'active'});
CREATE (:Person {person_id:'PER-035', name:'Sophie Bennett',   date_of_birth:date('1999-11-30'), gender:'female', nationality:'Australian', alias:null,          role:'civilian',            status:'active'});


// ────────────────────────────────────────────────────────────
// 3. NODES — Incident (12)
// ────────────────────────────────────────────────────────────

CREATE (:Incident {incident_id:'INC-001', crime_type:'robbery',      description:'Armed robbery at a convenience store on William Street. Suspect fled on foot heading north.',                          date:date('2026-01-15'), time:time('22:30:00'), status:'under_investigation', severity:'high'});
CREATE (:Incident {incident_id:'INC-002', crime_type:'drug_offence', description:'Controlled substance found during vehicle stop on Great Eastern Highway. 50g methamphetamine seized.',                date:date('2026-02-03'), time:time('14:15:00'), status:'open',               severity:'medium'});
CREATE (:Incident {incident_id:'INC-003', crime_type:'assault',      description:'Unprovoked assault outside a nightclub on James Street, Northbridge. Victim hospitalised with facial injuries.',       date:date('2026-02-20'), time:time('01:45:00'), status:'under_investigation', severity:'high'});
CREATE (:Incident {incident_id:'INC-004', crime_type:'burglary',     description:'Break-in at a jewellery store on South Terrace, Fremantle. Display cases smashed, stock stolen.',                     date:date('2025-11-10'), time:time('03:20:00'), status:'closed',             severity:'medium'});
CREATE (:Incident {incident_id:'INC-005', crime_type:'fraud',        description:'Fraudulent invoicing scheme targeting multiple businesses on St Georges Terrace. Estimated $450k in losses.',          date:date('2026-01-28'), time:null,              status:'open',               severity:'high'});
CREATE (:Incident {incident_id:'INC-006', crime_type:'homicide',     description:'Fatal stabbing at a residential property on Albany Highway, Cannington. Victim pronounced dead at scene.',              date:date('2026-03-01'), time:time('19:50:00'), status:'under_investigation', severity:'critical'});
CREATE (:Incident {incident_id:'INC-007', crime_type:'drug_offence', description:'Suspected drug supply operation at a Lake Street premises. Multiple persons observed in short visits over several days.',date:date('2026-02-15'), time:time('16:00:00'), status:'under_investigation', severity:'medium'});
CREATE (:Incident {incident_id:'INC-008', crime_type:'robbery',      description:'Aggravated robbery at a bottle shop on Morrison Road, Midland. Weapon brandished, cash register emptied.',             date:date('2026-02-28'), time:time('20:10:00'), status:'open',               severity:'high'});
CREATE (:Incident {incident_id:'INC-009', crime_type:'assault',      description:'Altercation at Scarborough Beach foreshore between two groups. Three persons injured.',                                 date:date('2025-12-20'), time:time('23:15:00'), status:'closed',             severity:'medium'});
CREATE (:Incident {incident_id:'INC-010', crime_type:'traffic',      description:'Hit and run on Joondalup Drive. Driver fled scene. Pedestrian sustained minor injuries.',                              date:date('2026-01-05'), time:time('07:40:00'), status:'closed',             severity:'low'});
CREATE (:Incident {incident_id:'INC-011', crime_type:'burglary',     description:'Residential break-in on Albany Highway, Victoria Park. Laptop, jewellery, and cash stolen.',                           date:date('2025-10-15'), time:time('11:00:00'), status:'cold',               severity:'medium'});
CREATE (:Incident {incident_id:'INC-012', crime_type:'fraud',        description:'Identity fraud ring using stolen personal data to open bank accounts. Linked to online marketplace.',                  date:date('2026-02-10'), time:null,              status:'under_investigation', severity:'high'});


// ────────────────────────────────────────────────────────────
// 4. NODES — Case (4)
// ────────────────────────────────────────────────────────────

CREATE (:Case {case_id:'CASE-001', case_name:'Operation Ironside — Northbridge Series', opened_date:date('2026-01-16'), closed_date:null,              status:'open',           priority:'high'});
CREATE (:Case {case_id:'CASE-002', case_name:'Operation Trident — Drug Network',        opened_date:date('2026-02-05'), closed_date:null,              status:'open',           priority:'high'});
CREATE (:Case {case_id:'CASE-003', case_name:'Operation Cerberus — Financial Crimes',   opened_date:date('2026-02-01'), closed_date:null,              status:'open',           priority:'medium'});
CREATE (:Case {case_id:'CASE-004', case_name:'Operation Sentinel — Midland Taskforce',  opened_date:date('2026-03-01'), closed_date:null,              status:'open',           priority:'critical'});


// ────────────────────────────────────────────────────────────
// 5. NODES — Location (18)
// ────────────────────────────────────────────────────────────

CREATE (:Location {location_id:'LOC-001', address:'142 William Street',         suburb:'Northbridge',   city:'Perth', district:'Central Metropolitan',     latitude:-31.9465, longitude:115.8605, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-002', address:'27 James Street',            suburb:'Northbridge',   city:'Perth', district:'Central Metropolitan',     latitude:-31.9470, longitude:115.8580, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-003', address:'8 Harvest Terrace',          suburb:'West Perth',    city:'Perth', district:'Central Metropolitan',     latitude:-31.9510, longitude:115.8470, location_type:'residential'});
CREATE (:Location {location_id:'LOC-004', address:'310 Great Eastern Highway',  suburb:'Midland',       city:'Perth', district:'South East Metropolitan',  latitude:-31.8890, longitude:116.0100, location_type:'public'});
CREATE (:Location {location_id:'LOC-005', address:'55 Beaufort Street',         suburb:'Perth',         city:'Perth', district:'Central Metropolitan',     latitude:-31.9430, longitude:115.8620, location_type:'residential'});
CREATE (:Location {location_id:'LOC-006', address:'88 Lake Street',             suburb:'Northbridge',   city:'Perth', district:'Central Metropolitan',     latitude:-31.9455, longitude:115.8570, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-007', address:'12 South Terrace',           suburb:'Fremantle',     city:'Perth', district:'South Metropolitan',       latitude:-32.0569, longitude:115.7460, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-008', address:'200 St Georges Terrace',     suburb:'Perth CBD',     city:'Perth', district:'Central Metropolitan',     latitude:-31.9535, longitude:115.8605, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-009', address:'45 Albany Highway',          suburb:'Cannington',    city:'Perth', district:'South East Metropolitan',  latitude:-32.0130, longitude:115.9340, location_type:'residential'});
CREATE (:Location {location_id:'LOC-010', address:'15 Morrison Road',           suburb:'Midland',       city:'Perth', district:'South East Metropolitan',  latitude:-31.8860, longitude:116.0050, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-011', address:'3 Scarborough Beach Road',   suburb:'Scarborough',   city:'Perth', district:'North Metropolitan',       latitude:-31.8940, longitude:115.7600, location_type:'public'});
CREATE (:Location {location_id:'LOC-012', address:'80 Joondalup Drive',         suburb:'Joondalup',     city:'Perth', district:'North Metropolitan',       latitude:-31.7460, longitude:115.7660, location_type:'public'});
CREATE (:Location {location_id:'LOC-013', address:'22 Albany Highway',          suburb:'Victoria Park', city:'Perth', district:'South Metropolitan',       latitude:-31.9760, longitude:115.8940, location_type:'residential'});
CREATE (:Location {location_id:'LOC-014', address:'100 Hay Street',            suburb:'Perth CBD',     city:'Perth', district:'Central Metropolitan',     latitude:-31.9530, longitude:115.8610, location_type:'commercial'});
CREATE (:Location {location_id:'LOC-015', address:'7 Marine Parade',            suburb:'Cottesloe',     city:'Perth', district:'West Metropolitan',        latitude:-31.9940, longitude:115.7530, location_type:'residential'});
CREATE (:Location {location_id:'LOC-016', address:'35 Walcott Street',          suburb:'Mt Lawley',     city:'Perth', district:'Central Metropolitan',     latitude:-31.9300, longitude:115.8710, location_type:'residential'});
CREATE (:Location {location_id:'LOC-017', address:'60 Wanneroo Road',           suburb:'Wanneroo',      city:'Perth', district:'North Metropolitan',       latitude:-31.7500, longitude:115.8070, location_type:'residential'});
CREATE (:Location {location_id:'LOC-018', address:'5 Pier Street',              suburb:'Perth CBD',     city:'Perth', district:'Central Metropolitan',     latitude:-31.9540, longitude:115.8615, location_type:'industrial'});


// ────────────────────────────────────────────────────────────
// 6. NODES — Vehicle (10)
// ────────────────────────────────────────────────────────────

CREATE (:Vehicle {vehicle_id:'VEH-001', license_plate:'1GBH 924', make:'Holden',     model:'Commodore',  year:2018, colour:'black',  vehicle_type:'sedan'});
CREATE (:Vehicle {vehicle_id:'VEH-002', license_plate:'1DLR 337', make:'Toyota',     model:'HiLux',      year:2020, colour:'white',  vehicle_type:'SUV'});
CREATE (:Vehicle {vehicle_id:'VEH-003', license_plate:'1FRD 450', make:'Ford',       model:'Ranger',     year:2019, colour:'blue',   vehicle_type:'SUV'});
CREATE (:Vehicle {vehicle_id:'VEH-004', license_plate:'1HYN 812', make:'Hyundai',    model:'i30',        year:2021, colour:'silver', vehicle_type:'sedan'});
CREATE (:Vehicle {vehicle_id:'VEH-005', license_plate:'1NIS 203', make:'Nissan',     model:'Navara',     year:2017, colour:'red',    vehicle_type:'SUV'});
CREATE (:Vehicle {vehicle_id:'VEH-006', license_plate:'1MAZ 667', make:'Mazda',      model:'3',          year:2022, colour:'grey',   vehicle_type:'sedan'});
CREATE (:Vehicle {vehicle_id:'VEH-007', license_plate:'1TOY 115', make:'Toyota',     model:'Camry',      year:2020, colour:'white',  vehicle_type:'sedan'});
CREATE (:Vehicle {vehicle_id:'VEH-008', license_plate:'1MIT 908', make:'Mitsubishi', model:'Triton',     year:2018, colour:'black',  vehicle_type:'SUV'});
CREATE (:Vehicle {vehicle_id:'VEH-009', license_plate:'1BMW 321', make:'BMW',        model:'3 Series',   year:2023, colour:'blue',   vehicle_type:'sedan'});
CREATE (:Vehicle {vehicle_id:'VEH-010', license_plate:'1HOL 555', make:'Holden',     model:'Colorado',   year:2019, colour:'white',  vehicle_type:'SUV'});


// ────────────────────────────────────────────────────────────
// 7. NODES — Phone / Device (12)
// ────────────────────────────────────────────────────────────

CREATE (:Phone {device_id:'DEV-001', phone_number:'0412 345 678', imei:'351234567890001', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-002', phone_number:'0423 987 654', imei:'351234567890002', device_type:'mobile',  carrier:'Optus'});
CREATE (:Phone {device_id:'DEV-003', phone_number:'0401 111 222', imei:'351234567890003', device_type:'mobile',  carrier:'Vodafone'});
CREATE (:Phone {device_id:'DEV-004', phone_number:'0434 555 888', imei:'351234567890004', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-005', phone_number:'0445 222 333', imei:'351234567890005', device_type:'mobile',  carrier:'Optus'});
CREATE (:Phone {device_id:'DEV-006', phone_number:'0456 777 999', imei:'351234567890006', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-007', phone_number:'0467 333 444', imei:'351234567890007', device_type:'mobile',  carrier:'Vodafone'});
CREATE (:Phone {device_id:'DEV-008', phone_number:'0478 444 555', imei:'351234567890008', device_type:'mobile',  carrier:'Optus'});
CREATE (:Phone {device_id:'DEV-009', phone_number:'0489 666 111', imei:'351234567890009', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-010', phone_number:'0490 888 777', imei:'351234567890010', device_type:'mobile',  carrier:'Vodafone'});
CREATE (:Phone {device_id:'DEV-011', phone_number:'0411 999 000', imei:'351234567890011', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-012', phone_number:'0422 000 111', imei:'351234567890012', device_type:'mobile',  carrier:'Optus'});
CREATE (:Phone {device_id:'DEV-013', phone_number:'0433 222 111', imei:'351234567890013', device_type:'mobile',  carrier:'Telstra'});
CREATE (:Phone {device_id:'DEV-014', phone_number:'0455 333 222', imei:'351234567890014', device_type:'mobile',  carrier:'Optus'});


// ────────────────────────────────────────────────────────────
// 8. NODES — Evidence (10)
// ────────────────────────────────────────────────────────────

CREATE (:Evidence {evidence_id:'EVI-001', type:'physical',    description:'Kitchen knife recovered from scene, partial fingerprints on handle.',                 collected_date:date('2026-01-16'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-002', type:'digital',     description:'CCTV footage from William Street convenience store showing suspect.',                collected_date:date('2026-01-16'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-003', type:'forensic',    description:'50g methamphetamine seized during vehicle stop.',                                    collected_date:date('2026-02-03'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-004', type:'digital',     description:'Mobile phone data extraction showing call logs and GPS history.',                    collected_date:date('2026-02-21'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-005', type:'documentary', description:'Fraudulent invoices totalling $450k recovered from office premises.',                collected_date:date('2026-02-05'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-006', type:'physical',    description:'Bloodstained clothing recovered from suspect vehicle.',                              collected_date:date('2026-03-02'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-007', type:'forensic',    description:'DNA sample collected from crime scene matching suspect in database.',                collected_date:date('2026-03-02'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-008', type:'testimonial', description:'Witness statement describing two males fleeing on foot towards Lake Street.',        collected_date:date('2026-01-16'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-009', type:'digital',     description:'Bank transaction records showing suspicious transfers between shell companies.',     collected_date:date('2026-02-12'), chain_of_custody:'intact'});
CREATE (:Evidence {evidence_id:'EVI-010', type:'physical',    description:'Crowbar and glass fragments recovered from Fremantle jewellery store break-in.',     collected_date:date('2025-11-10'), chain_of_custody:'compromised'});


// ────────────────────────────────────────────────────────────
// 9. NODES — Organisation (5)
// ────────────────────────────────────────────────────────────

CREATE (:Organisation {org_id:'ORG-001', name:'Northbridge Crew',       type:'gang',    established_date:null,              status:'under_investigation', jurisdiction:'state'});
CREATE (:Organisation {org_id:'ORG-002', name:'Metro Security Services', type:'company', established_date:date('2015-03-01'), status:'active',              jurisdiction:null});
CREATE (:Organisation {org_id:'ORG-003', name:'Pacific Trading Co',     type:'company', established_date:date('2020-08-15'), status:'under_investigation', jurisdiction:'national'});
CREATE (:Organisation {org_id:'ORG-004', name:'East Side Boys',         type:'gang',    established_date:null,              status:'active',              jurisdiction:'state'});
CREATE (:Organisation {org_id:'ORG-005', name:'Horizon Property Group', type:'company', established_date:date('2018-01-20'), status:'dissolved',           jurisdiction:'state'});


// ────────────────────────────────────────────────────────────
// 10. NODES — Communication (10)
// ────────────────────────────────────────────────────────────

CREATE (:Communication {comm_id:'COMM-001', type:'meeting',             date:date('2026-01-10'), time:time('20:00:00'), summary:'In-person meeting between Whitfield and Petrova at a Northbridge bar. Discussed logistics.',                  classification:'restricted'});
CREATE (:Communication {comm_id:'COMM-002', type:'intercepted',         date:date('2026-02-01'), time:time('11:30:00'), summary:'Intercepted phone conversation referencing a shipment arriving via Fremantle port.',                            classification:'confidential'});
CREATE (:Communication {comm_id:'COMM-003', type:'intelligence_report', date:date('2026-02-18'), time:null,             summary:'Intelligence report linking Pacific Trading Co to fraudulent invoice scheme across multiple shell entities.',   classification:'confidential'});
CREATE (:Communication {comm_id:'COMM-004', type:'meeting',             date:date('2026-02-25'), time:time('21:30:00'), summary:'Observed meeting between Kovac, Birch, and unknown male at Cannington residence.',                              classification:'restricted'});
CREATE (:Communication {comm_id:'COMM-005', type:'intercepted',         date:date('2026-01-12'), time:time('15:45:00'), summary:'Intercepted SMS discussing payment for "the Northbridge job".',                                                  classification:'confidential'});
CREATE (:Communication {comm_id:'COMM-006', type:'email',               date:date('2026-02-08'), time:time('09:15:00'), summary:'Email chain between Hassan and Gallagher discussing property transfers through Horizon Group.',                   classification:'restricted'});
CREATE (:Communication {comm_id:'COMM-007', type:'meeting',             date:date('2026-03-05'), time:time('18:00:00'), summary:'Informant debriefing with Leon Park regarding East Side Boys drug distribution in Midland area.',                 classification:'confidential'});
CREATE (:Communication {comm_id:'COMM-008', type:'meeting',             date:date('2026-03-02'), time:time('19:30:00'), summary:'Observed meeting between informant Leon Park and Ricky Santos at a Wanneroo residence. Santos discussed recent activity in the Midland area.', classification:'confidential'});
CREATE (:Communication {comm_id:'COMM-009', type:'intercepted',         date:date('2025-11-08'), time:time('22:15:00'), summary:'Intercepted phone call between Doyle and Santos discussing sale of stolen jewellery from Fremantle job.', classification:'restricted'});
CREATE (:Communication {comm_id:'COMM-010', type:'meeting',             date:date('2026-02-12'), time:time('14:00:00'), summary:'Observed meeting between Hassan and Gallagher at a Perth CBD cafe to discuss property portfolio restructuring.', classification:'restricted'});


// ════════════════════════════════════════════════════════════
// RELATIONSHIPS
// ════════════════════════════════════════════════════════════


// ────────────────────────────────────────────────────────────
// 11. Person ↔ Person (KNOWS, ASSOCIATED_WITH)
// ────────────────────────────────────────────────────────────

// Criminal associates
MATCH (a:Person {person_id:'PER-007'}), (b:Person {person_id:'PER-008'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-06-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-007'}), (b:Person {person_id:'PER-009'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-03-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-008'}), (b:Person {person_id:'PER-029'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2023-01-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-009'}), (b:Person {person_id:'PER-010'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-01-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-011'}), (b:Person {person_id:'PER-027'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-06-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-012'}), (b:Person {person_id:'PER-011'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-09-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-013'}), (b:Person {person_id:'PER-014'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2025-04-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-026'}), (b:Person {person_id:'PER-007'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-01-01'), to_date:null, active:true, association_type:'criminal'}]->(b);
MATCH (a:Person {person_id:'PER-026'}), (b:Person {person_id:'PER-013'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2024-06-01'), to_date:null, active:true, association_type:'criminal'}]->(b);

// Historical (dissolved) association
MATCH (a:Person {person_id:'PER-010'}), (b:Person {person_id:'PER-014'}) CREATE (a)-[:ASSOCIATED_WITH {from_date:date('2023-01-01'), to_date:date('2025-06-30'), active:false, association_type:'criminal'}]->(b);

// Social/familial knows
MATCH (a:Person {person_id:'PER-007'}), (b:Person {person_id:'PER-021'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-007'}), (b:Person {person_id:'PER-032'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-015'}), (b:Person {person_id:'PER-033'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-009'}), (b:Person {person_id:'PER-028'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-017'}), (b:Person {person_id:'PER-035'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-011'}), (b:Person {person_id:'PER-034'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-030'}), (b:Person {person_id:'PER-013'}) CREATE (a)-[:KNOWS]->(b);
MATCH (a:Person {person_id:'PER-027'}), (b:Person {person_id:'PER-006'}) MERGE (a)-[:KNOWS]->(b);


// ────────────────────────────────────────────────────────────
// 12. Person → Location (LIVES_AT) — with temporal history
// ────────────────────────────────────────────────────────────

// Current residences
MATCH (p:Person {person_id:'PER-007'}), (l:Location {location_id:'LOC-003'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-008'}), (l:Location {location_id:'LOC-001'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-009'}), (l:Location {location_id:'LOC-009'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-07-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-010'}), (l:Location {location_id:'LOC-010'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-011'}), (l:Location {location_id:'LOC-015'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-012'}), (l:Location {location_id:'LOC-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-09-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-013'}), (l:Location {location_id:'LOC-017'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-02-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-014'}), (l:Location {location_id:'LOC-012'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-015'}), (l:Location {location_id:'LOC-005'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-06-15'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-016'}), (l:Location {location_id:'LOC-008'}) CREATE (p)-[:LIVES_AT {from_date:date('2020-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-017'}), (l:Location {location_id:'LOC-013'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-018'}), (l:Location {location_id:'LOC-009'}) CREATE (p)-[:LIVES_AT {from_date:date('2019-05-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-019'}), (l:Location {location_id:'LOC-011'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-08-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-020'}), (l:Location {location_id:'LOC-016'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-11-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-021'}), (l:Location {location_id:'LOC-002'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-04-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-022'}), (l:Location {location_id:'LOC-001'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-026'}), (l:Location {location_id:'LOC-015'}) CREATE (p)-[:LIVES_AT {from_date:date('2023-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-027'}), (l:Location {location_id:'LOC-014'}) CREATE (p)-[:LIVES_AT {from_date:date('2024-03-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-029'}), (l:Location {location_id:'LOC-006'}) CREATE (p)-[:LIVES_AT {from_date:date('2025-01-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-032'}), (l:Location {location_id:'LOC-003'}) CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:null, active:true}]->(l);
MATCH (p:Person {person_id:'PER-034'}), (l:Location {location_id:'LOC-018'}) CREATE (p)-[:LIVES_AT {from_date:date('2021-09-01'), to_date:null, active:true}]->(l);

// Historical residences (moved)
MATCH (p:Person {person_id:'PER-007'}), (l:Location {location_id:'LOC-004'})  CREATE (p)-[:LIVES_AT {from_date:date('2021-05-01'), to_date:date('2023-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-009'}), (l:Location {location_id:'LOC-016'})  CREATE (p)-[:LIVES_AT {from_date:date('2022-01-01'), to_date:date('2025-06-30'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-008'}), (l:Location {location_id:'LOC-007'})  CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:date('2025-02-28'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-011'}), (l:Location {location_id:'LOC-013'})  CREATE (p)-[:LIVES_AT {from_date:date('2018-01-01'), to_date:date('2021-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-026'}), (l:Location {location_id:'LOC-018'})  CREATE (p)-[:LIVES_AT {from_date:date('2020-01-01'), to_date:date('2022-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-014'}), (l:Location {location_id:'LOC-010'})  CREATE (p)-[:LIVES_AT {from_date:date('2022-06-01'), to_date:date('2024-12-31'), active:false}]->(l);
MATCH (p:Person {person_id:'PER-013'}), (l:Location {location_id:'LOC-011'})  CREATE (p)-[:LIVES_AT {from_date:date('2021-01-01'), to_date:date('2024-01-31'), active:false}]->(l);


// ────────────────────────────────────────────────────────────
// 13. Person → Vehicle (OWNS) — with ownership changes
// ────────────────────────────────────────────────────────────

// Current ownership
MATCH (p:Person {person_id:'PER-007'}), (v:Vehicle {vehicle_id:'VEH-001'}) CREATE (p)-[:OWNS {from_date:date('2024-03-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-008'}), (v:Vehicle {vehicle_id:'VEH-002'}) CREATE (p)-[:OWNS {from_date:date('2023-08-15'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-009'}), (v:Vehicle {vehicle_id:'VEH-003'}) CREATE (p)-[:OWNS {from_date:date('2022-01-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-011'}), (v:Vehicle {vehicle_id:'VEH-009'}) CREATE (p)-[:OWNS {from_date:date('2023-06-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-014'}), (v:Vehicle {vehicle_id:'VEH-005'}) CREATE (p)-[:OWNS {from_date:date('2024-01-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-026'}), (v:Vehicle {vehicle_id:'VEH-006'}) CREATE (p)-[:OWNS {from_date:date('2022-09-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-016'}), (v:Vehicle {vehicle_id:'VEH-007'}) CREATE (p)-[:OWNS {from_date:date('2020-11-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-021'}), (v:Vehicle {vehicle_id:'VEH-004'}) CREATE (p)-[:OWNS {from_date:date('2021-04-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-027'}), (v:Vehicle {vehicle_id:'VEH-010'}) CREATE (p)-[:OWNS {from_date:date('2023-02-01'), to_date:null, active:true}]->(v);
MATCH (p:Person {person_id:'PER-034'}), (v:Vehicle {vehicle_id:'VEH-008'}) CREATE (p)-[:OWNS {from_date:date('2022-05-01'), to_date:null, active:true}]->(v);

// Historical ownership (vehicle changed hands)
MATCH (p:Person {person_id:'PER-010'}), (v:Vehicle {vehicle_id:'VEH-001'}) CREATE (p)-[:OWNS {from_date:date('2020-06-01'), to_date:date('2024-02-28'), active:false}]->(v);
MATCH (p:Person {person_id:'PER-013'}), (v:Vehicle {vehicle_id:'VEH-005'}) CREATE (p)-[:OWNS {from_date:date('2021-01-01'), to_date:date('2023-12-31'), active:false}]->(v);


// ────────────────────────────────────────────────────────────
// 14. Person → Phone (USES_PHONE)
// ────────────────────────────────────────────────────────────

MATCH (p:Person {person_id:'PER-007'}), (ph:Phone {device_id:'DEV-001'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-008'}), (ph:Phone {device_id:'DEV-005'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-009'}), (ph:Phone {device_id:'DEV-003'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-09-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-010'}), (ph:Phone {device_id:'DEV-004'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-011'}), (ph:Phone {device_id:'DEV-006'}) CREATE (p)-[:USES_PHONE {from_date:date('2023-03-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-012'}), (ph:Phone {device_id:'DEV-007'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-013'}), (ph:Phone {device_id:'DEV-008'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-014'}), (ph:Phone {device_id:'DEV-009'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-02-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-015'}), (ph:Phone {device_id:'DEV-010'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-06-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-026'}), (ph:Phone {device_id:'DEV-011'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-030'}), (ph:Phone {device_id:'DEV-012'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-01-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-027'}), (ph:Phone {device_id:'DEV-002'}) CREATE (p)-[:USES_PHONE {from_date:date('2025-05-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-021'}), (ph:Phone {device_id:'DEV-013'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-03-01'), to_date:null, active:true}]->(ph);
MATCH (p:Person {person_id:'PER-019'}), (ph:Phone {device_id:'DEV-014'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-08-01'), to_date:null, active:true}]->(ph);

// Historical phone usage (person changed phone)
MATCH (p:Person {person_id:'PER-008'}), (ph:Phone {device_id:'DEV-002'}) CREATE (p)-[:USES_PHONE {from_date:date('2024-01-01'), to_date:date('2025-05-31'), active:false}]->(ph);


// ────────────────────────────────────────────────────────────
// 15. Person → Organisation (WORKS_FOR)
// ────────────────────────────────────────────────────────────

MATCH (p:Person {person_id:'PER-007'}), (o:Organisation {org_id:'ORG-001'}) CREATE (p)-[:WORKS_FOR {from_date:date('2024-01-01'), to_date:null, active:true, position:'member'}]->(o);
MATCH (p:Person {person_id:'PER-008'}), (o:Organisation {org_id:'ORG-001'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-06-01'), to_date:null, active:true, position:'associate'}]->(o);
MATCH (p:Person {person_id:'PER-009'}), (o:Organisation {org_id:'ORG-004'}) CREATE (p)-[:WORKS_FOR {from_date:date('2023-01-01'), to_date:null, active:true, position:'member'}]->(o);
MATCH (p:Person {person_id:'PER-010'}), (o:Organisation {org_id:'ORG-004'}) CREATE (p)-[:WORKS_FOR {from_date:date('2024-06-01'), to_date:null, active:true, position:'member'}]->(o);
MATCH (p:Person {person_id:'PER-013'}), (o:Organisation {org_id:'ORG-001'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-01-01'), to_date:null, active:true, position:'runner'}]->(o);
MATCH (p:Person {person_id:'PER-014'}), (o:Organisation {org_id:'ORG-004'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-03-01'), to_date:null, active:true, position:'associate'}]->(o);
MATCH (p:Person {person_id:'PER-021'}), (o:Organisation {org_id:'ORG-002'}) CREATE (p)-[:WORKS_FOR {from_date:date('2022-09-01'), to_date:null, active:true, position:'security guard'}]->(o);
MATCH (p:Person {person_id:'PER-011'}), (o:Organisation {org_id:'ORG-003'}) CREATE (p)-[:WORKS_FOR {from_date:date('2021-01-01'), to_date:null, active:true, position:'director'}]->(o);
MATCH (p:Person {person_id:'PER-027'}), (o:Organisation {org_id:'ORG-005'}) CREATE (p)-[:WORKS_FOR {from_date:date('2019-06-01'), to_date:date('2024-12-31'), active:false, position:'manager'}]->(o);
MATCH (p:Person {person_id:'PER-027'}), (o:Organisation {org_id:'ORG-003'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-01-01'), to_date:null, active:true, position:'consultant'}]->(o);
MATCH (p:Person {person_id:'PER-026'}), (o:Organisation {org_id:'ORG-001'}) CREATE (p)-[:WORKS_FOR {from_date:date('2023-01-01'), to_date:null, active:true, position:'leader'}]->(o);
MATCH (p:Person {person_id:'PER-028'}), (o:Organisation {org_id:'ORG-004'}) CREATE (p)-[:WORKS_FOR {from_date:date('2024-01-01'), to_date:null, active:true, position:'associate'}]->(o);
MATCH (p:Person {person_id:'PER-028'}), (o:Organisation {org_id:'ORG-003'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-06-01'), to_date:null, active:true, position:'courier'}]->(o);
MATCH (p:Person {person_id:'PER-032'}), (o:Organisation {org_id:'ORG-001'}) CREATE (p)-[:WORKS_FOR {from_date:date('2025-09-01'), to_date:null, active:true, position:'associate'}]->(o);


// ────────────────────────────────────────────────────────────
// 16. Person → Incident (SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES)
// ────────────────────────────────────────────────────────────

// INC-001: Armed robbery, Northbridge
MATCH (p:Person {person_id:'PER-007'}), (i:Incident {incident_id:'INC-001'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-015'}), (i:Incident {incident_id:'INC-001'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-021'}), (i:Incident {incident_id:'INC-001'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-022'}), (i:Incident {incident_id:'INC-001'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-001'}), (i:Incident {incident_id:'INC-001'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-002: Drug offence, Midland
MATCH (p:Person {person_id:'PER-008'}), (i:Incident {incident_id:'INC-002'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-013'}), (i:Incident {incident_id:'INC-002'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-002'}), (i:Incident {incident_id:'INC-002'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-005'}), (i:Incident {incident_id:'INC-002'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-003: Assault, Northbridge — NOTE: Kovac (PER-009) is suspect here but witness elsewhere
MATCH (p:Person {person_id:'PER-009'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-017'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-024'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-025'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-001'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-003'}), (i:Incident {incident_id:'INC-003'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-004: Burglary, Fremantle
MATCH (p:Person {person_id:'PER-014'}), (i:Incident {incident_id:'INC-004'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-016'}), (i:Incident {incident_id:'INC-004'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-023'}), (i:Incident {incident_id:'INC-004'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-004'}), (i:Incident {incident_id:'INC-004'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-005: Fraud, Perth CBD
MATCH (p:Person {person_id:'PER-011'}), (i:Incident {incident_id:'INC-005'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-012'}), (i:Incident {incident_id:'INC-005'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-020'}), (i:Incident {incident_id:'INC-005'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-003'}), (i:Incident {incident_id:'INC-005'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-006'}), (i:Incident {incident_id:'INC-005'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-006: Homicide, Cannington — CRITICAL SEVERITY
MATCH (p:Person {person_id:'PER-009'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-010'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-018'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-023'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-004'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-005'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-006'}), (i:Incident {incident_id:'INC-006'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-007: Drug offence, Northbridge (Lake St)
MATCH (p:Person {person_id:'PER-007'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-008'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-029'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-022'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-032'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-002'}), (i:Incident {incident_id:'INC-007'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-008: Robbery, Midland — NOTE: cross-role: Sarah Nguyen (PER-015, normally victim) is witness here
MATCH (p:Person {person_id:'PER-010'}), (i:Incident {incident_id:'INC-008'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-019'}), (i:Incident {incident_id:'INC-008'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-015'}), (i:Incident {incident_id:'INC-008'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-002'}), (i:Incident {incident_id:'INC-008'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-003'}), (i:Incident {incident_id:'INC-008'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-009: Assault, Scarborough — NOTE: cross-role: Kovac (PER-009, suspect in INC-003/006) is witness here
MATCH (p:Person {person_id:'PER-013'}), (i:Incident {incident_id:'INC-009'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-019'}), (i:Incident {incident_id:'INC-009'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-009'}), (i:Incident {incident_id:'INC-009'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-006'}), (i:Incident {incident_id:'INC-009'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-010: Traffic, Joondalup
MATCH (p:Person {person_id:'PER-014'}), (i:Incident {incident_id:'INC-010'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-035'}), (i:Incident {incident_id:'INC-010'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-025'}), (i:Incident {incident_id:'INC-010'}) CREATE (p)-[:WITNESSED]->(i);
MATCH (p:Person {person_id:'PER-003'}), (i:Incident {incident_id:'INC-010'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-011: Burglary, Victoria Park (cold case)
MATCH (p:Person {person_id:'PER-020'}), (i:Incident {incident_id:'INC-011'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-004'}), (i:Incident {incident_id:'INC-011'}) CREATE (p)-[:INVESTIGATES]->(i);

// INC-012: Fraud, Perth CBD — linked to INC-005
MATCH (p:Person {person_id:'PER-011'}), (i:Incident {incident_id:'INC-012'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-027'}), (i:Incident {incident_id:'INC-012'}) CREATE (p)-[:SUSPECTED_OF]->(i);
MATCH (p:Person {person_id:'PER-016'}), (i:Incident {incident_id:'INC-012'}) CREATE (p)-[:VICTIM_OF]->(i);
MATCH (p:Person {person_id:'PER-006'}), (i:Incident {incident_id:'INC-012'}) CREATE (p)-[:INVESTIGATES]->(i);
MATCH (p:Person {person_id:'PER-001'}), (i:Incident {incident_id:'INC-012'}) CREATE (p)-[:INVESTIGATES]->(i);


// ────────────────────────────────────────────────────────────
// 17. Person → Case (ASSIGNED_TO) — officers only
// ────────────────────────────────────────────────────────────

MATCH (p:Person {person_id:'PER-001'}), (c:Case {case_id:'CASE-001'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-003'}), (c:Case {case_id:'CASE-001'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-002'}), (c:Case {case_id:'CASE-002'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-005'}), (c:Case {case_id:'CASE-002'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-006'}), (c:Case {case_id:'CASE-003'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-003'}), (c:Case {case_id:'CASE-003'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-004'}), (c:Case {case_id:'CASE-004'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-005'}), (c:Case {case_id:'CASE-004'}) CREATE (p)-[:ASSIGNED_TO]->(c);
MATCH (p:Person {person_id:'PER-006'}), (c:Case {case_id:'CASE-004'}) CREATE (p)-[:ASSIGNED_TO]->(c);


// ────────────────────────────────────────────────────────────
// 18. Person → Evidence (COLLECTED) — officers collecting evidence
// ────────────────────────────────────────────────────────────

MATCH (p:Person {person_id:'PER-001'}), (e:Evidence {evidence_id:'EVI-001'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-001'}), (e:Evidence {evidence_id:'EVI-002'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-001'}), (e:Evidence {evidence_id:'EVI-008'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-002'}), (e:Evidence {evidence_id:'EVI-003'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-003'}), (e:Evidence {evidence_id:'EVI-004'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-006'}), (e:Evidence {evidence_id:'EVI-005'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-004'}), (e:Evidence {evidence_id:'EVI-006'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-005'}), (e:Evidence {evidence_id:'EVI-007'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-006'}), (e:Evidence {evidence_id:'EVI-009'}) CREATE (p)-[:COLLECTED]->(e);
MATCH (p:Person {person_id:'PER-004'}), (e:Evidence {evidence_id:'EVI-010'}) CREATE (p)-[:COLLECTED]->(e);


// ────────────────────────────────────────────────────────────
// 19. Incident → Location (OCCURRED_AT)
// ────────────────────────────────────────────────────────────

MATCH (i:Incident {incident_id:'INC-001'}), (l:Location {location_id:'LOC-001'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-002'}), (l:Location {location_id:'LOC-004'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-003'}), (l:Location {location_id:'LOC-002'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-004'}), (l:Location {location_id:'LOC-007'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-005'}), (l:Location {location_id:'LOC-008'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-006'}), (l:Location {location_id:'LOC-009'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-007'}), (l:Location {location_id:'LOC-006'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-008'}), (l:Location {location_id:'LOC-010'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-009'}), (l:Location {location_id:'LOC-011'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-010'}), (l:Location {location_id:'LOC-012'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-011'}), (l:Location {location_id:'LOC-013'}) CREATE (i)-[:OCCURRED_AT]->(l);
MATCH (i:Incident {incident_id:'INC-012'}), (l:Location {location_id:'LOC-014'}) CREATE (i)-[:OCCURRED_AT]->(l);


// ────────────────────────────────────────────────────────────
// 20. Case → Incident (CONTAINS)
// ────────────────────────────────────────────────────────────

MATCH (c:Case {case_id:'CASE-001'}), (i:Incident {incident_id:'INC-001'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-001'}), (i:Incident {incident_id:'INC-003'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-001'}), (i:Incident {incident_id:'INC-007'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-002'}), (i:Incident {incident_id:'INC-002'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-002'}), (i:Incident {incident_id:'INC-007'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-003'}), (i:Incident {incident_id:'INC-005'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-003'}), (i:Incident {incident_id:'INC-012'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-004'}), (i:Incident {incident_id:'INC-006'}) CREATE (c)-[:CONTAINS]->(i);
MATCH (c:Case {case_id:'CASE-004'}), (i:Incident {incident_id:'INC-008'}) CREATE (c)-[:CONTAINS]->(i);


// ────────────────────────────────────────────────────────────
// 21. Case → Evidence (HAS_EVIDENCE)
// ────────────────────────────────────────────────────────────

MATCH (c:Case {case_id:'CASE-001'}), (e:Evidence {evidence_id:'EVI-001'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-001'}), (e:Evidence {evidence_id:'EVI-002'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-001'}), (e:Evidence {evidence_id:'EVI-004'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-001'}), (e:Evidence {evidence_id:'EVI-008'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-002'}), (e:Evidence {evidence_id:'EVI-003'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-003'}), (e:Evidence {evidence_id:'EVI-005'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-003'}), (e:Evidence {evidence_id:'EVI-009'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-004'}), (e:Evidence {evidence_id:'EVI-004'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-004'}), (e:Evidence {evidence_id:'EVI-006'}) CREATE (c)-[:HAS_EVIDENCE]->(e);
MATCH (c:Case {case_id:'CASE-004'}), (e:Evidence {evidence_id:'EVI-007'}) CREATE (c)-[:HAS_EVIDENCE]->(e);


// ────────────────────────────────────────────────────────────
// 22. Evidence → Incident (RELATED_TO)
// ────────────────────────────────────────────────────────────

MATCH (e:Evidence {evidence_id:'EVI-001'}), (i:Incident {incident_id:'INC-001'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-002'}), (i:Incident {incident_id:'INC-001'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-003'}), (i:Incident {incident_id:'INC-002'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-004'}), (i:Incident {incident_id:'INC-003'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-005'}), (i:Incident {incident_id:'INC-005'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-006'}), (i:Incident {incident_id:'INC-006'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-007'}), (i:Incident {incident_id:'INC-006'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-008'}), (i:Incident {incident_id:'INC-001'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-009'}), (i:Incident {incident_id:'INC-012'}) CREATE (e)-[:RELATED_TO]->(i);
MATCH (e:Evidence {evidence_id:'EVI-010'}), (i:Incident {incident_id:'INC-004'}) CREATE (e)-[:RELATED_TO]->(i);


// ────────────────────────────────────────────────────────────
// 23. Evidence → Location (COLLECTED_AT)
// ────────────────────────────────────────────────────────────

MATCH (e:Evidence {evidence_id:'EVI-001'}), (l:Location {location_id:'LOC-001'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-002'}), (l:Location {location_id:'LOC-001'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-003'}), (l:Location {location_id:'LOC-004'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-004'}), (l:Location {location_id:'LOC-002'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-005'}), (l:Location {location_id:'LOC-008'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-006'}), (l:Location {location_id:'LOC-009'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-007'}), (l:Location {location_id:'LOC-009'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-008'}), (l:Location {location_id:'LOC-001'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-009'}), (l:Location {location_id:'LOC-014'}) CREATE (e)-[:COLLECTED_AT]->(l);
MATCH (e:Evidence {evidence_id:'EVI-010'}), (l:Location {location_id:'LOC-007'}) CREATE (e)-[:COLLECTED_AT]->(l);


// ────────────────────────────────────────────────────────────
// 24. Evidence → Person (LINKED_TO)
// ────────────────────────────────────────────────────────────

MATCH (e:Evidence {evidence_id:'EVI-001'}), (p:Person {person_id:'PER-007'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-002'}), (p:Person {person_id:'PER-007'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-003'}), (p:Person {person_id:'PER-008'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-004'}), (p:Person {person_id:'PER-009'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-006'}), (p:Person {person_id:'PER-009'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-007'}), (p:Person {person_id:'PER-010'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-009'}), (p:Person {person_id:'PER-011'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-009'}), (p:Person {person_id:'PER-027'}) CREATE (e)-[:LINKED_TO]->(p);
MATCH (e:Evidence {evidence_id:'EVI-010'}), (p:Person {person_id:'PER-014'}) CREATE (e)-[:LINKED_TO]->(p);


// ────────────────────────────────────────────────────────────
// 25. Vehicle → Location (SEEN_AT, REGISTERED_AT)
// ────────────────────────────────────────────────────────────

// SEEN_AT sightings
MATCH (v:Vehicle {vehicle_id:'VEH-001'}), (l:Location {location_id:'LOC-001'}) CREATE (v)-[:SEEN_AT {date:date('2026-01-15'), time:time('22:25:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-001'}), (l:Location {location_id:'LOC-006'}) CREATE (v)-[:SEEN_AT {date:date('2026-02-15'), time:time('15:30:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-002'}), (l:Location {location_id:'LOC-004'}) CREATE (v)-[:SEEN_AT {date:date('2026-02-03'), time:time('14:00:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-003'}), (l:Location {location_id:'LOC-009'}) CREATE (v)-[:SEEN_AT {date:date('2026-03-01'), time:time('19:30:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-005'}), (l:Location {location_id:'LOC-010'}) CREATE (v)-[:SEEN_AT {date:date('2026-02-28'), time:time('20:05:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-005'}), (l:Location {location_id:'LOC-012'}) CREATE (v)-[:SEEN_AT {date:date('2026-01-05'), time:time('07:35:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-006'}), (l:Location {location_id:'LOC-002'}) CREATE (v)-[:SEEN_AT {date:date('2026-01-10'), time:time('19:50:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-009'}), (l:Location {location_id:'LOC-008'}) CREATE (v)-[:SEEN_AT {date:date('2026-01-28'), time:time('10:00:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-009'}), (l:Location {location_id:'LOC-002'}) CREATE (v)-[:SEEN_AT {date:date('2026-02-08'), time:time('20:30:00')}]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-010'}), (l:Location {location_id:'LOC-014'}) CREATE (v)-[:SEEN_AT {date:date('2026-02-10'), time:time('11:30:00')}]->(l);

// REGISTERED_AT
MATCH (v:Vehicle {vehicle_id:'VEH-001'}), (l:Location {location_id:'LOC-003'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-002'}), (l:Location {location_id:'LOC-001'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-003'}), (l:Location {location_id:'LOC-009'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-004'}), (l:Location {location_id:'LOC-002'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-005'}), (l:Location {location_id:'LOC-012'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-006'}), (l:Location {location_id:'LOC-015'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-007'}), (l:Location {location_id:'LOC-008'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-008'}), (l:Location {location_id:'LOC-018'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-009'}), (l:Location {location_id:'LOC-015'}) CREATE (v)-[:REGISTERED_AT]->(l);
MATCH (v:Vehicle {vehicle_id:'VEH-010'}), (l:Location {location_id:'LOC-014'}) CREATE (v)-[:REGISTERED_AT]->(l);


// ────────────────────────────────────────────────────────────
// 26. Vehicle → Incident (USED_IN)
// ────────────────────────────────────────────────────────────

MATCH (v:Vehicle {vehicle_id:'VEH-001'}), (i:Incident {incident_id:'INC-002'}) CREATE (v)-[:USED_IN]->(i);
MATCH (v:Vehicle {vehicle_id:'VEH-003'}), (i:Incident {incident_id:'INC-006'}) CREATE (v)-[:USED_IN]->(i);
MATCH (v:Vehicle {vehicle_id:'VEH-005'}), (i:Incident {incident_id:'INC-008'}) CREATE (v)-[:USED_IN]->(i);
MATCH (v:Vehicle {vehicle_id:'VEH-005'}), (i:Incident {incident_id:'INC-010'}) CREATE (v)-[:USED_IN]->(i);
MATCH (v:Vehicle {vehicle_id:'VEH-002'}), (i:Incident {incident_id:'INC-007'}) CREATE (v)-[:USED_IN]->(i);


// ────────────────────────────────────────────────────────────
// 27. Phone ↔ Phone (CALLED, MESSAGED)
// ────────────────────────────────────────────────────────────

// Whitfield (DEV-001) ↔ Petrova (DEV-005)
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-005'}) CREATE (a)-[:CALLED {date:date('2026-01-10'), time:time('19:45:00'), duration:342}]->(b);
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-005'}) CREATE (a)-[:CALLED {date:date('2026-01-14'), time:time('21:10:00'), duration:128}]->(b);
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-005'}) CREATE (a)-[:MESSAGED {date:date('2026-01-15'), time:time('18:00:00')}]->(b);

// Whitfield (DEV-001) ↔ Kovac (DEV-003)
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-003'}) CREATE (a)-[:CALLED {date:date('2026-02-19'), time:time('23:30:00'), duration:67}]->(b);
MATCH (a:Phone {device_id:'DEV-003'}), (b:Phone {device_id:'DEV-001'}) CREATE (a)-[:CALLED {date:date('2026-02-20'), time:time('00:15:00'), duration:45}]->(b);

// Whitfield (DEV-001) ↔ Maric (DEV-011)
MATCH (a:Phone {device_id:'DEV-011'}), (b:Phone {device_id:'DEV-001'}) CREATE (a)-[:CALLED {date:date('2026-01-12'), time:time('15:40:00'), duration:210}]->(b);
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-011'}) CREATE (a)-[:MESSAGED {date:date('2026-01-13'), time:time('09:00:00')}]->(b);

// Kovac (DEV-003) ↔ Birch (DEV-004)
MATCH (a:Phone {device_id:'DEV-003'}), (b:Phone {device_id:'DEV-004'}) CREATE (a)-[:CALLED {date:date('2026-02-24'), time:time('18:30:00'), duration:180}]->(b);
MATCH (a:Phone {device_id:'DEV-004'}), (b:Phone {device_id:'DEV-003'}) CREATE (a)-[:MESSAGED {date:date('2026-02-25'), time:time('17:00:00')}]->(b);

// Hassan (DEV-006) ↔ Gallagher (DEV-002)
MATCH (a:Phone {device_id:'DEV-006'}), (b:Phone {device_id:'DEV-002'}) CREATE (a)-[:CALLED {date:date('2026-02-07'), time:time('14:20:00'), duration:420}]->(b);
MATCH (a:Phone {device_id:'DEV-006'}), (b:Phone {device_id:'DEV-002'}) CREATE (a)-[:CALLED {date:date('2026-02-09'), time:time('10:00:00'), duration:300}]->(b);
MATCH (a:Phone {device_id:'DEV-006'}), (b:Phone {device_id:'DEV-002'}) CREATE (a)-[:MESSAGED {date:date('2026-02-08'), time:time('08:45:00')}]->(b);

// Hassan (DEV-006) ↔ Wu (DEV-007)
MATCH (a:Phone {device_id:'DEV-007'}), (b:Phone {device_id:'DEV-006'}) CREATE (a)-[:CALLED {date:date('2026-01-25'), time:time('16:00:00'), duration:90}]->(b);

// Santos (DEV-008) ↔ Doyle (DEV-009)
MATCH (a:Phone {device_id:'DEV-008'}), (b:Phone {device_id:'DEV-009'}) CREATE (a)-[:CALLED {date:date('2026-02-27'), time:time('22:00:00'), duration:55}]->(b);
MATCH (a:Phone {device_id:'DEV-008'}), (b:Phone {device_id:'DEV-009'}) CREATE (a)-[:MESSAGED {date:date('2026-02-28'), time:time('10:30:00')}]->(b);
MATCH (a:Phone {device_id:'DEV-009'}), (b:Phone {device_id:'DEV-008'}) CREATE (a)-[:CALLED {date:date('2025-11-09'), time:time('14:00:00'), duration:180}]->(b);

// Whitfield (DEV-001) ↔ Thompson (DEV-013)
MATCH (a:Phone {device_id:'DEV-001'}), (b:Phone {device_id:'DEV-013'}) CREATE (a)-[:CALLED {date:date('2026-01-14'), time:time('18:30:00'), duration:95}]->(b);

// Santos (DEV-008) ↔ Maric (DEV-011) — broker connection
MATCH (a:Phone {device_id:'DEV-011'}), (b:Phone {device_id:'DEV-008'}) CREATE (a)-[:CALLED {date:date('2026-02-15'), time:time('12:00:00'), duration:150}]->(b);

// Informant Park (DEV-012) ↔ Santos (DEV-008)
MATCH (a:Phone {device_id:'DEV-012'}), (b:Phone {device_id:'DEV-008'}) CREATE (a)-[:CALLED {date:date('2026-03-04'), time:time('20:00:00'), duration:240}]->(b);


// ────────────────────────────────────────────────────────────
// 28. Phone → Location (LOCATED_AT) — cell tower pings
// ────────────────────────────────────────────────────────────

MATCH (ph:Phone {device_id:'DEV-001'}), (l:Location {location_id:'LOC-001'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-01-15'), time:time('22:28:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-001'}), (l:Location {location_id:'LOC-006'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-02-15'), time:time('16:05:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-005'}), (l:Location {location_id:'LOC-002'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-01-10'), time:time('20:05:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-003'}), (l:Location {location_id:'LOC-009'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-03-01'), time:time('19:45:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-004'}), (l:Location {location_id:'LOC-009'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-03-01'), time:time('19:50:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-004'}), (l:Location {location_id:'LOC-010'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-02-28'), time:time('20:00:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-006'}), (l:Location {location_id:'LOC-008'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-01-28'), time:time('10:15:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-009'}), (l:Location {location_id:'LOC-012'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-01-05'), time:time('07:38:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-011'}), (l:Location {location_id:'LOC-002'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-01-10'), time:time('19:55:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-011'}), (l:Location {location_id:'LOC-015'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-02-20'), time:time('14:30:00')}]->(l);
MATCH (ph:Phone {device_id:'DEV-014'}), (l:Location {location_id:'LOC-010'}) CREATE (ph)-[:LOCATED_AT {date:date('2026-02-28'), time:time('19:55:00')}]->(l);


// ────────────────────────────────────────────────────────────
// 29. Organisation → Incident (INVOLVED_IN)
// ────────────────────────────────────────────────────────────

MATCH (o:Organisation {org_id:'ORG-001'}), (i:Incident {incident_id:'INC-001'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-001'}), (i:Incident {incident_id:'INC-007'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-003'}), (i:Incident {incident_id:'INC-005'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-003'}), (i:Incident {incident_id:'INC-012'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-004'}), (i:Incident {incident_id:'INC-006'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-004'}), (i:Incident {incident_id:'INC-008'}) CREATE (o)-[:INVOLVED_IN]->(i);
MATCH (o:Organisation {org_id:'ORG-005'}), (i:Incident {incident_id:'INC-012'}) CREATE (o)-[:INVOLVED_IN]->(i);


// ────────────────────────────────────────────────────────────
// 30. Communication relationships
// ────────────────────────────────────────────────────────────

// COMM-001: Meeting — Whitfield & Petrova at Northbridge bar
MATCH (p:Person {person_id:'PER-007'}), (cm:Communication {comm_id:'COMM-001'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-008'}), (cm:Communication {comm_id:'COMM-001'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-001'}), (l:Location {location_id:'LOC-002'}) CREATE (cm)-[:TOOK_PLACE_AT]->(l);
MATCH (cm:Communication {comm_id:'COMM-001'}), (c:Case {case_id:'CASE-001'}) CREATE (cm)-[:RELATES_TO]->(c);
MATCH (cm:Communication {comm_id:'COMM-001'}), (i:Incident {incident_id:'INC-001'}) CREATE (cm)-[:RELATES_TO]->(i);

// COMM-002: Intercepted call — Whitfield & Petrova re: shipment
MATCH (p:Person {person_id:'PER-007'}), (cm:Communication {comm_id:'COMM-002'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-008'}), (cm:Communication {comm_id:'COMM-002'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-002'}), (i:Incident {incident_id:'INC-002'}) CREATE (cm)-[:RELATES_TO]->(i);

// COMM-003: Intel report — Pacific Trading fraud
MATCH (p:Person {person_id:'PER-011'}), (cm:Communication {comm_id:'COMM-003'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-027'}), (cm:Communication {comm_id:'COMM-003'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-003'}), (i:Incident {incident_id:'INC-005'}) CREATE (cm)-[:RELATES_TO]->(i);
MATCH (cm:Communication {comm_id:'COMM-003'}), (c:Case {case_id:'CASE-003'}) CREATE (cm)-[:RELATES_TO]->(c);

// COMM-004: Meeting — Kovac, Birch, unknown at Cannington
MATCH (p:Person {person_id:'PER-009'}), (cm:Communication {comm_id:'COMM-004'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-010'}), (cm:Communication {comm_id:'COMM-004'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-028'}), (cm:Communication {comm_id:'COMM-004'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-004'}), (l:Location {location_id:'LOC-009'}) CREATE (cm)-[:TOOK_PLACE_AT]->(l);
MATCH (cm:Communication {comm_id:'COMM-004'}), (c:Case {case_id:'CASE-004'}) CREATE (cm)-[:RELATES_TO]->(c);

// COMM-005: Intercepted SMS — "the Northbridge job"
MATCH (p:Person {person_id:'PER-007'}), (cm:Communication {comm_id:'COMM-005'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-026'}), (cm:Communication {comm_id:'COMM-005'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-005'}), (i:Incident {incident_id:'INC-001'}) CREATE (cm)-[:RELATES_TO]->(i);

// COMM-006: Email — Hassan & Gallagher re: property transfers
MATCH (p:Person {person_id:'PER-011'}), (cm:Communication {comm_id:'COMM-006'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-027'}), (cm:Communication {comm_id:'COMM-006'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-006'}), (i:Incident {incident_id:'INC-012'}) CREATE (cm)-[:RELATES_TO]->(i);

// COMM-007: Informant debrief — Leon Park on East Side Boys
MATCH (p:Person {person_id:'PER-030'}), (cm:Communication {comm_id:'COMM-007'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-005'}), (cm:Communication {comm_id:'COMM-007'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-007'}), (l:Location {location_id:'LOC-010'}) CREATE (cm)-[:TOOK_PLACE_AT]->(l);
MATCH (cm:Communication {comm_id:'COMM-007'}), (i:Incident {incident_id:'INC-002'}) CREATE (cm)-[:RELATES_TO]->(i);
MATCH (cm:Communication {comm_id:'COMM-007'}), (c:Case {case_id:'CASE-002'}) CREATE (cm)-[:RELATES_TO]->(c);

// COMM-008: Observed meeting — Leon Park & Ricky Santos at Wanneroo
MATCH (p:Person {person_id:'PER-030'}), (cm:Communication {comm_id:'COMM-008'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-013'}), (cm:Communication {comm_id:'COMM-008'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-008'}), (l:Location {location_id:'LOC-017'}) CREATE (cm)-[:TOOK_PLACE_AT]->(l);
MATCH (cm:Communication {comm_id:'COMM-008'}), (c:Case {case_id:'CASE-002'}) CREATE (cm)-[:RELATES_TO]->(c);

// COMM-009: Intercepted call — Doyle & Santos re: stolen jewellery
MATCH (p:Person {person_id:'PER-014'}), (cm:Communication {comm_id:'COMM-009'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-013'}), (cm:Communication {comm_id:'COMM-009'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-009'}), (i:Incident {incident_id:'INC-004'}) CREATE (cm)-[:RELATES_TO]->(i);

// COMM-010: Observed meeting — Hassan & Gallagher at Perth CBD cafe
MATCH (p:Person {person_id:'PER-006'}), (cm:Communication {comm_id:'COMM-010'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-011'}), (cm:Communication {comm_id:'COMM-010'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (p:Person {person_id:'PER-027'}), (cm:Communication {comm_id:'COMM-010'}) CREATE (p)-[:PARTICIPATED_IN]->(cm);
MATCH (cm:Communication {comm_id:'COMM-010'}), (l:Location {location_id:'LOC-014'}) CREATE (cm)-[:TOOK_PLACE_AT]->(l);
MATCH (cm:Communication {comm_id:'COMM-010'}), (i:Incident {incident_id:'INC-012'}) CREATE (cm)-[:RELATES_TO]->(i);


// ────────────────────────────────────────────────────────────
// 31. VERIFICATION QUERIES
// ────────────────────────────────────────────────────────────

// Run after loading to verify:
// MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label;
// MATCH ()-[r]->() RETURN type(r) AS rel_type, count(*) AS count ORDER BY rel_type;
//
// Expected node counts:
//   Person: 35, Incident: 12, Case: 4, Location: 18,
//   Vehicle: 10, Phone: 14, Evidence: 10, Organisation: 5,
//   Communication: 10  =>  Total: 117 nodes
//
// Key cross-role patterns to verify:
//   PER-009 (Kovac):  SUSPECTED_OF INC-003, INC-006  |  WITNESSED INC-009
//   PER-015 (Nguyen): VICTIM_OF INC-001              |  WITNESSED INC-008
//   PER-023 (Walsh):  WITNESSED INC-004              |  WITNESSED INC-006
//
// Historical edges to verify:
//   PER-007 LIVES_AT LOC-004 (active:false) + LOC-003 (active:true)
//   PER-009 LIVES_AT LOC-016 (active:false) + LOC-009 (active:true)
//   PER-010 OWNS VEH-001 (active:false), PER-007 OWNS VEH-001 (active:true)
//   PER-008 USES_PHONE DEV-002 (active:false) + DEV-005 (active:true)
