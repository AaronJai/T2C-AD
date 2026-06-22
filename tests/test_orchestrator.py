# tests/test_orchestrator.py
"""Contract tests for the Orchestrator (5.2): the 8 no-GPU/no-DB acceptance criteria.

Stage stages are stubbed by monkeypatching the module-level names the orchestrator imports,
plus a SimpleNamespace standing in for PipelineComponents (only attribute access is used).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import pipeline.orchestrator as orch
from pipeline.orchestrator import Orchestrator
from pipeline.types import (AmbiguityResult, BenchmarkItem, CandidateMapping,
                            EntityLookupResult, EvaluationResult, ExecutionResult,
                            SchemaCandidate, SchemaElement, SchemaMapping, ValidationResult)


# ── builders ────────────────────────────────────────────────────────────────
def vr_accept() -> ValidationResult:
    return ValidationResult(syntax_valid=True, schema_score=1.0, properties_score=1.0,
                            error_type=None, route_to="accept")


def vr_syntax() -> ValidationResult:
    return ValidationResult(syntax_valid=False, schema_score=0.0, properties_score=None,
                            error_type="syntax", route_to="query_generator",
                            metadata=[{"msg": "syntax bad"}])


def vr_schema() -> ValidationResult:
    return ValidationResult(syntax_valid=True, schema_score=0.5, properties_score=None,
                            error_type="schema", route_to="schema_linker",
                            metadata=[{"msg": "unknown label"}])


def make_cm() -> CandidateMapping:
    el = SchemaElement(element_type="relationship_type", name="SUSPECTED_OF",
                       source_label="Person", target_label="Incident")
    return CandidateMapping(question="q",
                            mentions={"connected to": [SchemaCandidate(el, 1.0, 1)]})


TOP1_CYPHER = make_cm().top1_mapping().cypher_syntax   # the persisted-mapping fingerprint


def make_mapping(cy: str) -> SchemaMapping:
    return SchemaMapping(question="q", committed={}, cypher_syntax=cy, resolution_mode="automated")


def make_item(qid: str = "Q-001") -> BenchmarkItem:
    return BenchmarkItem(question_id=qid, question="q", num_hops=1, is_ambiguous=False,
                         ambiguity_type=None, default_interp="d",
                         cypher_default="MATCH (n) RETURN n", interpretations=[])


def make_ar(is_amb: bool) -> AmbiguityResult:
    return AmbiguityResult(is_ambiguous=is_amb, detected_types=[], schema_entropy=0.0,
                           entity_entropy=0.0, llm_rationale="")


# ── stubs ───────────────────────────────────────────────────────────────────
class Seq:
    """Pop sequentially; repeat the last item once exhausted. Counts calls."""

    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def __call__(self, cypher, components):
        self.calls += 1
        return self.items.pop(0) if len(self.items) > 1 else self.items[0]


class QGStub:
    def __init__(self, query: str = "MATCH (n) RETURN n"):
        self.query = query
        self.calls: list = []          # error_feedback seen per call

    def generate(self, question, schema_mapping, schema, error_feedback=None):
        self.calls.append(error_feedback)
        return self.query


class LinkerStub:
    def __init__(self, cm):
        self.cm = cm
        self.n = 0

    def link(self, question, schema):
        self.n += 1
        return self.cm


class DisStub:
    def __init__(self, returns):
        self.returns = list(returns)
        self.tried_lens: list = []     # len(previously_tried) seen per call

    def __call__(self, question, ar, cm, el, dis_llm, previously_tried):
        self.tried_lens.append(len(previously_tried))
        return self.returns.pop(0) if len(self.returns) > 1 else self.returns[0]


class EvalStub:
    def __init__(self, outcomes):
        # outcomes: list of (is_correct, matches_any, failure_mode)
        self.outcomes = list(outcomes)
        self.first_flags: list = []

    def __call__(self, execution_result, benchmark_item, generated_cypher, cyver_result,
                 condition, retry_count, driver, database_name, embedding_model=None,
                 is_first_attempt=False):
        o = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        self.first_flags.append(is_first_attempt)
        qid = benchmark_item.question_id if benchmark_item else "Q"
        return EvaluationResult(question_id=qid, condition=condition, is_correct=o[0],
                                matches_any_interpretation=o[1], ambiguity_type=None,
                                failure_mode=o[2], generated_cypher=generated_cypher,
                                cyver_result=cyver_result, retry_count=retry_count,
                                is_first_attempt=is_first_attempt)


def make_components(**over):
    base = dict(query_generator=QGStub(), schema_linker=LinkerStub(make_cm()),
                ad_llm=object(), dis_llm=object(), entity_cache=object(),
                neo4j_driver=object(), database_name=None, schema=None,
                embedding_model=None, use_prefilter=False)
    base.update(over)
    return SimpleNamespace(**base)


def patch_stages(monkeypatch, *, cyver, eval_stub, dis=None, ad_amb=False):
    monkeypatch.setattr(orch, "cyver_validator", cyver)
    monkeypatch.setattr(orch, "db_executor",
                        lambda c, d, db: ExecutionResult(True, [{"n": 1}], None, 1.0))
    monkeypatch.setattr(orch, "semantic_evaluator", eval_stub)
    monkeypatch.setattr(orch, "ambiguity_detector", lambda q, cm, el, llm: make_ar(ad_amb))
    monkeypatch.setattr(orch, "entity_lookup", lambda q, cm, cache: EntityLookupResult(q, {}))
    if dis is not None:
        monkeypatch.setattr(orch, "disambiguator", dis)


# ── criterion 1: baseline path ────────────────────────────────────────────────
def test_baseline_single_pass(monkeypatch):
    comps = make_components()
    patch_stages(monkeypatch, cyver=Seq([vr_accept()]),
                 eval_stub=EvalStub([(True, True, None)]))

    state = Orchestrator().run("q", make_item(), "baseline", comps)

    assert state.evaluation_result is not None and state.evaluation_result.is_correct is True
    assert state.retry_count == 0
    assert state.evaluation_result.is_first_attempt is True
    assert comps.schema_linker.n == 0                # no SL/AD/Dis touched
    assert state.candidate_mapping is None and state.ambiguity_result is None
    assert len(comps.query_generator.calls) == 1


# ── criterion 2: syntax retry recovers ────────────────────────────────────────
def test_syntax_retry_recovers(monkeypatch):
    comps = make_components()
    patch_stages(monkeypatch, cyver=Seq([vr_syntax(), vr_syntax(), vr_accept()]),
                 eval_stub=EvalStub([(True, True, None)]))

    state = Orchestrator().run("q", make_item(), "baseline", comps)

    assert len(comps.query_generator.calls) == 3        # QG called 3×
    assert state.retry_count == 0                        # syntax retries don't cost budget
    assert state.validation_result.route_to == "accept"
    assert comps.query_generator.calls[0] is None        # first attempt: no feedback
    assert comps.query_generator.calls[1] is not None and "MATCH" in comps.query_generator.calls[1]
    assert comps.query_generator.calls[2] is not None
    assert state.evaluation_result.is_correct is True


# ── criterion 3: syntax retries exhausted ─────────────────────────────────────
def test_syntax_exhausted(monkeypatch):
    comps = make_components()
    first_vr = vr_syntax()
    patch_stages(monkeypatch, cyver=Seq([first_vr]),
                 eval_stub=EvalStub([(True, True, None)]))

    state = Orchestrator().run("q", make_item(), "baseline", comps)

    assert state.is_failed is True
    assert state.failure_reason == "max_syntax_retries_exhausted"
    assert state.evaluation_result is None
    assert state.first_validation_result is first_vr     # set once, the first stub result
    assert len(comps.query_generator.calls) == 3         # MAX_SYNTAX_RETRIES + 1


# ── criterion 4: schema retry persists previously_tried + re-invokes Disambiguator ─
def test_schema_retry(monkeypatch):
    comps = make_components()
    dis = DisStub([make_mapping("DISAMB")])
    patch_stages(monkeypatch, cyver=Seq([vr_schema(), vr_accept()]),
                 eval_stub=EvalStub([(True, True, None)]), dis=dis, ad_amb=False)

    state = Orchestrator().run("q", make_item(), "disambiguation_enhanced", comps)

    assert comps.schema_linker.n == 2                    # SL.link called twice
    assert state.retry_count == 1
    # previously_tried PERSISTS: the schema-failed top1 mapping is still listed
    assert len(state.previously_tried_mappings) == 2
    assert state.previously_tried_mappings[0].cypher_syntax == TOP1_CYPHER
    # Disambiguator invoked on the retry despite AD saying unambiguous
    assert len(dis.tried_lens) == 1
    # first QG call of the retry carries the schema-failure feedback
    assert comps.query_generator.calls[0] is None
    assert comps.query_generator.calls[1] is not None and "MATCH" in comps.query_generator.calls[1]
    assert state.evaluation_result.is_correct is True


# ── criterion 5: schema retries exhausted ─────────────────────────────────────
def test_schema_exhausted(monkeypatch):
    comps = make_components()
    dis = DisStub([make_mapping("A"), make_mapping("B"), make_mapping("C"), make_mapping("D")])
    patch_stages(monkeypatch, cyver=Seq([vr_schema()]),
                 eval_stub=EvalStub([(True, True, None)]), dis=dis, ad_amb=True)

    state = Orchestrator().run("q", make_item(), "disambiguation_enhanced", comps)

    assert state.is_failed is True
    assert state.failure_reason == "max_schema_retries_exhausted"
    assert comps.schema_linker.n == 4                    # MAX_SCHEMA_RETRIES + 1 outer iters
    assert state.retry_count == 3
    assert state.evaluation_result is None


# ── criterion 6: C3 semantic-mismatch retry ───────────────────────────────────
def test_c3_semantic_retry(monkeypatch):
    comps = make_components()
    dis = DisStub([make_mapping("A"), make_mapping("B")])
    eval_stub = EvalStub([(False, False, "wrong_result"), (True, True, None)])
    patch_stages(monkeypatch, cyver=Seq([vr_accept()]), eval_stub=eval_stub, dis=dis, ad_amb=True)

    state = Orchestrator().run("q", make_item(), "disambiguation_enhanced", comps)

    assert len(dis.tried_lens) == 2                      # disambiguator called twice
    assert dis.tried_lens[0] < dis.tried_lens[1]         # with growing previously_tried
    assert eval_stub.first_flags == [True, False]        # is_first only on the first eval
    assert len(state.evaluation_history) == 2
    assert state.evaluation_history[0].is_correct is False
    assert state.evaluation_history[1].is_correct is True
    assert state.evaluation_result is state.evaluation_history[-1]
    assert state.retry_count == 0                         # dis retry doesn't cost schema budget


# ── criterion 7: C3 candidates exhausted (disambiguator → None) ────────────────
def test_c3_exhausted_candidates(monkeypatch):
    comps = make_components()
    dis = DisStub([None])
    patch_stages(monkeypatch, cyver=Seq([vr_accept()]),
                 eval_stub=EvalStub([(True, True, None)]), dis=dis, ad_amb=True)

    state = Orchestrator().run("q", make_item(), "disambiguation_enhanced", comps)

    assert state.evaluation_result is None               # broke pre-execution
    assert state.is_failed is False
    assert len(comps.query_generator.calls) == 0         # never reached the QG


# ── criterion 8: ad_predictions populated once per C3 outer iteration ──────────
def test_ad_predictions(monkeypatch):
    comps = make_components()
    dis = DisStub([make_mapping("A")])
    patch_stages(monkeypatch, cyver=Seq([vr_accept()]),
                 eval_stub=EvalStub([(True, True, None)]), dis=dis, ad_amb=True)

    state = Orchestrator().run("q", make_item("Q-042"), "disambiguation_enhanced", comps)

    assert state.ad_predictions == [("Q-042", True)]
