# experiments/run_evaluation.py
"""Run all three conditions over the benchmark; compute metrics; render Tables 1–3."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import yaml

from experiments.build_condition1 import build_condition1
from experiments.build_condition2 import build_condition2
from experiments.build_condition3 import build_condition3
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.evaluation.metrics import (MetricBundle, QuestionRecord, compute_metrics,
                                         format_metric_tables)
from pipeline.orchestrator import Orchestrator
from pipeline.schema import build_pole_schema_repr
from pipeline.types import BenchmarkItem, Condition, EvaluationResult


def run_condition(benchmark: list[BenchmarkItem], components, condition: Condition):
    """Orchestrate every item for one condition.
    Returns (records, ad_predictions) — one QuestionRecord per item (AMENDED 2026-06-10:
    per-attempt data for 4.2). is_failed / no-evaluation states map to a synthesized
    invalid_query final result so all 125 questions appear in records.
    """
    orch = Orchestrator()
    records: list[QuestionRecord] = []
    ad_predictions: list[tuple[str, bool]] = []
    for item in benchmark:
        state = orch.run(item.question, item, condition, components)
        ad_predictions.extend(state.ad_predictions)        # empty for C1/C2
        if state.evaluation_result is not None:
            final = state.evaluation_result
            history = state.evaluation_history             # final == history[-1]
        else:
            # never evaluated → history is empty by construction (5.2); synthesize the final
            final = EvaluationResult(
                question_id=item.question_id, condition=condition,
                is_correct=False, matches_any_interpretation=False,
                ambiguity_type=item.ambiguity_type, failure_mode="invalid_query",
                generated_cypher=state.generated_cypher or "",
                cyver_result=state.validation_result, retry_count=state.retry_count,
                is_first_attempt=False)                    # first attempt never executed
            history = [final]
        records.append(QuestionRecord(final=final, history=history,
                                      first_validation=state.first_validation_result))
    return records, ad_predictions


def _persist(results_dir: str, model_key: str, bundles: dict[Condition, MetricBundle],
             tables: str) -> None:
    """Write the rendered tables and the raw metric bundles to results_dir for the write-up.
    Filenames carry the model_key so a base-model comparison (one run per base) never overwrites.
    """
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"tables_{model_key}.md").write_text(tables)
    payload = {cond: asdict(bundle) for cond, bundle in bundles.items()}
    (out / f"metrics_{model_key}.json").write_text(json.dumps(payload, indent=2))


def main(config_path: str = "config/pipeline.yaml") -> None:
    cfg = yaml.safe_load(Path(config_path).read_text())
    neo4j_uri = cfg["neo4j"]["uri"]
    neo4j_auth = (cfg["neo4j"]["user"], os.environ["NEO4J_PASSWORD"])
    database = cfg["neo4j"].get("database")

    # Resolve the active base + adapter paths from the model registry (2.1)
    registry = yaml.safe_load(Path(cfg["models_registry"]).read_text())
    key = cfg["active_model"]
    if key not in registry:
        raise SystemExit(f"active_model '{key}' not in registry. Known: {list(registry)}")
    base = registry[key]["base"]
    sl_adapter = f"checkpoints/{key}/sl_adapter"
    qg_adapter = f"checkpoints/{key}/qg_adapter"
    ad_spec = cfg.get("ad") or {"backend": "huggingface", "model_name_or_path": base}
    dis_spec = cfg.get("dis")

    schema = build_pole_schema_repr()
    benchmark = load_benchmark(cfg["benchmark"])

    # locked diversity_penalty from 2.2 (fail loudly if missing — don't silently default)
    sli = yaml.safe_load(Path(cfg["schema_linker_inference"]).read_text())
    diversity_penalty = sli["diversity_penalty"]

    embedding_model = None
    if cfg.get("use_embedding_model"):
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    bundles: dict[Condition, MetricBundle] = {}

    with build_condition1(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          base_model_spec={"backend": "huggingface", "model_name_or_path": base},
                          schema=schema) as c1:
        c1.embedding_model = embedding_model
        results, _ = run_condition(benchmark, c1, "baseline")
        bundles["baseline"] = compute_metrics(results, ad_predictions=None)

    with build_condition2(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          base_model=base, sl_adapter=sl_adapter, qg_adapter=qg_adapter,
                          schema=schema) as c2:
        c2.embedding_model = embedding_model
        results, _ = run_condition(benchmark, c2, "schema_grounded")
        bundles["schema_grounded"] = compute_metrics(results, ad_predictions=None)

    with build_condition3(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          base_model=base, sl_adapter=sl_adapter, qg_adapter=qg_adapter,
                          schema=schema, diversity_penalty=diversity_penalty,
                          ad_spec=ad_spec, dis_spec=dis_spec,
                          embedding_model=embedding_model) as c3:
        results, ad_preds = run_condition(benchmark, c3, "disambiguation_enhanced")
        bundles["disambiguation_enhanced"] = compute_metrics(results, ad_predictions=ad_preds)

    tables = format_metric_tables(bundles)
    print(tables)
    _persist(cfg["results_dir"], key, bundles, tables)


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "config/pipeline.yaml")
