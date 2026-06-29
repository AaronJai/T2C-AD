# tests/evaluation/test_semantic_evaluator.py
"""Contract tests for the Semantic Evaluator (step 4.1) — no live Neo4j required.

Ground-truth execution is monkeypatched (`_execute_ground_truth`) so the comparison and
failure-mode logic are exercised without a driver. Acceptance criteria 1–5; criterion 6
(end-to-end against the live POLE graph) is deferred to the Kaya run.
"""
from __future__ import annotations

import importlib

from pipeline.evaluation import semantic_evaluator
from pipeline.evaluation.semantic_evaluator import (
    _is_id_field,
    _result_sets_equal,
)
from pipeline.types import (
    BenchmarkItem,
    EvaluationResult,
    ExecutionResult,
    ValidationResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _benchmark_item(*, ambiguous: bool = False) -> BenchmarkItem:
    return BenchmarkItem(
        question_id="Q1",
        question="who is connected to incident 1?",
        num_hops=1,
        is_ambiguous=ambiguous,
        ambiguity_type="schema" if ambiguous else None,
        default_interp="default",
        cypher_default="MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name",
        interpretations=(
            [{"interp": "alt", "cypher": "MATCH (p:Person)-[:WITNESSED]->(i:Incident) RETURN p.name"}]
            if ambiguous else []
        ),
    )


def _accept() -> ValidationResult:
    return ValidationResult(
        syntax_valid=True, schema_score=1.0, properties_score=1.0,
        error_type=None, route_to="accept",
    )


class _FakeEmbeddingModel:
    """Returns a fixed cosine similarity for any pair (stands in for SentenceTransformer)."""

    def __init__(self, similarity: float) -> None:
        self._similarity = similarity

    def encode(self, texts, convert_to_tensor=True):
        import torch

        # Two unit vectors whose cosine similarity is exactly `self._similarity`.
        import math
        theta = math.acos(max(-1.0, min(1.0, self._similarity)))
        return torch.tensor([[1.0, 0.0], [math.cos(theta), math.sin(theta)]])


# ── Criterion 1: order-insensitive frozenset comparison ──────────────────────────
def test_order_insensitive_equal() -> None:
    assert _result_sets_equal([{"name": "A"}, {"name": "B"}],
                              [{"name": "B"}, {"name": "A"}]) is True


def test_both_empty_equal() -> None:
    assert _result_sets_equal([], []) is True


def test_one_empty_not_equal() -> None:
    assert _result_sets_equal([{"x": 1}], []) is False


def test_float_variance_absorbed() -> None:
    assert _result_sets_equal([{"x": 1.0000001}], [{"x": 1.0000002}]) is True


def test_node_dict_value_does_not_crash() -> None:
    """A generated query returning a whole node (RETURN p → dict value) must compare, not raise."""
    node = {"p": {"name": "A", "id": "PER-007"}}
    # Identical node dicts compare equal (order-insensitive within the dict)...
    assert _result_sets_equal([node], [{"p": {"id": "PER-007", "name": "A"}}]) is True
    # ...and a node-dict vs a scalar ground truth is simply unequal (a wrong_result, not a crash).
    assert _result_sets_equal([node], [{"p": "A"}]) is False


def test_list_value_does_not_crash() -> None:
    """A list-valued field (e.g. collect()) is hashable-normalised and compares order-sensitively."""
    assert _result_sets_equal([{"names": ["A", "B"]}], [{"names": ["A", "B"]}]) is True
    assert _result_sets_equal([{"names": ["A", "B"]}], [{"names": ["B", "A"]}]) is False


# ── Column-name insensitivity (decisions-log 2026-06-27): EX must not punish naming ──
def test_equal_despite_different_variable_name() -> None:
    """Gold `RETURN p.name` vs generated `RETURN x.name` — same value, different column key."""
    assert _result_sets_equal([{"p.name": "James Whitfield"}],
                              [{"x.name": "James Whitfield"}]) is True


def test_equal_despite_alias() -> None:
    """Gold `RETURN p.name` vs generated `RETURN p.name AS name`."""
    assert _result_sets_equal([{"p.name": "James"}], [{"name": "James"}]) is True


def test_equal_whole_node_different_variable() -> None:
    """Gold `RETURN v` vs generated `RETURN x` — same node dict under a different variable."""
    assert _result_sets_equal([{"v": {"rego": "1ABC", "make": "Toyota"}}],
                              [{"x": {"make": "Toyota", "rego": "1ABC"}}]) is True


def test_multi_column_name_insensitive_but_position_aligned() -> None:
    """Multi-column rows match by value in RETURN order, regardless of variable prefix."""
    gold = [{"l.address": "1 William St", "l.suburb": "Perth"}]
    gen = [{"x.address": "1 William St", "x.suburb": "Perth"}]
    assert _result_sets_equal(gold, gen) is True


def test_name_insensitivity_does_not_make_wrong_values_equal() -> None:
    """Different values are still unequal — name-insensitivity must not become value-blind."""
    assert _result_sets_equal([{"p.name": "James"}], [{"x.name": "Bob"}]) is False
    # differing column count is still unequal
    assert _result_sets_equal([{"a": 1}], [{"a": 1, "b": 2}]) is False


# ── Criterion 2: ID-field detection + ID fields never pass via fallback ───────────
def test_is_id_field() -> None:
    assert _is_id_field("PER-007") is True
    assert _is_id_field("INC-001") is True
    assert _is_id_field("VEH-012") is True
    assert _is_id_field("James") is False
    assert _is_id_field("Operation Ironside") is False


def test_id_fields_never_pass_via_fallback() -> None:
    """Differing IDs must NOT pass even with a high-similarity embedding model (same size)."""
    model = _FakeEmbeddingModel(similarity=1.0)
    assert _result_sets_equal([{"id": "PER-007"}], [{"id": "PER-013"}], embedding_model=model) is False


# ── Criterion 3: cosine fallback on free-text strings ────────────────────────────
def test_fallback_high_similarity_equal() -> None:
    model = _FakeEmbeddingModel(similarity=0.99)
    assert _result_sets_equal(
        [{"desc": "a stolen vehicle was recovered"}],
        [{"desc": "the recovered car had been stolen"}],
        embedding_model=model,
    ) is True


def test_fallback_low_similarity_not_equal() -> None:
    model = _FakeEmbeddingModel(similarity=0.10)
    assert _result_sets_equal(
        [{"desc": "a stolen vehicle was recovered"}],
        [{"desc": "the witness gave a statement"}],
        embedding_model=model,
    ) is False


def test_no_embedding_model_no_fallback() -> None:
    """Without an embedding model, mismatched free text returns False (exact only)."""
    assert _result_sets_equal([{"desc": "x"}], [{"desc": "y"}]) is False


# ── Criterion 4: invalid / unexecuted query ──────────────────────────────────────
def test_execution_failure_is_invalid_query() -> None:
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=False, result_set=[], error="boom",
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(),
        generated_cypher="MATCH ...",
        cyver_result=_accept(),
        condition="schema_grounded",
        retry_count=0,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
    )
    assert isinstance(result, EvaluationResult)
    assert result.failure_mode == "invalid_query"
    assert result.is_correct is False
    assert result.matches_any_interpretation is False


