# scratchpad/gen_benchmark_v3.py
"""Author data/benchmark-v3.json from the 7.1 skeleton.

Writes cypher_default + per-interpretation Cypher for all 120 items, computes
num_hops from extract_schema_pattern (the same relationship count the 7.2 harness
gate 7 uses), and runs the offline structural checks (distribution, hop<=3, coverage)
before the live harness proves executability on Kaya.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pipeline.schema_linker.pattern_extraction import extract_schema_pattern

ROOT = Path(__file__).resolve().parents[1]
SKELETON = ROOT / "data" / "benchmark-v3-skeleton.json"
OUT = ROOT / "data" / "benchmark-v3.json"

V3_REL_TYPES = [
    "SUSPECTED_OF", "WITNESSED", "VICTIM_OF", "INVESTIGATES", "CONTAINS",
    "OCCURRED_AT", "LIVES_AT", "OWNS", "USES_PHONE", "CALLED", "ASSOCIATED_WITH",
]


def hops(cypher: str) -> int:
    """Relationship count of the extracted schema pattern — the gate-7 definition."""
    pat = extract_schema_pattern(cypher)
    return pat.count("[") if pat else 0


# ── Per-item Cypher. Each entry: id -> (default, [(interp, cypher), ...]) ──────────
# Incident identity is by incident_id where the incident is named descriptively, and by
# crime_type (+ suburb/address via OCCURRED_AT) where the question phrases it that way.
ROLE_ANY = "MATCH (p:Person)-[r]->(i:Incident {{incident_id:'{iid}'}}) RETURN DISTINCT p.name"
ROLE_ONE = "MATCH (p:Person)-[:{rel}]->(i:Incident {{incident_id:'{iid}'}}) RETURN DISTINCT p.name"


def role_any(iid: str) -> str:
    return ROLE_ANY.format(iid=iid)


def role_one(rel: str, iid: str) -> str:
    return ROLE_ONE.format(rel=rel, iid=iid)


def schema_item(iid: str, interps: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
    return role_any(iid), interps


# suspects/witnesses/investigators/victim shorthand for schema items
def S(iid): return ("Only suspects", role_one("SUSPECTED_OF", iid))
def W(iid): return ("Only witnesses", role_one("WITNESSED", iid))
def I(iid): return ("Only investigating officers", role_one("INVESTIGATES", iid))
def V(iid): return ("Only the victim", role_one("VICTIM_OF", iid))
def S1(iid): return ("Only the suspect", role_one("SUSPECTED_OF", iid))
def W1(iid): return ("Only the witness", role_one("WITNESSED", iid))
def I1(iid): return ("Only the investigating officer", role_one("INVESTIGATES", iid))


ITEMS: dict[str, tuple[str, list[tuple[str, str]]]] = {}

# ── Unambiguous Q-V3-001 .. 040 ──────────────────────────────────────────────────
ITEMS["Q-V3-001"] = ("MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {crime_type:'homicide'}) RETURN p.name", [])
ITEMS["Q-V3-002"] = ("MATCH (p:Person)-[:INVESTIGATES]->(:Incident {crime_type:'homicide'}) RETURN p.name", [])
ITEMS["Q-V3-003"] = ("MATCH (p:Person)-[:VICTIM_OF]->(:Incident {crime_type:'homicide'}) RETURN p.name", [])
ITEMS["Q-V3-004"] = ("MATCH (:Case {case_id:'CASE-V3-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id", [])
ITEMS["Q-V3-005"] = ("MATCH (c:Case)-[:CONTAINS]->(:Incident {crime_type:'homicide'}) RETURN c.case_name", [])
ITEMS["Q-V3-006"] = ("MATCH (:Person {name:'Daniel Kim'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number", [])
ITEMS["Q-V3-007"] = ("MATCH (:Person {name:'James Whitfield'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id", [])
ITEMS["Q-V3-008"] = ("MATCH (p:Person)-[:LIVES_AT {active:true}]->(:Location {address:'55 Beaufort Street'}) RETURN p.name", [])
ITEMS["Q-V3-009"] = ("MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name", [])
ITEMS["Q-V3-010"] = ("MATCH (:Phone {phone_number:'0412 345 678'})-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number", [])
ITEMS["Q-V3-011"] = ("MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id", [])
ITEMS["Q-V3-012"] = ("MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'William Street' RETURN p.name", [])
ITEMS["Q-V3-013"] = ("MATCH (i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(l:Location {suburb:'Fremantle'}) RETURN l.address", [])
ITEMS["Q-V3-014"] = ("MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(:Location {suburb:'Fremantle'}) RETURN p.name", [])
ITEMS["Q-V3-015"] = ("MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(:Location {suburb:'Scarborough'}) RETURN p.name", [])
ITEMS["Q-V3-016"] = ("MATCH (:Incident {crime_type:'homicide'})-[:OCCURRED_AT]->(l:Location) RETURN l.address", [])
ITEMS["Q-V3-017"] = ("MATCH (:Person {name:'Ricky Santos'})-[:OWNS {active:false}]->(v:Vehicle) RETURN v.vehicle_id", [])
ITEMS["Q-V3-018"] = ("MATCH (p:Person)-[:USES_PHONE {active:true}]->(:Phone {phone_number:'0423 987 654'}) RETURN p.name", [])
ITEMS["Q-V3-019"] = ("MATCH (:Phone {phone_number:'0478 444 555'})-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number", [])
ITEMS["Q-V3-020"] = ("MATCH (p:Person)-[:LIVES_AT {active:true}]->(:Location {address:'35 Walcott Street'}) RETURN p.name", [])
ITEMS["Q-V3-021"] = ("MATCH (:Case {case_id:'CASE-V3-001'})-[:CONTAINS]->(i:Incident)<-[:SUSPECTED_OF]-(p:Person) RETURN DISTINCT p.name", [])
ITEMS["Q-V3-022"] = ("MATCH (:Case {case_id:'CASE-V3-004'})-[:CONTAINS]->(i:Incident)<-[:INVESTIGATES]-(p:Person) RETURN DISTINCT p.name", [])
ITEMS["Q-V3-023"] = ("MATCH (:Case {case_id:'CASE-V3-002'})-[:CONTAINS]->(i:Incident)-[:OCCURRED_AT]->(l:Location) RETURN DISTINCT l.suburb", [])
ITEMS["Q-V3-024"] = ("MATCH (:Person {name:'James Whitfield'})-[:USES_PHONE {active:true}]->(:Phone)-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number", [])
ITEMS["Q-V3-025"] = ("MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(a:Person)-[:SUSPECTED_OF]->(:Incident) RETURN DISTINCT a.name", [])
ITEMS["Q-V3-026"] = ("MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)-[:OCCURRED_AT]->(l:Location), (p)-[:LIVES_AT {active:true}]->(home:Location) WHERE l.address CONTAINS 'William Street' RETURN DISTINCT home.address", [])
ITEMS["Q-V3-027"] = ("MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {crime_type:'homicide'}), (p)-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id", [])
ITEMS["Q-V3-028"] = ("MATCH (p:Person)-[:WITNESSED]->(i:Incident)-[:OCCURRED_AT]->(l:Location), (p)-[:USES_PHONE {active:true}]->(ph:Phone) WHERE l.address CONTAINS 'William Street' RETURN ph.phone_number", [])
ITEMS["Q-V3-029"] = ("MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'St Georges Terrace' RETURN p.name", [])
ITEMS["Q-V3-030"] = ("MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {suburb:'Cannington'}) WHERE l.address CONTAINS 'Albany Highway' RETURN p.name", [])
ITEMS["Q-V3-031"] = ("MATCH (c:Case)-[:CONTAINS]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(:Location {suburb:'Midland'}) RETURN c.case_name", [])
ITEMS["Q-V3-032"] = ("MATCH (p:Person)-[:VICTIM_OF]->(i:Incident {crime_type:'burglary'})-[:OCCURRED_AT]->(:Location {suburb:'Fremantle'}) RETURN p.name", [])
ITEMS["Q-V3-033"] = ("MATCH (a:Phone)-[:CALLED]->(:Phone)<-[:USES_PHONE {active:true}]-(:Person {name:'Ricky Santos'}) RETURN DISTINCT a.phone_number", [])
ITEMS["Q-V3-034"] = ("MATCH (:Person {name:'Amir Hassan'})-[:OWNS {active:true}]->(v:Vehicle) RETURN v.make, v.model", [])
ITEMS["Q-V3-035"] = ("MATCH (p:Person)-[:WITNESSED]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Lake Street' RETURN p.name", [])
ITEMS["Q-V3-036"] = ("MATCH (:Case {case_id:'CASE-V3-003'})-[:CONTAINS]->(i:Incident)<-[:INVESTIGATES]-(p:Person) RETURN DISTINCT p.name", [])
ITEMS["Q-V3-037"] = ("MATCH (:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'}) RETURN l.address", [])
ITEMS["Q-V3-038"] = ("MATCH (p:Person)-[:OWNS {active:true}]->(:Vehicle {make:'Holden', model:'Commodore'}) RETURN p.name", [])
ITEMS["Q-V3-039"] = ("MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id", [])
ITEMS["Q-V3-040"] = ("MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Hay Street' RETURN p.name", [])

# ── Schema ambiguity Q-V3-041 .. 060 ──────────────────────────────────────────────
ITEMS["Q-V3-041"] = schema_item("INC-V3-001", [S("INC-V3-001"), W("INC-V3-001"), I("INC-V3-001")])
ITEMS["Q-V3-042"] = schema_item("INC-V3-006", [S("INC-V3-006"), W("INC-V3-006"), I("INC-V3-006")])
ITEMS["Q-V3-043"] = schema_item("INC-V3-005", [S("INC-V3-005"), W("INC-V3-005"), I("INC-V3-005")])
ITEMS["Q-V3-044"] = schema_item("INC-V3-009", [S1("INC-V3-009"), W1("INC-V3-009"), I1("INC-V3-009")])
ITEMS["Q-V3-045"] = schema_item("INC-V3-007", [S("INC-V3-007"), W("INC-V3-007"), I("INC-V3-007")])
ITEMS["Q-V3-046"] = schema_item("INC-V3-008", [S1("INC-V3-008"), W1("INC-V3-008"), I("INC-V3-008")])
ITEMS["Q-V3-047"] = schema_item("INC-V3-004", [S1("INC-V3-004"), W1("INC-V3-004"), I1("INC-V3-004")])
ITEMS["Q-V3-048"] = schema_item("INC-V3-006", [S("INC-V3-006"), I("INC-V3-006"), V("INC-V3-006")])
ITEMS["Q-V3-049"] = schema_item("INC-V3-012", [S("INC-V3-012"), W1("INC-V3-012"), I("INC-V3-012")])
ITEMS["Q-V3-050"] = schema_item("INC-V3-003", [S1("INC-V3-003"), W("INC-V3-003"), I("INC-V3-003")])
ITEMS["Q-V3-051"] = schema_item("INC-V3-002", [S("INC-V3-002"), W1("INC-V3-002"), I("INC-V3-002")])
ITEMS["Q-V3-052"] = schema_item("INC-V3-010", [S1("INC-V3-010"), W1("INC-V3-010"), I1("INC-V3-010")])
ITEMS["Q-V3-053"] = schema_item("INC-V3-011", [S1("INC-V3-011"), W1("INC-V3-011"), I1("INC-V3-011")])
ITEMS["Q-V3-054"] = schema_item("INC-V3-001", [S("INC-V3-001"), V("INC-V3-001"), W("INC-V3-001")])
ITEMS["Q-V3-055"] = schema_item("INC-V3-005", [S("INC-V3-005"), I("INC-V3-005")])
ITEMS["Q-V3-056"] = schema_item("INC-V3-006", [S("INC-V3-006"), W("INC-V3-006"), I("INC-V3-006")])
ITEMS["Q-V3-057"] = schema_item("INC-V3-008", [S1("INC-V3-008"), V("INC-V3-008"), I("INC-V3-008")])
ITEMS["Q-V3-058"] = schema_item("INC-V3-006", [S("INC-V3-006"), W("INC-V3-006"), V("INC-V3-006")])
ITEMS["Q-V3-059"] = (
    "MATCH (:Case {case_id:'CASE-V3-003'})-[:CONTAINS]->(i:Incident)<-[r]-(p:Person) RETURN DISTINCT p.name",
    [("Only suspects", "MATCH (:Case {case_id:'CASE-V3-003'})-[:CONTAINS]->(i:Incident)<-[:SUSPECTED_OF]-(p:Person) RETURN DISTINCT p.name"),
     ("Only witnesses", "MATCH (:Case {case_id:'CASE-V3-003'})-[:CONTAINS]->(i:Incident)<-[:WITNESSED]-(p:Person) RETURN DISTINCT p.name"),
     ("Only investigating officers", "MATCH (:Case {case_id:'CASE-V3-003'})-[:CONTAINS]->(i:Incident)<-[:INVESTIGATES]-(p:Person) RETURN DISTINCT p.name")],
)
ITEMS["Q-V3-060"] = schema_item("INC-V3-004", [S1("INC-V3-004"), W1("INC-V3-004"), I1("INC-V3-004")])

# ── Entity ambiguity Q-V3-061 .. 080 ──────────────────────────────────────────────
ITEMS["Q-V3-061"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Tran' RETURN l.address",
    [("Megan Tran (PER-V3-002)", "MATCH (:Person {name:'Megan Tran'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("Kevin Tran (PER-V3-031)", "MATCH (:Person {name:'Kevin Tran'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-062"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Kim' RETURN l.address",
    [("Rachel Kim (PER-V3-006)", "MATCH (:Person {name:'Rachel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("Daniel Kim (PER-V3-009)", "MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-063"] = (
    "MATCH (p:Person)-[:USES_PHONE {active:true}]->(ph:Phone) WHERE p.name ENDS WITH ' Nguyen' RETURN ph.phone_number",
    [("Michael Nguyen (PER-V3-015)", "MATCH (:Person {name:'Michael Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number"),
     ("Sarah Nguyen (PER-V3-019)", "MATCH (:Person {name:'Sarah Nguyen'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number")],
)
ITEMS["Q-V3-064"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Chen' RETURN DISTINCT i.incident_id",
    [("David Chen (PER-V3-001, investigating officer)", "MATCH (:Person {name:'David Chen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Wei Chen (PER-V3-012, suspect)", "MATCH (:Person {name:'Wei Chen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-065"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Smith' RETURN DISTINCT i.incident_id",
    [("James Smith (PER-V3-016, suspect)", "MATCH (:Person {name:'James Smith'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Laura Smith (PER-V3-032, witness)", "MATCH (:Person {name:'Laura Smith'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-066"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Bennett' RETURN DISTINCT i.incident_id",
    [("Sophie Bennett (PER-V3-024)", "MATCH (:Person {name:'Sophie Bennett'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Sarah Bennett (PER-V3-025)", "MATCH (:Person {name:'Sarah Bennett'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-067"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name STARTS WITH 'James ' RETURN l.address",
    [("James Kowalski (PER-V3-004)", "MATCH (:Person {name:'James Kowalski'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("James Whitfield (PER-V3-007)", "MATCH (:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("James Smith (PER-V3-016)", "MATCH (:Person {name:'James Smith'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-068"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name STARTS WITH 'Sarah ' RETURN l.address",
    [("Sarah Nguyen (PER-V3-019)", "MATCH (:Person {name:'Sarah Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("Sarah Bennett (PER-V3-025)", "MATCH (:Person {name:'Sarah Bennett'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-069"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name = 'David Chen' OR p.alias = 'David' RETURN DISTINCT i.incident_id",
    [("David Chen (PER-V3-001, given name)", "MATCH (:Person {name:'David Chen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Wei Chen (PER-V3-012, alias 'David')", "MATCH (p:Person {alias:'David'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-070"] = (
    "MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Albany Highway' RETURN i.incident_id",
    [("Albany Highway, Cannington — homicide (INC-V3-006)", "MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Cannington'}) WHERE l.address CONTAINS 'Albany Highway' RETURN i.incident_id"),
     ("Albany Highway, Victoria Park — burglary (INC-V3-011)", "MATCH (i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Victoria Park'}) WHERE l.address CONTAINS 'Albany Highway' RETURN i.incident_id")],
)
ITEMS["Q-V3-071"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE l.address CONTAINS 'Albany Highway' RETURN p.name",
    [("Residents of Albany Highway, Cannington (LOC-V3-009)", "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {suburb:'Cannington'}) WHERE l.address CONTAINS 'Albany Highway' RETURN p.name"),
     ("Residents of Albany Highway, Victoria Park (LOC-V3-013)", "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location {suburb:'Victoria Park'}) WHERE l.address CONTAINS 'Albany Highway' RETURN p.name")],
)
ITEMS["Q-V3-072"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Tran' RETURN DISTINCT i.incident_id",
    [("Megan Tran (PER-V3-002, officer)", "MATCH (:Person {name:'Megan Tran'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Kevin Tran (PER-V3-031, witness)", "MATCH (:Person {name:'Kevin Tran'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-073"] = (
    "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) WHERE p.name ENDS WITH ' Nguyen' RETURN l.address",
    [("Michael Nguyen (PER-V3-015)", "MATCH (:Person {name:'Michael Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("Sarah Nguyen (PER-V3-019)", "MATCH (:Person {name:'Sarah Nguyen'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-074"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name ENDS WITH ' Kim' RETURN DISTINCT i.incident_id",
    [("Daniel Kim (PER-V3-009, suspect/witness)", "MATCH (:Person {name:'Daniel Kim'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Rachel Kim (PER-V3-006, officer)", "MATCH (:Person {name:'Rachel Kim'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-075"] = (
    "MATCH (p:Person)-[r]->(i:Incident) WHERE p.name STARTS WITH 'Sarah ' RETURN DISTINCT i.incident_id",
    [("Sarah Nguyen (PER-V3-019)", "MATCH (:Person {name:'Sarah Nguyen'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id"),
     ("Sarah Bennett (PER-V3-025)", "MATCH (:Person {name:'Sarah Bennett'})-[r]->(i:Incident) RETURN DISTINCT i.incident_id")],
)
ITEMS["Q-V3-076"] = (
    "MATCH (i:Incident {crime_type:'robbery'}) RETURN i.incident_id",
    [("The William Street robbery (INC-V3-001)", "MATCH (i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id"),
     ("The Midland robbery (INC-V3-008)", "MATCH (i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(:Location {suburb:'Midland'}) RETURN i.incident_id")],
)
ITEMS["Q-V3-077"] = (
    "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'}) RETURN DISTINCT p.name",
    [("Suspects of the William Street robbery (INC-V3-001)", "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN p.name"),
     ("Suspects of the Midland robbery (INC-V3-008)", "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})-[:OCCURRED_AT]->(:Location {suburb:'Midland'}) RETURN p.name")],
)
ITEMS["Q-V3-078"] = (
    "MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'assault'}) RETURN DISTINCT p.name",
    [("Witnesses of the Northbridge assault (INC-V3-003)", "MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN p.name"),
     ("Witnesses of the Scarborough assault (INC-V3-009)", "MATCH (p:Person)-[:WITNESSED]->(i:Incident {crime_type:'assault'})-[:OCCURRED_AT]->(:Location {suburb:'Scarborough'}) RETURN p.name")],
)
ITEMS["Q-V3-079"] = (
    "MATCH (i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location) RETURN l.address",
    [("The St Georges Terrace fraud (INC-V3-005)", "MATCH (i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'St Georges Terrace' RETURN l.address"),
     ("The Hay Street fraud (INC-V3-012)", "MATCH (i:Incident {crime_type:'fraud'})-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Hay Street' RETURN l.address")],
)
ITEMS["Q-V3-080"] = (
    "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'drug_offence'}) RETURN DISTINCT p.name",
    [("Investigators of the Midland drug offence (INC-V3-002)", "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident {crime_type:'drug_offence'})-[:OCCURRED_AT]->(:Location {suburb:'Midland'}) RETURN p.name"),
     ("Investigators of the Lake Street drug offence (INC-V3-007)", "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Lake Street' RETURN p.name")],
)

# ── Intent ambiguity Q-V3-081 .. 100 ──────────────────────────────────────────────
ITEMS["Q-V3-081"] = (
    "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-007'}) RETURN p.name",
    [("Return the count of suspects", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-007'}) RETURN count(p) AS n"),
     ("Return the list of suspects' names", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-007'}) RETURN p.name")],
)
ITEMS["Q-V3-082"] = (
    "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type",
    [("Return the count of incidents", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN count(i) AS n"),
     ("Return the list of incident details", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id, i.crime_type")],
)
ITEMS["Q-V3-083"] = (
    "MATCH (p:Person)-[l:LIVES_AT {active:true}]->(:Location {address:'55 Beaufort Street'}) RETURN p.name",
    [("Return just the residents' names", "MATCH (p:Person)-[l:LIVES_AT {active:true}]->(:Location {address:'55 Beaufort Street'}) RETURN p.name"),
     ("Return the residents with their move-in dates", "MATCH (p:Person)-[l:LIVES_AT {active:true}]->(:Location {address:'55 Beaufort Street'}) RETURN p.name, l.from_date")],
)
ITEMS["Q-V3-084"] = (
    "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id",
    [("Only incidents whose suburb is exactly 'Perth'", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id"),
     ("All incidents in the Perth metro area (any suburb)", "MATCH (i:Incident) RETURN i.incident_id")],
)
ITEMS["Q-V3-085"] = (
    "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}) RETURN p.name",
    [("Return a single (main) suspect", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}) RETURN p.name ORDER BY p.name LIMIT 1"),
     ("Return all suspects", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}) RETURN p.name")],
)
ITEMS["Q-V3-086"] = (
    "MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name",
    [("Return the count of current associates", "MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN count(o) AS n"),
     ("Return the list of current associates", "MATCH (:Person {name:'Anton Maric'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name")],
)
ITEMS["Q-V3-087"] = (
    "MATCH (:Person {name:'James Whitfield'})-[:USES_PHONE {active:true}]->(:Phone)-[c:CALLED]->(b:Phone) RETURN b.phone_number",
    [("Return the called phone numbers only", "MATCH (:Person {name:'James Whitfield'})-[:USES_PHONE {active:true}]->(:Phone)-[c:CALLED]->(b:Phone) RETURN b.phone_number"),
     ("Return each call with its timestamp", "MATCH (:Person {name:'James Whitfield'})-[:USES_PHONE {active:true}]->(:Phone)-[c:CALLED]->(b:Phone) RETURN b.phone_number, c.timestamp")],
)
ITEMS["Q-V3-088"] = (
    "MATCH (:Person {name:'Ricky Santos'})-[:USES_PHONE {active:true}]->(ph:Phone)-[:CALLED]-(o:Phone)<-[:USES_PHONE {active:true}]-(op:Person) RETURN count(DISTINCT op) AS n",
    [("Count only outgoing calls", "MATCH (:Person {name:'Ricky Santos'})-[:USES_PHONE {active:true}]->(ph:Phone)-[:CALLED]->(o:Phone)<-[:USES_PHONE {active:true}]-(op:Person) RETURN count(DISTINCT op) AS n"),
     ("Count all calls, incoming and outgoing", "MATCH (:Person {name:'Ricky Santos'})-[:USES_PHONE {active:true}]->(ph:Phone)-[:CALLED]-(o:Phone)<-[:USES_PHONE {active:true}]-(op:Person) RETURN count(DISTINCT op) AS n")],
)
ITEMS["Q-V3-089"] = (
    "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}), (p)-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id",
    [("Return the count of vehicles", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}), (p)-[:OWNS {active:true}]->(v:Vehicle) RETURN count(v) AS n"),
     ("Return the list of vehicles", "MATCH (p:Person)-[:SUSPECTED_OF]->(:Incident {incident_id:'INC-V3-006'}), (p)-[:OWNS {active:true}]->(v:Vehicle) RETURN v.vehicle_id")],
)
ITEMS["Q-V3-090"] = (
    "MATCH (c:Case)-[:CONTAINS]->(i:Incident) WITH c, count(i) AS n RETURN c.case_name ORDER BY n DESC, c.case_name LIMIT 1",
    [("Return the single largest case", "MATCH (c:Case)-[:CONTAINS]->(i:Incident) WITH c, count(i) AS n RETURN c.case_name ORDER BY n DESC, c.case_name LIMIT 1"),
     ("Return all cases ranked by number of incidents", "MATCH (c:Case)-[:CONTAINS]->(i:Incident) WITH c, count(i) AS n RETURN c.case_name, n ORDER BY n DESC, c.case_name")],
)
ITEMS["Q-V3-091"] = (
    "MATCH (:Person {name:'Priya Sharma'})-[:INVESTIGATES]->(i:Incident) RETURN i.incident_id",
    [("Return just the number", "MATCH (:Person {name:'Priya Sharma'})-[:INVESTIGATES]->(i:Incident) RETURN count(i) AS n"),
     ("Return the list of incidents", "MATCH (:Person {name:'Priya Sharma'})-[:INVESTIGATES]->(i:Incident) RETURN i.incident_id")],
)
ITEMS["Q-V3-092"] = (
    "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id ORDER BY i.date DESC LIMIT 1",
    [("Only the most recent Northbridge incident", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id ORDER BY i.date DESC LIMIT 1"),
     ("All Northbridge incidents, newest first", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Northbridge'}) RETURN i.incident_id ORDER BY i.date DESC")],
)
ITEMS["Q-V3-093"] = (
    "MATCH (:Person {name:'Anton Maric'})-[:USES_PHONE {active:true}]->(:Phone)-[:CALLED]->(b:Phone) RETURN count(DISTINCT b) AS n",
    [("Return the count", "MATCH (:Person {name:'Anton Maric'})-[:USES_PHONE {active:true}]->(:Phone)-[:CALLED]->(b:Phone) RETURN count(DISTINCT b) AS n"),
     ("Return the list of contacts", "MATCH (:Person {name:'Anton Maric'})-[:USES_PHONE {active:true}]->(:Phone)-[:CALLED]->(b:Phone) RETURN DISTINCT b.phone_number")],
)
ITEMS["Q-V3-094"] = (
    "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Hay Street' RETURN p.name ORDER BY p.name LIMIT 1",
    [("Return a single (primary) officer", "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Hay Street' RETURN p.name ORDER BY p.name LIMIT 1"),
     ("Return all investigating officers", "MATCH (p:Person)-[:INVESTIGATES]->(i:Incident)-[:OCCURRED_AT]->(l:Location) WHERE l.address CONTAINS 'Hay Street' RETURN p.name")],
)
ITEMS["Q-V3-095"] = (
    "MATCH (p:Person)-[:WITNESSED]->(:Incident {incident_id:'INC-V3-006'}) RETURN p.name",
    [("Return the number of witnesses", "MATCH (p:Person)-[:WITNESSED]->(:Incident {incident_id:'INC-V3-006'}) RETURN count(p) AS n"),
     ("Return the witnesses' names", "MATCH (p:Person)-[:WITNESSED]->(:Incident {incident_id:'INC-V3-006'}) RETURN p.name")],
)
ITEMS["Q-V3-096"] = (
    "MATCH (:Case {case_id:'CASE-V3-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id",
    [("Return the count of incidents", "MATCH (:Case {case_id:'CASE-V3-001'})-[:CONTAINS]->(i:Incident) RETURN count(i) AS n"),
     ("Return the list of incident details", "MATCH (:Case {case_id:'CASE-V3-001'})-[:CONTAINS]->(i:Incident) RETURN i.incident_id, i.crime_type")],
)
ITEMS["Q-V3-097"] = (
    "MATCH (:Person {name:'Daniel Kim'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number",
    [("Return the phone number", "MATCH (:Person {name:'Daniel Kim'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number"),
     ("Return the full phone record (number and device id)", "MATCH (:Person {name:'Daniel Kim'})-[:USES_PHONE {active:true}]->(ph:Phone) RETURN ph.phone_number, ph.device_id")],
)
ITEMS["Q-V3-098"] = (
    "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id",
    [("Only incidents in the 'Perth' suburb (the CBD)", "MATCH (i:Incident)-[:OCCURRED_AT]->(:Location {suburb:'Perth'}) RETURN i.incident_id"),
     ("All incidents in the dataset", "MATCH (i:Incident) RETURN i.incident_id")],
)
ITEMS["Q-V3-099"] = (
    "MATCH (:Person {name:'Megan Tran'})-[:INVESTIGATES]->(i:Incident) RETURN count(i) AS n",
    [("Return the count of incidents she investigates", "MATCH (:Person {name:'Megan Tran'})-[:INVESTIGATES]->(i:Incident) RETURN count(i) AS n"),
     ("Return the list of those incidents", "MATCH (:Person {name:'Megan Tran'})-[:INVESTIGATES]->(i:Incident) RETURN i.incident_id")],
)
ITEMS["Q-V3-100"] = (
    "MATCH (:Phone)-[:CALLED]->(ph:Phone)<-[:USES_PHONE {active:true}]-(p:Person) WITH p, count(*) AS n RETURN p.name ORDER BY n DESC, p.name LIMIT 1",
    [("Return the single most-called person", "MATCH (:Phone)-[:CALLED]->(ph:Phone)<-[:USES_PHONE {active:true}]-(p:Person) WITH p, count(*) AS n RETURN p.name ORDER BY n DESC, p.name LIMIT 1"),
     ("Return people ranked by calls received", "MATCH (:Phone)-[:CALLED]->(ph:Phone)<-[:USES_PHONE {active:true}]-(p:Person) WITH p, count(*) AS n RETURN p.name, n ORDER BY n DESC, p.name")],
)

# ── Temporal ambiguity Q-V3-101 .. 120 ────────────────────────────────────────────
def lives(name):
    cur = f"MATCH (:Person {{name:'{name}'}})-[:LIVES_AT {{active:true}}]->(l:Location) RETURN l.address"
    allr = f"MATCH (:Person {{name:'{name}'}})-[:LIVES_AT]->(l:Location) RETURN l.address"
    return cur, [("Current address only", cur), ("Including historical addresses", allr)]


def owns(name):
    cur = f"MATCH (:Person {{name:'{name}'}})-[:OWNS {{active:true}}]->(v:Vehicle) RETURN v.vehicle_id"
    allr = f"MATCH (:Person {{name:'{name}'}})-[:OWNS]->(v:Vehicle) RETURN v.vehicle_id"
    return cur, [("Currently owned vehicles only", cur), ("Including vehicles previously owned", allr)]


def uses(name):
    cur = f"MATCH (:Person {{name:'{name}'}})-[:USES_PHONE {{active:true}}]->(ph:Phone) RETURN ph.phone_number"
    allr = f"MATCH (:Person {{name:'{name}'}})-[:USES_PHONE]->(ph:Phone) RETURN ph.phone_number"
    return cur, [("Current phone only", cur), ("Including previous phone", allr)]


def owner_of(make, model):
    cur = f"MATCH (p:Person)-[:OWNS {{active:true}}]->(:Vehicle {{make:'{make}', model:'{model}'}}) RETURN p.name"
    allr = f"MATCH (p:Person)-[:OWNS]->(:Vehicle {{make:'{make}', model:'{model}'}}) RETURN p.name"
    return cur, [("Current owner only", cur), ("Including the previous owner", allr)]


def user_of(number):
    cur = f"MATCH (p:Person)-[:USES_PHONE {{active:true}}]->(:Phone {{phone_number:'{number}'}}) RETURN p.name"
    allr = f"MATCH (p:Person)-[:USES_PHONE]->(:Phone {{phone_number:'{number}'}}) RETURN p.name"
    return cur, [("Current user only", cur), ("Including the previous user", allr)]


def assoc(name):
    cur = f"MATCH (:Person {{name:'{name}'}})-[:ASSOCIATED_WITH {{active:true}}]-(o:Person) RETURN o.name"
    allr = f"MATCH (:Person {{name:'{name}'}})-[:ASSOCIATED_WITH]-(o:Person) RETURN o.name"
    return cur, [("Current associates only", cur), ("Including former associates", allr)]


ITEMS["Q-V3-101"] = lives("James Whitfield")
ITEMS["Q-V3-102"] = lives("Lina Petrova")
ITEMS["Q-V3-103"] = owns("Ricky Santos")
ITEMS["Q-V3-104"] = owner_of("Holden", "Commodore")
ITEMS["Q-V3-105"] = owner_of("Ford", "Ranger")
ITEMS["Q-V3-106"] = uses("Lina Petrova")
ITEMS["Q-V3-107"] = user_of("0412 345 678")
ITEMS["Q-V3-108"] = user_of("0478 444 555")
ITEMS["Q-V3-109"] = assoc("Tyler Birch")
ITEMS["Q-V3-110"] = assoc("Amir Hassan")
ITEMS["Q-V3-111"] = (
    "MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address",
    [("His current address", "MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:true}]->(l:Location) RETURN l.address"),
     ("His previous address", "MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT {active:false}]->(l:Location) RETURN l.address"),
     ("All addresses on record", "MATCH (:Person {name:'Daniel Kim'})-[:LIVES_AT]->(l:Location) RETURN l.address")],
)
ITEMS["Q-V3-112"] = lives("Amir Hassan")
ITEMS["Q-V3-113"] = lives("Tyler Birch")
ITEMS["Q-V3-114"] = lives("Connor Doyle")
ITEMS["Q-V3-115"] = lives("Sarah Nguyen")
ITEMS["Q-V3-116"] = owns("Nina Orlov")
ITEMS["Q-V3-117"] = owner_of("Nissan", "Navara")
ITEMS["Q-V3-118"] = owner_of("BMW", "3 Series")
ITEMS["Q-V3-119"] = uses("Michael Nguyen")
ITEMS["Q-V3-120"] = (
    "MATCH (:Person {name:'Tyler Birch'})-[a:ASSOCIATED_WITH]-(o:Person) WHERE a.from_date <= date('2024-12-31') AND (a.to_date IS NULL OR a.to_date >= date('2024-01-01')) RETURN o.name",
    [("Associates whose edge was active during 2024", "MATCH (:Person {name:'Tyler Birch'})-[a:ASSOCIATED_WITH]-(o:Person) WHERE a.from_date <= date('2024-12-31') AND (a.to_date IS NULL OR a.to_date >= date('2024-01-01')) RETURN o.name"),
     ("His current associates only", "MATCH (:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH {active:true}]-(o:Person) RETURN o.name"),
     ("All associates ever recorded", "MATCH (:Person {name:'Tyler Birch'})-[:ASSOCIATED_WITH]-(o:Person) RETURN o.name")],
)


def main() -> None:
    skeleton = json.loads(SKELETON.read_text())
    out = []
    max_hop = 0
    rel_counter: Counter[str] = Counter()
    for entry in skeleton:
        qid = entry["question_id"]
        if qid not in ITEMS:
            raise SystemExit(f"missing cypher for {qid}")
        default, interps = ITEMS[qid]
        interp_objs = [{"interp": t, "cypher": c} for t, c in interps]
        nh = hops(default)
        max_hop = max(max_hop, nh)
        # coverage: count rel types across all gold cypher of this item
        for cy in [default] + [c for _, c in interps]:
            if hops(cy) > 3:
                raise SystemExit(f"{qid}: gold exceeds 3 hops: {cy}")
            for rt in V3_REL_TYPES:
                if f":{rt}]" in cy or f":{rt} " in cy or f":{rt}|" in cy or f"|{rt}]" in cy or f"|{rt}|" in cy:
                    rel_counter[rt] += 1
        item = {
            "question_id": qid,
            "question": entry["question"],
            "num_hops": nh,
            "is_ambiguous": entry["is_ambiguous"],
            "ambiguity_type": entry["ambiguity_type"],
            "default_interp": entry["default_interp"],
            "cypher_default": default,
            "interpretations": interp_objs,
        }
        # contract sanity: ambiguous -> >=1 interp; unambiguous -> 0
        if item["is_ambiguous"] and len(interp_objs) < 2:
            raise SystemExit(f"{qid}: ambiguous but <2 interpretations")
        if not item["is_ambiguous"] and interp_objs:
            raise SystemExit(f"{qid}: unambiguous but carries interpretations")
        out.append(item)

    OUT.write_text(json.dumps(out, indent=2))
    # ── offline diagnostics ──
    by_type = Counter(i["ambiguity_type"] for i in out)
    hop_dist = Counter(i["num_hops"] for i in out)
    print(f"wrote {len(out)} items -> {OUT}")
    print("by type:", dict(by_type))
    print("hop dist:", dict(sorted(hop_dist.items())))
    print("max hop:", max_hop)
    print("rel coverage (>=3 required):")
    for rt in V3_REL_TYPES:
        flag = "" if rel_counter[rt] >= 3 else "  <<< UNDER 3"
        print(f"  {rt:<16} {rel_counter[rt]}{flag}")
    qids = [i["question_id"] for i in out]
    qtexts = [i["question"] for i in out]
    assert len(set(qids)) == 120, "duplicate question_id"
    assert len(set(qtexts)) == 120, "duplicate question text"
    print("unique ids/text OK")


if __name__ == "__main__":
    main()
