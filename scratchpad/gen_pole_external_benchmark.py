"""One-off generation script for data/benchmark-pole-external.json (step 9.2).

Builds the 100-item canonical benchmark from the confirmed skeleton
(scratchpad/benchmark-pole-external-skeleton-draft.json) by authoring cypher_default +
per-interpretation Cypher against the real POLE-external schema. Not part of the pipeline —
a scratchpad generator, mirroring 7.1/7.2's own scratchpad/gen_benchmark.py convention.

Every item's gold Cypher is executed live during generation (non-empty check; ambiguous
items also get a pairwise-divergence check) so authoring failures surface immediately,
before the full experiments/validate_benchmark.py harness runs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import neo4j

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "benchmark-pole-external.json"

driver = neo4j.GraphDatabase.driver(
    "bolt://localhost:7687", auth=("neo4j", os.environ["NEO4J_PASSWORD"])
)


def run(cypher: str) -> list[dict]:
    with driver.session(database="neo4j") as s:
        return [r.data() for r in s.run(cypher)]


items: list[dict] = []


def add(question_id, question, num_hops, ambiguity_type, default_interp,
        cypher_default, interpretations=None):
    interpretations = interpretations or []
    is_ambiguous = ambiguity_type is not None
    item = {
        "question_id": question_id,
        "question": question,
        "num_hops": num_hops,
        "is_ambiguous": is_ambiguous,
        "ambiguity_type": ambiguity_type,
        "default_interp": default_interp,
        "cypher_default": cypher_default,
        "interpretations": interpretations,
    }
    items.append(item)


# ════════════════════════════════════════════════════════════════════════════════
# ENTITY (20) — duplicate Person names, no safe default; narrows by name(+nhs_no)
# ════════════════════════════════════════════════════════════════════════════════
add("Q-POLE-E01", "What is Andrea George's address?", 1, "entity",
    "No safe default — two distinct Persons share the identical full name",
    "MATCH (p:Person {name:'Andrea', surname:'George'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address",
    [
        {"interp": "nhs_no 800-46-2184", "cypher": "MATCH (p:Person {name:'Andrea', surname:'George', nhs_no:'800-46-2184'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"},
        {"interp": "nhs_no 391-46-9135", "cypher": "MATCH (p:Person {name:'Andrea', surname:'George', nhs_no:'391-46-9135'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"},
    ])

add("Q-POLE-E02", "What is Anne Rice's address?", 1, "entity",
    "No safe default — two distinct Persons share the identical full name",
    "MATCH (p:Person {name:'Anne', surname:'Rice'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address",
    [
        {"interp": "nhs_no 632-68-0917", "cypher": "MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'632-68-0917'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"},
        {"interp": "nhs_no 612-83-6356", "cypher": "MATCH (p:Person {name:'Anne', surname:'Rice', nhs_no:'612-83-6356'})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"},
    ])


def entity_surname_item(qid, question, surname, names):
    """names: ordered list of first names sharing `surname`, capped at 4 interpretations."""
    kept = names[:4]
    add(qid, question, 1, "entity",
        f"No safe default — {len(names)} distinct {surname} persons",
        f"MATCH (p:Person {{surname:'{surname}'}})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address",
        [{"interp": nm, "cypher": f"MATCH (p:Person {{surname:'{surname}', name:'{nm}'}})-[:CURRENT_ADDRESS]->(l:Location) RETURN l.address"}
         for nm in kept])


entity_surname_item("Q-POLE-E03", "What is the home address of a person named Ford?", "Ford",
                    ["Deborah", "Dennis", "Jimmy", "Philip"])
entity_surname_item("Q-POLE-E04", "Where does Fuller live?", "Fuller",
                    ["Carl", "Jeffrey", "Juan", "Nancy", "Rachel"])
entity_surname_item("Q-POLE-E05", "What address is registered for Murray?", "Murray",
                    ["Diana", "Jennifer", "Mary", "Phyllis", "William"])
entity_surname_item("Q-POLE-E06", "Find the address for Nguyen.", "Nguyen",
                    ["Anne", "Jeffrey", "Paul", "Wayne", "William"])
entity_surname_item("Q-POLE-E07", "What is Austin's current address?", "Austin",
                    ["Brian", "Dennis", "Heather", "Irene", "Scott"])
entity_surname_item("Q-POLE-E08", "Where is Bradley currently living?", "Bradley",
                    ["Adam", "Dennis", "Diane", "Rachel"])
entity_surname_item("Q-POLE-E09", "What address does Butler live at?", "Butler",
                    ["Denise", "Jennifer", "Maria", "Patricia"])
entity_surname_item("Q-POLE-E10", "What is the address of a person named Foster?", "Foster",
                    ["Andrew", "Cynthia", "Jessica", "Tammy"])
entity_surname_item("Q-POLE-E11", "Where does Hanson currently live?", "Hanson",
                    ["Andrea", "Irene", "Patricia", "Richard"])
entity_surname_item("Q-POLE-E12", "What address is on file for Hughes?", "Hughes",
                    ["Louis", "Maria", "Nancy", "Stephanie"])
entity_surname_item("Q-POLE-E13", "Find the home address of Jackson.", "Jackson",
                    ["Diana", "Mark", "Norma", "Steven"])
entity_surname_item("Q-POLE-E14", "What is Knight's registered address?", "Knight",
                    ["Christopher", "Cynthia", "James", "Peter"])
entity_surname_item("Q-POLE-E15", "Where can Martin be found living?", "Martin",
                    ["Brandon", "Cheryl", "Douglas", "Michael"])
entity_surname_item("Q-POLE-E16", "What address does Mason live at?", "Mason",
                    ["Michael", "Nicholas", "Philip", "Wayne"])
entity_surname_item("Q-POLE-E17", "Find Moreno's address.", "Moreno",
                    ["Andrea", "Barbara", "Daniel", "Julie"])
entity_surname_item("Q-POLE-E18", "What is Robertson's home address?", "Robertson",
                    ["Amanda", "Ashley", "Harold", "Kelly"])
entity_surname_item("Q-POLE-E19", "Where does Rogers currently reside?", "Rogers",
                    ["Donna", "Jennifer", "Joseph", "Kathleen"])
entity_surname_item("Q-POLE-E20", "What address is Williamson registered at?", "Williamson",
                    ["Emily", "Fred", "Phillip", "Raymond"])


# ════════════════════════════════════════════════════════════════════════════════
# SCHEMA (20) — KNOWS-family default-vs-narrow (S01-S10); PARTY_TO vs INVOLVED_IN (S11-S20)
# ════════════════════════════════════════════════════════════════════════════════
KNOWS_ALL = "KNOWS|KNOWS_SN|KNOWS_PHONE|KNOWS_LW|FAMILY_REL"


def any_conn(surname, name):
    return f"MATCH (p1:Person {{surname:'{surname}', name:'{name}'}})-[:{KNOWS_ALL}]-(p2:Person) RETURN DISTINCT p2.name, p2.surname"


def narrow_conn(surname, name, rel):
    return f"MATCH (p1:Person {{surname:'{surname}', name:'{name}'}})-[:{rel}]-(p2:Person) RETURN DISTINCT p2.name, p2.surname"


add("Q-POLE-S01", "Who is Benjamin Hamilton connected to?", 1, "schema",
    "Any KNOWS-family relationship type (10 people: Todd Hamilton, Frances Sullivan, + 8 KNOWS_SN contacts)",
    any_conn("Hamilton", "Benjamin"),
    [{"interp": "Only through his social network (KNOWS_SN)", "cypher": narrow_conn("Hamilton", "Benjamin", "KNOWS_SN")}])

add("Q-POLE-S02", "Who is Benjamin Hamilton related to by family?", 1, "schema",
    "Any KNOWS-family relationship type (10 people)",
    any_conn("Hamilton", "Benjamin"),
    [{"interp": "Only FAMILY_REL", "cypher": narrow_conn("Hamilton", "Benjamin", "FAMILY_REL")}])

add("Q-POLE-S03", "Who has Benjamin Hamilton had phone contact with?", 1, "schema",
    "Any KNOWS-family relationship type (10 people)",
    any_conn("Hamilton", "Benjamin"),
    [{"interp": "Only KNOWS_PHONE", "cypher": narrow_conn("Hamilton", "Benjamin", "KNOWS_PHONE")}])

add("Q-POLE-S04", "Who does Rachel Turner live with?", 1, "schema",
    "Any KNOWS-family relationship type (2 people: Todd Garcia, Eric Gutierrez)",
    any_conn("Turner", "Rachel"),
    [{"interp": "Only KNOWS_LW", "cypher": narrow_conn("Turner", "Rachel", "KNOWS_LW")}])

add("Q-POLE-S05", "Who has Rachel Turner been in phone contact with?", 1, "schema",
    "Any KNOWS-family relationship type (2 people)",
    any_conn("Turner", "Rachel"),
    [{"interp": "Only KNOWS_PHONE", "cypher": narrow_conn("Turner", "Rachel", "KNOWS_PHONE")}])

add("Q-POLE-S06", "Who does Mildred Kelly live with?", 1, "schema",
    "Any KNOWS-family relationship type (3 people: Stephen Perez, Jeffrey Campbell, Bruce Baker)",
    any_conn("Kelly", "Mildred"),
    [{"interp": "Only KNOWS_LW", "cypher": narrow_conn("Kelly", "Mildred", "KNOWS_LW")}])

add("Q-POLE-S07", "Who has Mildred Kelly had phone contact with?", 1, "schema",
    "Any KNOWS-family relationship type (3 people)",
    any_conn("Kelly", "Mildred"),
    [{"interp": "Only KNOWS_PHONE", "cypher": narrow_conn("Kelly", "Mildred", "KNOWS_PHONE")}])

add("Q-POLE-S08", "Who has Nancy Campbell been in phone contact with?", 1, "schema",
    "Any KNOWS-family relationship type (2 people: Carl Hayes, Angela Mccoy)",
    any_conn("Campbell", "Nancy"),
    [{"interp": "Only KNOWS_PHONE", "cypher": narrow_conn("Campbell", "Nancy", "KNOWS_PHONE")}])

add("Q-POLE-S09", "Who is Nancy Campbell connected to through her social network?", 1, "schema",
    "Any KNOWS-family relationship type (2 people)",
    any_conn("Campbell", "Nancy"),
    [{"interp": "Only KNOWS_SN", "cypher": narrow_conn("Campbell", "Nancy", "KNOWS_SN")}])

add("Q-POLE-S10", "Who does Todd Garcia live with?", 1, "schema",
    "Any KNOWS-family relationship type (3 people: Rachel Turner, Phillip Perry, Angela Mccoy)",
    any_conn("Garcia", "Todd"),
    [{"interp": "Only KNOWS_LW", "cypher": narrow_conn("Garcia", "Todd", "KNOWS_LW")}])


def crime_participant_item(qid, question, crime_id, kind="vehicle"):
    other_label, other_prop = ("Vehicle", "v.reg") if kind == "vehicle" else ("Object", "o.description")
    other_alias = "v" if kind == "vehicle" else "o"
    default_cy = (f"MATCH (a)-[:PARTY_TO|INVOLVED_IN]->(c:Crime {{id:'{crime_id}'}}) "
                  f"RETURN labels(a) AS labels, a")
    person_cy = f"MATCH (p:Person)-[:PARTY_TO]->(c:Crime {{id:'{crime_id}'}}) RETURN p.name, p.surname"
    other_cy = f"MATCH ({other_alias}:{other_label})-[:INVOLVED_IN]->(c:Crime {{id:'{crime_id}'}}) RETURN {other_prop}"
    add(qid, question, 1, "schema",
        "Any participant (person via PARTY_TO or " + ("vehicle" if kind == "vehicle" else "object") + " via INVOLVED_IN)",
        default_cy,
        [{"interp": "Only the person (PARTY_TO)", "cypher": person_cy},
         {"interp": f"Only the {'vehicle' if kind == 'vehicle' else 'object(s)'} (INVOLVED_IN)", "cypher": other_cy}])


crime_participant_item("Q-POLE-S11", "Who or what was involved in crime ab71bb05a5b0620dfec3779eead19d2c121cb73ee58e51cc7306d0dc5ff471c0?",
                       "ab71bb05a5b0620dfec3779eead19d2c121cb73ee58e51cc7306d0dc5ff471c0")
crime_participant_item("Q-POLE-S12", "What was connected to crime e35c34d58fa35f2110b059882a34703d132552a4ad408eac3f82f15aeb165f0f?",
                       "e35c34d58fa35f2110b059882a34703d132552a4ad408eac3f82f15aeb165f0f")
crime_participant_item("Q-POLE-S13", "Who/what does crime 576f4e50b1cbeb488c89bd28bd1697a1ad48fa0a5f4df857a844657e61f4487a involve?",
                       "576f4e50b1cbeb488c89bd28bd1697a1ad48fa0a5f4df857a844657e61f4487a")
crime_participant_item("Q-POLE-S14", "What's linked to incident 9cdadc1c345c17336210079096c372a7faaae0268e4725edbb031e4a19a4bc45?",
                       "9cdadc1c345c17336210079096c372a7faaae0268e4725edbb031e4a19a4bc45")
crime_participant_item("Q-POLE-S15", "Who or what was tied to crime 87b7f4fb4e9168b8c46dc5195ae75b68b2c2aeae6d7c36a6d2738280a2940f04?",
                       "87b7f4fb4e9168b8c46dc5195ae75b68b2c2aeae6d7c36a6d2738280a2940f04")
crime_participant_item("Q-POLE-S16", "Who/what is connected to crime cb58245b5903b1c02536c9f487c099015c1cc29405bce7107a6b99c1ccb81f0c?",
                       "cb58245b5903b1c02536c9f487c099015c1cc29405bce7107a6b99c1ccb81f0c")
crime_participant_item("Q-POLE-S17", "What was involved in crime 0e2192e79961a6572131429c9adbbae2a25b051a490e170913fb36bdb762f862?",
                       "0e2192e79961a6572131429c9adbbae2a25b051a490e170913fb36bdb762f862")
crime_participant_item("Q-POLE-S18", "Who or what featured in crime 70160845dc32f6cf61d614fa8a296d0e95a981d48325a57bcc73c9996bac7109?",
                       "70160845dc32f6cf61d614fa8a296d0e95a981d48325a57bcc73c9996bac7109")
crime_participant_item("Q-POLE-S19", "What's associated with crime 8aab5d71757708aeac451ffedfdecbcfffb8cdbdf5a07bdce397ed2ba7d6d8e3?",
                       "8aab5d71757708aeac451ffedfdecbcfffb8cdbdf5a07bdce397ed2ba7d6d8e3")
crime_participant_item("Q-POLE-S20", "Who or what was part of crime 2dec74f10fd12d8dcb28cb05ff058b4e4134ecb58d0e515c888f0611ca794339?",
                       "2dec74f10fd12d8dcb28cb05ff058b4e4134ecb58d0e515c888f0611ca794339", kind="object")


# ════════════════════════════════════════════════════════════════════════════════
# UNAMBIGUOUS CONTROL (20)
# ════════════════════════════════════════════════════════════════════════════════
def unambig(qid, question, num_hops, cy):
    add(qid, question, num_hops, None, "Direct/keyed property lookup", cy)


unambig("Q-POLE-U01", "What rank does the officer with badge number 80-1015383 hold?", 0,
        "MATCH (o:Officer {badge_no:'80-1015383'}) RETURN o.rank")
unambig("Q-POLE-U02", "What is the surname of the officer with badge number 70-0643982?", 0,
        "MATCH (o:Officer {badge_no:'70-0643982'}) RETURN o.surname")
unambig("Q-POLE-U03", "What rank is the officer with badge number 57-6110377?", 0,
        "MATCH (o:Officer {badge_no:'57-6110377'}) RETURN o.rank")
unambig("Q-POLE-U04", "What rank is the officer with badge number 18-0221971?", 0,
        "MATCH (o:Officer {badge_no:'18-0221971'}) RETURN o.rank")
unambig("Q-POLE-U05", "What rank is the officer with badge number 38-1719233?", 0,
        "MATCH (o:Officer {badge_no:'38-1719233'}) RETURN o.rank")
unambig("Q-POLE-U06", "What make is the vehicle with registration RY52 APF?", 0,
        "MATCH (v:Vehicle {reg:'RY52 APF'}) RETURN v.make")
unambig("Q-POLE-U07", "What model is the vehicle with registration RH42 TAB?", 0,
        "MATCH (v:Vehicle {reg:'RH42 TAB'}) RETURN v.model")
unambig("Q-POLE-U08", "What year was the vehicle with registration LW72 POF made?", 0,
        "MATCH (v:Vehicle {reg:'LW72 POF'}) RETURN v.year")
unambig("Q-POLE-U09", "What phone number is registered to the person with NHS number 991-70-5333?", 1,
        "MATCH (p:Person {nhs_no:'991-70-5333'})-[:HAS_PHONE]->(ph:Phone) RETURN ph.phoneNo")
unambig("Q-POLE-U10", "What email address is registered to the person with NHS number 556-65-1110?", 1,
        "MATCH (p:Person {nhs_no:'556-65-1110'})-[:HAS_EMAIL]->(e:Email) RETURN e.email_address")
unambig("Q-POLE-U11", "What postcode covers 178 Polding Street?", 1,
        "MATCH (l:Location {address:'178 Polding Street'})-[:HAS_POSTCODE]->(pc:PostCode) RETURN pc.code")
unambig("Q-POLE-U12", "What postcode covers 6 Gypsy Lane?", 1,
        "MATCH (l:Location {address:'6 Gypsy Lane'})-[:HAS_POSTCODE]->(pc:PostCode) RETURN pc.code")
unambig("Q-POLE-U13", "What postcode covers 116 Myrtle Street?", 1,
        "MATCH (l:Location {address:'116 Myrtle Street'})-[:HAS_POSTCODE]->(pc:PostCode) RETURN pc.code")
unambig("Q-POLE-U14", "What postcode covers 53 Birch Lane?", 1,
        "MATCH (l:Location {address:'53 Birch Lane'})-[:HAS_POSTCODE]->(pc:PostCode) RETURN pc.code")
unambig("Q-POLE-U15", "What area is postcode WN3 4NL in?", 1,
        "MATCH (pc:PostCode {code:'WN3 4NL'})-[:POSTCODE_IN_AREA]->(a:Area) RETURN a.areaCode")
unambig("Q-POLE-U16", "What type of crime was recorded under ID 10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31?", 0,
        "MATCH (c:Crime {id:'10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31'}) RETURN c.type")
unambig("Q-POLE-U17", "On what date did crime 8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4 occur?", 0,
        "MATCH (c:Crime {id:'8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4'}) RETURN c.date")
unambig("Q-POLE-U18", "What is the last recorded outcome for crime 9bc0db533b9248a8b3a7ac151f273fe01f25ad72b394dd5cc6ef9bd6558eb707?", 0,
        "MATCH (c:Crime {id:'9bc0db533b9248a8b3a7ac151f273fe01f25ad72b394dd5cc6ef9bd6558eb707'}) RETURN c.last_outcome")
unambig("Q-POLE-U19", "What is the surname of the person with NHS number 117-66-8129?", 0,
        "MATCH (p:Person {nhs_no:'117-66-8129'}) RETURN p.surname")
unambig("Q-POLE-U20", "What is the surname of the person with NHS number 620-83-1546?", 0,
        "MATCH (p:Person {nhs_no:'620-83-1546'}) RETURN p.surname")


# ════════════════════════════════════════════════════════════════════════════════
# INTENT (20)
# ════════════════════════════════════════════════════════════════════════════════
def rank_tie_item(qid, question, rank, exclude_names, tied):
    """exclude_names: [(surname,name),...] excluded by name. tied: [(surname,name,n),...]."""
    excl_clause = " AND ".join(f"NOT (o.surname='{sn}' AND o.name='{nm}')" for sn, nm in exclude_names)
    default_cy = (f"MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {{rank:'{rank}'}}) "
                  f"WHERE {excl_clause} WITH o, count(*) AS n RETURN o.surname, o.name, n ORDER BY n DESC LIMIT 1")
    interps = [{"interp": f"{nm} {sn} (n={n})",
               "cypher": f"MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {{surname:'{sn}', name:'{nm}'}}) RETURN o.surname, o.name, count(*) AS n"}
              for sn, nm, n in tied]
    add(qid, question, 1, "intent", "Single top of the remainder (arbitrary tiebreak)", default_cy, interps)


rank_tie_item("Q-POLE-I01", "Which Inspector has investigated the most crimes, aside from Nettles Worthy?",
              "Inspector", [("Nettles", "Worthy")],
              [("Skynner", "Winonah", 44), ("Miskimmon", "Ricca", 44)])
rank_tie_item("Q-POLE-I02", "Which Police Constable has investigated the most crimes, aside from Ings Cloe?",
              "Police Constable", [("Ings", "Cloe")],
              [("Vinson", "Hedy", 43), ("Greensall", "Simmonds", 43)])
rank_tie_item("Q-POLE-I10", "Which Chief Inspector has investigated the most crimes, aside from the top three (Monelli Kort, Stave Urban, Febry Roberto)?",
              "Chief Inspector", [("Monelli", "Kort"), ("Stave", "Urban"), ("Febry", "Roberto")],
              [("Jeandot", "Whitney", 37), ("Gorrie", "Esma", 37), ("Rahlof", "Evey", 37), ("Syddie", "Dottie", 37)])
rank_tie_item("Q-POLE-I11", "Which Sergeant has investigated the most crimes, aside from the top three (DeSousa Madelon, Notti Kania, Klehyn Olenolin)?",
              "Sergeant", [("DeSousa", "Madelon"), ("Notti", "Kania"), ("Klehyn", "Olenolin")],
              [("Macias", "Hernando", 42), ("Shurmore", "Rea", 42)])


def area_tie_item(qid, question, exclude_area, tied):
    default_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) "
                  f"WHERE a.areaCode <> '{exclude_area}' WITH a, count(*) AS n "
                  f"RETURN a.areaCode, n ORDER BY n DESC LIMIT 1")
    interps = [{"interp": f"{ac} (n={n})",
               "cypher": (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {{areaCode:'{ac}'}}) "
                          f"RETURN a.areaCode, count(*) AS n")}
              for ac, n in tied]
    add(qid, question, 2, "intent", "Single top of the remainder (arbitrary tiebreak)", default_cy, interps)


area_tie_item("Q-POLE-I03", "Which area recorded the most crime, after BL9?", "BL9",
              [("M14", 562), ("BL4", 562), ("BL2", 562)])


def area_compare_item(qid, question, area_a, area_b, total_a, total_b, violent_a, violent_b):
    total_winner, total_wn = (area_a, total_a) if total_a > total_b else (area_b, total_b)
    violent_winner, violent_wn = (area_a, violent_a) if violent_a > violent_b else (area_b, violent_b)
    total_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) "
               f"WHERE a.areaCode IN ['{area_a}','{area_b}'] "
               f"WITH a.areaCode AS area, count(*) AS n RETURN area, n ORDER BY n DESC LIMIT 1")
    violent_cy = (f"MATCH (c:Crime {{type:'Violence and sexual offences'}})-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) "
                 f"WHERE a.areaCode IN ['{area_a}','{area_b}'] "
                 f"WITH a.areaCode AS area, count(*) AS n RETURN area, n ORDER BY n DESC LIMIT 1")
    add(qid, question, 2, "intent", "Total crime count (broadest reading of 'dangerous')",
        total_cy,
        [{"interp": f"By total crime count: {total_winner} ({total_wn} > {total_a + total_b - total_wn})", "cypher": total_cy},
         {"interp": f"By violent/sexual-offence count specifically: {violent_winner} ({violent_wn} > {violent_a + violent_b - violent_wn})", "cypher": violent_cy}])


area_compare_item("Q-POLE-I04", "Which area is more dangerous, BL3 or M40?", "BL3", "M40", 814, 766, 223, 234)
area_compare_item("Q-POLE-I14", "Which area is more dangerous, M9 or BL9?", "M9", "BL9", 699, 623, 187, 204)
area_compare_item("Q-POLE-I15", "Which area is more dangerous, M14 or M6?", "M14", "M6", 562, 540, 144, 176)


def count_vs_list_item(qid, question, area, default_is_count, n, extra_filter=None, extra_label=""):
    where = f"a.areaCode='{area}'" + (f" AND {extra_filter}" if extra_filter else "")
    count_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) "
               f"WHERE {where} RETURN count(*) AS n")
    list_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) "
              f"WHERE {where} RETURN c.id, c.type, c.date")
    default_cy = count_cy if default_is_count else list_cy
    default_interp = "Return the count (single number)" if default_is_count else "List every individual crime"
    label = f" in area {area}{extra_label}"
    add(qid, question, 2, "intent", default_interp, default_cy,
        [{"interp": f"Count only ({n})", "cypher": count_cy},
         {"interp": f"List every individual crime{label}", "cypher": list_cy}])


count_vs_list_item("Q-POLE-I05", "How many crimes happened in area M1?", "M1", True, 975)
count_vs_list_item("Q-POLE-I06", "What crimes happened in area BL1?", "BL1", False, 860)
count_vs_list_item("Q-POLE-I07", "How many Violence and sexual offences crimes occurred in BL3?", "BL3", True, 223,
                   extra_filter="c.type='Violence and sexual offences'")
count_vs_list_item("Q-POLE-I12", "How many crimes happened in area BL9?", "BL9", True, 623)
count_vs_list_item("Q-POLE-I13", "How many crimes happened in area M14?", "M14", True, 562)

add("Q-POLE-I08", "List crimes of type Public order in area M9.", 2, "intent",
    "List every individual crime",
    "MATCH (c:Crime {type:'Public order'})-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M9'}) RETURN c.id, c.date",
    [{"interp": "List all matching crimes (174)", "cypher": "MATCH (c:Crime {type:'Public order'})-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M9'}) RETURN c.id, c.date"},
     {"interp": "Count only (174)", "cypher": "MATCH (c:Crime {type:'Public order'})-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M9'}) RETURN count(*) AS n"}])

add("Q-POLE-I09", "How many crimes has Sergeant DeSousa Madelon investigated?", 1, "intent",
    "Return the count (single number)",
    "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN count(*) AS n",
    [{"interp": "Count only (50)", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN count(*) AS n"},
     {"interp": "List every individual crime investigated", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'DeSousa', name:'Madelon'}) RETURN c.id, c.date"}])

add("Q-POLE-I16", "List all crimes investigated by Inspector Skynner Winonah.", 1, "intent",
    "List every individual crime",
    "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN c.id, c.date",
    [{"interp": "List all 44 crimes", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN c.id, c.date"},
     {"interp": "Count only (44)", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Skynner', name:'Winonah'}) RETURN count(*) AS n"}])

add("Q-POLE-I17", "How many crimes has Police Constable Vinson Hedy investigated?", 1, "intent",
    "Return the count (single number)",
    "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN count(*) AS n",
    [{"interp": "Count only (43)", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN count(*) AS n"},
     {"interp": "List every individual crime", "cypher": "MATCH (c:Crime)-[:INVESTIGATED_BY]->(o:Officer {surname:'Vinson', name:'Hedy'}) RETURN c.id, c.date"}])

add("Q-POLE-I18", "What crime types occurred in area BL4?", 2, "intent",
    "List distinct crime types",
    "MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL4'}) RETURN DISTINCT c.type",
    [{"interp": "List distinct crime types present", "cypher": "MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL4'}) RETURN DISTINCT c.type"},
     {"interp": "List every individual crime record", "cypher": "MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'BL4'}) RETURN c.id, c.type, c.date"}])

add("Q-POLE-I19", "Which is the most common crime type across all areas?", 0, "intent",
    "Single top type (Violence and sexual offences, n=8765)",
    "MATCH (c:Crime) WHERE c.type IS NOT NULL WITH c.type AS t, count(*) AS n RETURN t, n ORDER BY n DESC LIMIT 1",
    [{"interp": "Single top type only", "cypher": "MATCH (c:Crime) WHERE c.type IS NOT NULL WITH c.type AS t, count(*) AS n RETURN t, n ORDER BY n DESC LIMIT 1"},
     {"interp": "List all types above a threshold (>2000 occurrences)",
      "cypher": "MATCH (c:Crime) WHERE c.type IS NOT NULL WITH c.type AS t, count(*) AS n WHERE n > 2000 RETURN t, n ORDER BY n DESC"}])

add("Q-POLE-I20", "How many Vehicle crime incidents were recorded?", 0, "intent",
    "Return the count (single number)",
    "MATCH (c:Crime {type:'Vehicle crime'}) RETURN count(*) AS n",
    [{"interp": "Count only (2598)", "cypher": "MATCH (c:Crime {type:'Vehicle crime'}) RETURN count(*) AS n"},
     {"interp": "List every individual crime", "cypher": "MATCH (c:Crime {type:'Vehicle crime'}) RETURN c.id, c.date"}])


# ════════════════════════════════════════════════════════════════════════════════
# TEMPORAL (20) — same-day vs trailing-window date ambiguity
# ════════════════════════════════════════════════════════════════════════════════
def day_int_clause(day: int) -> str:
    return f"toInteger(split(c.date,'/')[0]) = {day}"


def window_clause(lo: int, hi: int) -> str:
    return f"toInteger(split(c.date,'/')[0]) >= {lo} AND toInteger(split(c.date,'/')[0]) <= {hi}"


def area_temporal_item(qid, question, area, day, window_lo, window_hi, same_n, window_n, window_label):
    same_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {{areaCode:'{area}'}}) "
              f"WHERE {day_int_clause(day)} RETURN count(*) AS n")
    window_cy = (f"MATCH (c:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area {{areaCode:'{area}'}}) "
                f"WHERE {window_clause(window_lo, window_hi)} RETURN count(*) AS n")
    add(qid, question, 2, "temporal", "Same calendar day", same_cy,
        [{"interp": f"Same day only ({same_n})", "cypher": same_cy},
         {"interp": f"Trailing {window_label} ({window_n})", "cypher": window_cy}])


area_temporal_item("Q-POLE-T01", "How many crimes happened in area M1 around 11 August 2017?", "M1", 11, 5, 11, 47, 217, "7-day window, 5-11 Aug")
area_temporal_item("Q-POLE-T02", "How many crimes happened in area M1 around 26 August 2017?", "M1", 26, 20, 26, 46, 247, "7-day window, 20-26 Aug")
area_temporal_item("Q-POLE-T03", "How many crimes happened in area M1 around 4 August 2017?", "M1", 4, 1, 4, 41, 132, "window, 1-4 Aug clipped at month start")
area_temporal_item("Q-POLE-T04", "How many crimes happened in area M1 around 31 August 2017?", "M1", 31, 25, 31, 42, 231, "7-day window, 25-31 Aug")
area_temporal_item("Q-POLE-T05", "How many crimes happened in area M1 around 18 August 2017?", "M1", 18, 12, 18, 36, 191, "7-day window, 12-18 Aug")
area_temporal_item("Q-POLE-T06", "How many crimes happened in area M1 around 24 August 2017?", "M1", 24, 18, 24, 37, 240, "7-day window, 18-24 Aug")
area_temporal_item("Q-POLE-T07", "How many crimes happened in area M1 around 20 August 2017?", "M1", 20, 14, 20, 39, 208, "7-day window, 14-20 Aug")
area_temporal_item("Q-POLE-T08", "How many crimes happened in area M1 around 9 August 2017?", "M1", 9, 3, 9, 26, 199, "7-day window, 3-9 Aug")
area_temporal_item("Q-POLE-T09", "How many crimes happened in area M1 around 2 August 2017?", "M1", 2, 1, 2, 28, 63, "window, 1-2 Aug clipped at month start")
area_temporal_item("Q-POLE-T10", "How many crimes happened in area M1 around 13 August 2017?", "M1", 13, 7, 13, 24, 209, "7-day window, 7-13 Aug")
area_temporal_item("Q-POLE-T11", "How many crimes happened in area M1 around 16 August 2017?", "M1", 16, 10, 16, 30, 221, "7-day window, 10-16 Aug")
area_temporal_item("Q-POLE-T12", "How many crimes happened in area M1 around 21 August 2017?", "M1", 21, 15, 21, 33, 217, "7-day window, 15-21 Aug")
area_temporal_item("Q-POLE-T13", "How many crimes happened in area M1 around 27 August 2017?", "M1", 27, 21, 27, 30, 238, "7-day window, 21-27 Aug")
area_temporal_item("Q-POLE-T14", "How many crimes happened in area M1 around 5 August 2017?", "M1", 5, 1, 5, 31, 163, "window, 1-5 Aug clipped at month start")
area_temporal_item("Q-POLE-T15", "How many crimes happened in area M1 around 29 August 2017?", "M1", 29, 23, 29, 20, 231, "7-day window, 23-29 Aug")
area_temporal_item("Q-POLE-T20", "How many crimes happened in area BL1 around 15 August 2017, same-day vs trailing-week?", "BL1", 15, 9, 15, 26, 182, "7-day window, 09-15 Aug")


def citywide_temporal_item(qid, question, day, window_lo, window_hi, same_n, window_n, window_label):
    same_cy = f"MATCH (c:Crime) WHERE {day_int_clause(day)} RETURN count(*) AS n"
    window_cy = f"MATCH (c:Crime) WHERE {window_clause(window_lo, window_hi)} RETURN count(*) AS n"
    add(qid, question, 0, "temporal", "Same calendar day", same_cy,
        [{"interp": f"Same day only ({same_n})", "cypher": same_cy},
         {"interp": f"Trailing {window_label} ({window_n})", "cypher": window_cy}])


citywide_temporal_item("Q-POLE-T16", "How many crimes were recorded (citywide) around 28 August 2017?", 28, 22, 28, 1014, 6556, "7-day window, 22-28 Aug")
citywide_temporal_item("Q-POLE-T17", "How many crimes were recorded (citywide) around 30 August 2017?", 30, 24, 30, 871, 6557, "7-day window, 24-30 Aug")
citywide_temporal_item("Q-POLE-T18", "How many crimes were recorded (citywide) around 11 August 2017?", 11, 5, 11, 930, 6423, "7-day window, 5-11 Aug")

add("Q-POLE-T19", "When did phone 0-(008)297-1581 last contact 9-(984)524-5395?", 2, "temporal",
    "Most recent single contact",
    "MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) "
    "RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1",
    [{"interp": "Most recent only: 20/08/2017 00:05",
      "cypher": "MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) "
                "RETURN pc.call_date, pc.call_time ORDER BY pc.call_date DESC, pc.call_time DESC LIMIT 1"},
     {"interp": "Full contact history: 04/08/2017 00:32 and 20/08/2017 00:05",
      "cypher": "MATCH (p1:Phone {phoneNo:'0-(008)297-1581'})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone {phoneNo:'9-(984)524-5395'}) "
                "RETURN pc.call_date, pc.call_time ORDER BY pc.call_date, pc.call_time"}])


# ════════════════════════════════════════════════════════════════════════════════
# sanity: 100 items, 20 per category
# ════════════════════════════════════════════════════════════════════════════════
assert len(items) == 100, f"expected 100 items, got {len(items)}"
from collections import Counter
dist = Counter(it["ambiguity_type"] for it in items)
print("distribution:", dict(dist))
assert dist == {None: 20, "schema": 20, "entity": 20, "intent": 20, "temporal": 20}, dist

# ════════════════════════════════════════════════════════════════════════════════
# live sanity pass: every gold cypher non-empty; ambiguous interps pairwise distinct
# ════════════════════════════════════════════════════════════════════════════════
def result_key(rows: list[dict]) -> frozenset:
    return frozenset(tuple(sorted(r.items(), key=lambda kv: kv[0])) for r in rows)


failures = []
for it in items:
    default_rows = run(it["cypher_default"])
    if not default_rows:
        failures.append((it["question_id"], "cypher_default empty"))
    interp_keys = []
    for interp in it["interpretations"]:
        rows = run(interp["cypher"])
        if not rows:
            failures.append((it["question_id"], f"interp empty: {interp['interp']}"))
        interp_keys.append(result_key(rows))
    if it["is_ambiguous"]:
        for a in range(len(interp_keys)):
            for b in range(a + 1, len(interp_keys)):
                if interp_keys[a] == interp_keys[b]:
                    failures.append((it["question_id"], f"interps not distinct: {a} vs {b}"))

if failures:
    for qid, msg in failures:
        print("FAIL", qid, msg)
    raise SystemExit(f"{len(failures)} live sanity failures — fix before writing output")

print(f"All {len(items)} items: gold cyphers non-empty, ambiguous interpretations pairwise distinct.")

OUT_PATH.write_text(json.dumps(items, indent=2) + "\n")
print(f"Wrote {OUT_PATH} ({len(items)} items)")

driver.close()
