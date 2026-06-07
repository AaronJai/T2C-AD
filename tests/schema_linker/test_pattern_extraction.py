"""Contract tests for 1.1 schema pattern extraction (spec acceptance criteria)."""
from __future__ import annotations

from pipeline.schema_linker.pattern_extraction import (
    extract_schema_pattern,
    has_relationship_type,
)


# ── Acceptance 1: the two worked examples produce exactly the OUT strings ─────────
def test_worked_example_one():
    cypher = (
        "MATCH (p:Person {name:'James Whitfield'})-[:LIVES_AT {active:true}]->(l:Location)\n"
        "RETURN l.address, l.suburb"
    )
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:LIVES_AT {active:true}]->(l:Location)"
    )


def test_worked_example_two():
    cypher = (
        "MATCH (c:Case {case_id:'CASE-001'})-[:CONTAINS]->(i:Incident)"
        "<-[:SUSPECTED_OF]-(p:Person)\n"
        "RETURN p.name, i.crime_type"
    )
    assert extract_schema_pattern(cypher) == (
        "(c:Case)-[:CONTAINS]->(i:Incident)<-[:SUSPECTED_OF]-(p:Person)"
    )


# ── Acceptance 2: node-only query → no relationship → flagged for exclusion ───────
def test_node_only_extracts_label_and_is_flagged_for_exclusion():
    pattern = extract_schema_pattern("MATCH (p:Person {name:'X'}) RETURN p")
    assert pattern == "(p:Person)"
    # The relationship-type filter predicate excludes it (no rel type).
    assert has_relationship_type(pattern) is False


def test_filter_predicate_accepts_a_typed_relationship():
    pattern = "(p:Person)-[:LIVES_AT {active:true}]->(l:Location)"
    assert has_relationship_type(pattern) is True


# ── Acceptance 3: malformed input returns None (never raises) ────────────────────
def test_unbalanced_brackets_returns_none():
    assert extract_schema_pattern("MATCH (p:Person]->(l:Location RETURN p") is None
    assert extract_schema_pattern("MATCH (p:Person") is None


def test_empty_or_no_match_returns_none():
    assert extract_schema_pattern("") is None
    assert extract_schema_pattern("   ") is None
    assert extract_schema_pattern("RETURN 1") is None


# ── Acceptance 4: per-value property treatment ───────────────────────────────────
def test_boolean_value_retained_on_relationship():
    cypher = "MATCH (p:Person)-[:LIVES_AT {active:true}]->(l:Location) RETURN l"
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:LIVES_AT {active:true}]->(l:Location)"
    )


def test_string_value_on_relationship_reduced_to_name():
    cypher = "MATCH (p:Person)-[:LIVES_AT {from_date:'2020-01-01'}]->(l:Location) RETURN l"
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:LIVES_AT {from_date}]->(l:Location)"
    )


def test_string_valued_node_map_dropped_leaving_label():
    cypher = "MATCH (i:Incident {incident_id:'INC-001'})-[:CONTAINS]-(c:Case) RETURN i"
    assert extract_schema_pattern(cypher) == "(i:Incident)-[:CONTAINS]-(c:Case)"


# ── Edge cases from the spec ─────────────────────────────────────────────────────
def test_undirected_edge_keeps_undirected_form():
    cypher = "MATCH (a:Person)-[:KNOWS]-(b:Person) RETURN a"
    assert extract_schema_pattern(cypher) == "(a:Person)-[:KNOWS]-(b:Person)"


def test_relationship_keeps_boolean_and_strips_other_values_together():
    cypher = (
        "MATCH (p:Person)-[:WORKS_FOR {active:true, from_date:'2019-05-01'}]->(o:Organisation)"
        " RETURN o"
    )
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:WORKS_FOR {active:true, from_date}]->(o:Organisation)"
    )


def test_multiple_match_clauses_are_newline_joined():
    cypher = (
        "MATCH (p:Person {name:'X'})-[:SUSPECTED_OF]->(i:Incident)\n"
        "MATCH (i)-[:OCCURRED_AT]->(l:Location)\n"
        "RETURN l"
    )
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:SUSPECTED_OF]->(i:Incident)\n"
        "(i)-[:OCCURRED_AT]->(l:Location)"
    )


def test_comma_separated_paths_in_one_clause_are_comma_joined():
    cypher = "MATCH (p:Person {name:'X'})-[:OWNS]->(v:Vehicle), (p)-[:USES_PHONE]->(ph:Phone) RETURN v"
    assert extract_schema_pattern(cypher) == (
        "(p:Person)-[:OWNS]->(v:Vehicle), (p)-[:USES_PHONE]->(ph:Phone)"
    )


def test_boolean_value_retained_on_node():
    cypher = "MATCH (p:Person {active:true})-[:SUSPECTED_OF]->(i:Incident) RETURN p"
    assert extract_schema_pattern(cypher) == (
        "(p:Person {active:true})-[:SUSPECTED_OF]->(i:Incident)"
    )