def test_cyver_not_accepted_is_invalid_query() -> None:
    rejected = ValidationResult(
        syntax_valid=False, schema_score=0.0, properties_score=None,
        error_type="syntax", route_to="query_generator",
    )
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=True, result_set=[{"name": "A"}], error=None,
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(),
        generated_cypher="MATCH ...",
        cyver_result=rejected,
        condition="schema_grounded",
        retry_count=0,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
    )
    assert result.failure_mode == "invalid_query"
    assert result.is_correct is False


# ── Criterion 5: stubbed ground truth → the three success/failure modes ───────────
def _patch_ground_truth(monkeypatch, default_result, interp_results) -> None:
    # The package __init__ re-exports the `semantic_evaluator` function, shadowing the
    # submodule of the same name — so patch the module object resolved via importlib.
    module = importlib.import_module("pipeline.evaluation.semantic_evaluator")
    monkeypatch.setattr(
        module, "_execute_ground_truth",
        lambda item, driver, database_name: (default_result, interp_results),
    )


def test_matches_default_is_correct(monkeypatch) -> None:
    _patch_ground_truth(monkeypatch, default_result=[{"name": "A"}], interp_results=[])
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=True, result_set=[{"name": "A"}], error=None,
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(),
        generated_cypher="MATCH ...",
        cyver_result=_accept(),
        condition="disambiguation_enhanced",
        retry_count=0,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
        is_first_attempt=True,
    )
    assert result.is_correct is True
    assert result.matches_any_interpretation is True
    assert result.failure_mode is None
    assert result.is_first_attempt is True


def test_matches_non_default_interpretation(monkeypatch) -> None:
    _patch_ground_truth(
        monkeypatch,
        default_result=[{"name": "A"}],
        interp_results=[[{"name": "B"}]],
    )
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=True, result_set=[{"name": "B"}], error=None,
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(ambiguous=True),
        generated_cypher="MATCH ...",
        cyver_result=_accept(),
        condition="disambiguation_enhanced",
        retry_count=1,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
    )
    assert result.is_correct is False
    assert result.matches_any_interpretation is True
    assert result.failure_mode == "valid_non_default"


def test_matches_neither_is_wrong_result(monkeypatch) -> None:
    _patch_ground_truth(
        monkeypatch,
        default_result=[{"name": "A"}],
        interp_results=[[{"name": "B"}]],
    )
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=True, result_set=[{"name": "Z"}], error=None,
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(ambiguous=True),
        generated_cypher="MATCH ...",
        cyver_result=_accept(),
        condition="disambiguation_enhanced",
        retry_count=0,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
    )
    assert result.is_correct is False
    assert result.matches_any_interpretation is False
    assert result.failure_mode == "wrong_result"


def test_unambiguous_valid_non_default_never_arises(monkeypatch) -> None:
    """Unambiguous item: interp_results empty → matches_any == is_correct (edge case)."""
    _patch_ground_truth(monkeypatch, default_result=[{"name": "A"}], interp_results=[])
    result = semantic_evaluator(
        execution_result=ExecutionResult(success=True, result_set=[{"name": "Z"}], error=None,
                                         execution_time_ms=1.0),
        benchmark_item=_benchmark_item(ambiguous=False),
        generated_cypher="MATCH ...",
        cyver_result=_accept(),
        condition="schema_grounded",
        retry_count=0,
        driver=None,  # type: ignore[arg-type]
        database_name="neo4j",
    )
    assert result.matches_any_interpretation is False
    assert result.failure_mode == "wrong_result"
