"""Contract tests for the evaluation harness (step 5.4).

No GPU/Neo4j: the condition builders yield fake context-managed components, Orchestrator.run
returns canned PipelineStates, and compute_metrics/format_metric_tables are stubbed. The tests
assert run_condition's record assembly (criterion 1), main's config resolution + builder wiring
(criterion 2), and the fail-loud edge cases (criterion 3). The full live run is deferred.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

import experiments.run_evaluation as rev
from pipeline.evaluation.metrics import QuestionRecord
from pipeline.types import BenchmarkItem, EvaluationResult, PipelineState, ValidationResult


# ── Builders / fixtures ────────────────────────────────────────────────────────────
def _item(qid: str, atype=None) -> BenchmarkItem:
    return BenchmarkItem(
        question_id=qid, question=f"q-{qid}", num_hops=1,
        is_ambiguous=atype is not None, ambiguity_type=atype,
        default_interp="d", cypher_default="MATCH (n) RETURN n", interpretations=[],
    )


def _vr(route="accept") -> ValidationResult:
    return ValidationResult(syntax_valid=True, schema_score=1.0, properties_score=1.0,
                            error_type=None, route_to=route)


def _ev(qid, *, is_first=False, correct=True) -> EvaluationResult:
    return EvaluationResult(
        question_id=qid, condition="disambiguation_enhanced", is_correct=correct,
        matches_any_interpretation=correct, ambiguity_type=None, failure_mode=None,
        generated_cypher="MATCH (n) RETURN n", cyver_result=_vr(), retry_count=0,
        is_first_attempt=is_first)


def _patch_orch(monkeypatch, states: list[PipelineState]) -> None:
    """Patch Orchestrator so its single instance returns the canned states in order."""
    it = iter(states)

    class _FakeOrch:
        def run(self, question, item, condition, components):  # noqa: D401 - test stub
            return next(it)

    monkeypatch.setattr(rev, "Orchestrator", _FakeOrch)


# ── Criterion 1: run_condition record assembly ─────────────────────────────────────
def test_run_condition_synthesizes_invalid_query_for_unevaluated(monkeypatch):
    item = _item("Q-001", atype="schema")
    state = PipelineState(question=item.question, benchmark_item=item, condition="baseline")
    state.evaluation_result = None
    state.generated_cypher = "BROKEN"
    state.validation_result = _vr(route="query_generator")
    state.first_validation_result = state.validation_result
    state.retry_count = 2
    _patch_orch(monkeypatch, [state])

    records, ad_preds = rev.run_condition([item], object(), "baseline")

    assert len(records) == 1
    rec = records[0]
    assert isinstance(rec, QuestionRecord)
    final = rec.final
    assert final.failure_mode == "invalid_query"
    assert final.is_correct is False and final.matches_any_interpretation is False
    assert final.question_id == "Q-001" and final.condition == "baseline"
    assert final.ambiguity_type == "schema"            # carried from the item
    assert final.generated_cypher == "BROKEN"
    assert final.cyver_result is state.validation_result
    assert final.retry_count == 2
    assert final.is_first_attempt is False
    assert rec.history == [final]                       # length 1, the synthesized final
    assert rec.first_validation is state.first_validation_result
    assert ad_preds == []                               # no AD predictions for baseline


def test_run_condition_uses_history_when_evaluated(monkeypatch):
    item = _item("Q-002", atype="entity")
    ev1 = _ev("Q-002", is_first=True, correct=False)
    ev2 = _ev("Q-002", is_first=False, correct=True)
    state = PipelineState(question=item.question, benchmark_item=item,
                          condition="disambiguation_enhanced")
    state.evaluation_result = ev2
    state.evaluation_history = [ev1, ev2]
    state.first_validation_result = _vr()
    state.ad_predictions = [("Q-002", True)]
    _patch_orch(monkeypatch, [state])

    records, ad_preds = rev.run_condition([item], object(), "disambiguation_enhanced")

    rec = records[0]
    assert len(rec.history) == 2
    assert rec.final is ev2 and rec.history[-1] is ev2
    assert rec.first_validation is state.first_validation_result
    assert ad_preds == [("Q-002", True)]


def test_run_condition_concatenates_ad_predictions(monkeypatch):
    items = [_item("Q-1", "schema"), _item("Q-2", "entity")]
    s1 = PipelineState(question="a", benchmark_item=items[0], condition="disambiguation_enhanced")
    s1.evaluation_result = _ev("Q-1"); s1.evaluation_history = [s1.evaluation_result]
    s1.ad_predictions = [("Q-1", True), ("Q-1", False)]      # outer retry → duplicate qid
    s2 = PipelineState(question="b", benchmark_item=items[1], condition="disambiguation_enhanced")
    s2.evaluation_result = _ev("Q-2"); s2.evaluation_history = [s2.evaluation_result]
    s2.ad_predictions = [("Q-2", True)]
    _patch_orch(monkeypatch, [s1, s2])

    records, ad_preds = rev.run_condition(items, object(), "disambiguation_enhanced")

    assert len(records) == 2
    assert ad_preds == [("Q-1", True), ("Q-1", False), ("Q-2", True)]


# ── main: config + wiring fixture ──────────────────────────────────────────────────
def _write_configs(tmp_path, *, active="mistral7b", dp: object = 0.2, registry_ok=True):
    reg = "" if not registry_ok else (
        "mistral7b:\n  base: \"org/Base-7B\"\n  target_modules: [\"q_proj\"]\n"
        "  dtype: \"float16\"\n  load_in_4bit: true\n")
    (tmp_path / "models.yaml").write_text(reg or "othermodel:\n  base: \"x\"\n")
    sli = "diversity_penalty: 0.2\n" if dp is not None else "other: 1\n"
    (tmp_path / "sli.yaml").write_text(sli)
    cfg = (
        "neo4j:\n  uri: \"bolt://x\"\n  user: \"neo4j\"\n  database: \"neo4j\"\n"
        f"models_registry: \"{tmp_path/'models.yaml'}\"\n"
        f"active_model: \"{active}\"\n"
        "ad: null\ndis: null\n"
        "benchmark: \"ignored.json\"\n"
        f"schema_linker_inference: \"{tmp_path/'sli.yaml'}\"\n"
        "use_embedding_model: false\n"
        f"results_dir: \"{tmp_path/'results'}\"\n"
    )
    path = tmp_path / "pipeline.yaml"
    path.write_text(cfg)
    return str(path)


@pytest.fixture
def wired(monkeypatch):
    """Patch builders, run_condition, metrics, benchmark + schema; capture all calls."""
    calls = {"builders": {}, "compute": []}

    def _builder(name):
        @contextmanager
        def _cm(**kwargs):
            calls["builders"][name] = kwargs

            class _C:  # settable embedding_model attr
                embedding_model = None
            yield _C()
        return _cm

    monkeypatch.setattr(rev, "build_condition1", _builder("c1"))
    monkeypatch.setattr(rev, "build_condition2", _builder("c2"))
    monkeypatch.setattr(rev, "build_condition3", _builder("c3"))
    monkeypatch.setattr(rev, "load_benchmark", lambda p: [_item("Q-1")])
    monkeypatch.setattr(rev, "build_pole_schema_repr", lambda: "SCHEMA")
    monkeypatch.setattr(rev, "run_condition",
                        lambda bench, comp, cond: ([], [("Q-1", True)] if cond ==
                                                   "disambiguation_enhanced" else []))

    def _compute(records, ad_predictions=None):
        calls["compute"].append(ad_predictions)
        return f"bundle-{len(calls['compute'])}"

    monkeypatch.setattr(rev, "compute_metrics", _compute)
    monkeypatch.setattr(rev, "format_metric_tables", lambda bundles: "TABLES")
    monkeypatch.setattr(rev, "_persist", lambda *a, **k: None)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    return calls


# ── Criterion 2: main resolves config + wires builders ─────────────────────────────
def test_main_resolves_and_wires(monkeypatch, tmp_path, wired):
    cfg_path = _write_configs(tmp_path)
    rev.main(cfg_path)

    b = wired["builders"]
    # C1 gets the base via a build_llm spec carrying the registry quant/dtype (5.4 OOM fix).
    assert b["c1"]["base_model_spec"] == {"backend": "huggingface",
                                          "model_name_or_path": "org/Base-7B",
                                          "load_in_4bit": True, "torch_dtype": "float16"}
    assert b["c1"]["neo4j_auth"] == ("neo4j", "secret")
    # C2/C3 get base + the namespaced adapter paths derived from active_model, plus quant/dtype.
    for cond in ("c2", "c3"):
        assert b[cond]["base_model"] == "org/Base-7B"
        assert b[cond]["sl_adapter"] == "checkpoints/mistral7b/sl_adapter"
        assert b[cond]["qg_adapter"] == "checkpoints/mistral7b/qg_adapter"
        assert b[cond]["load_in_4bit"] is True
        assert b[cond]["torch_dtype"] == "float16"
    # Locked diversity_penalty flows to C3 only.
    assert b["c3"]["diversity_penalty"] == 0.2
    # ad null → defaults to active base (with quant/dtype); dis null → None (share AD).
    assert b["c3"]["ad_spec"] == {"backend": "huggingface", "model_name_or_path": "org/Base-7B",
                                  "load_in_4bit": True, "torch_dtype": "float16"}
    assert b["c3"]["dis_spec"] is None
    # ad_predictions: None for C1/C2, the real list for C3.
    assert wired["compute"] == [None, None, [("Q-1", True)]]


# ── Criterion 3: fail-loud edge cases ──────────────────────────────────────────────
def test_unknown_active_model_raises(monkeypatch, tmp_path, wired):
    cfg_path = _write_configs(tmp_path, active="nope")
    with pytest.raises(SystemExit):
        rev.main(cfg_path)


def test_missing_password_raises(monkeypatch, tmp_path, wired):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    cfg_path = _write_configs(tmp_path)
    with pytest.raises(KeyError):
        rev.main(cfg_path)


def test_missing_diversity_penalty_raises(monkeypatch, tmp_path, wired):
    cfg_path = _write_configs(tmp_path, dp=None)
    with pytest.raises(KeyError):
        rev.main(cfg_path)
