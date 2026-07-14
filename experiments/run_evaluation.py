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
from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT, AD_SYSTEM_PROMPT_V3
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT, DIS_SYSTEM_PROMPT_V3
from pipeline.entity_lookup.registry import registry_for_version
from pipeline.evaluation.metrics import (MetricBundle, QuestionRecord, compute_metrics,
                                         format_metric_tables)
from pipeline.orchestrator import Orchestrator
from pipeline.schema import adapter_suffix_for_version, build_pole_schema_repr, build_pole_v3_schema_repr
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
             tables: str, results_tag: str = "") -> None:
    """Write the rendered tables and the raw metric bundles to results_dir for the write-up.
    Filenames carry the model_key so a base-model comparison (one run per base) never overwrites,
    plus the dataset `results_tag` (7.3) so v2/v3 artefacts never collide. An empty tag reproduces
    today's names (`tables_{model_key}.md`), so v2 artefacts are byte-identical.
    """
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    suffix = f"_{results_tag}" if results_tag else ""
    (out / f"tables_{model_key}{suffix}.md").write_text(tables)
    payload = {cond: asdict(bundle) for cond, bundle in bundles.items()}
    (out / f"metrics_{model_key}{suffix}.json").write_text(json.dumps(payload, indent=2))


def resolve_dataset(cfg: dict) -> dict:
    """Resolve the version-specific run objects from config, without loading any model (7.3).

    Returns the schema repr, entity registry, AD/Dis system prompts, results_tag and benchmark
    path for `dataset_version` (default 'v2' when the key is absent → the frozen baseline). v2 is
    byte-identical to pre-7.3 behaviour; 'v3' selects the concise schema/registry/prompts.
    """
    version = cfg.get("dataset_version", "v2")
    if version == "v3":
        return {
            "dataset_version": "v3",
            "schema": build_pole_v3_schema_repr(),
            "entity_registry": registry_for_version("v3"),
            "ad_system_prompt": AD_SYSTEM_PROMPT_V3,
            "dis_system_prompt": DIS_SYSTEM_PROMPT_V3,
            "adapter_suffix": adapter_suffix_for_version("v3"),
            "results_tag": cfg.get("results_tag", ""),
            "benchmark": cfg["benchmark"],
        }
    if version == "v2":
        return {
            "dataset_version": "v2",
            "schema": build_pole_schema_repr(),
            "entity_registry": registry_for_version("v2"),
            "ad_system_prompt": AD_SYSTEM_PROMPT,
            "dis_system_prompt": DIS_SYSTEM_PROMPT,
            "adapter_suffix": adapter_suffix_for_version("v2"),
            "results_tag": cfg.get("results_tag", ""),
            "benchmark": cfg["benchmark"],
        }
    raise SystemExit(f"Unknown dataset_version '{version}' in config. Known: 'v2', 'v3'.")


def _resolve_sl_decoding(sli: dict, key: str, kind: str) -> dict:
    """The SL decoding block for the active model, locked by the 2.2 sweep.

    Prefers `decoding[<model_key>]` (the generalized, per-model block). For a local model a
    legacy flat `diversity_penalty` (the original 2.2 output) is still honoured as a beam
    block. Fails loudly otherwise — never picks a default.
    """
    decoding_map = (sli or {}).get("decoding")
    if isinstance(decoding_map, dict) and key in decoding_map:
        return dict(decoding_map[key])
    if kind == "local" and "diversity_penalty" in (sli or {}):
        return {"strategy": "beam", "diversity_penalty": sli["diversity_penalty"], "k": 5}
    raise KeyError(
        f"No SL decoding for model '{key}' in schema_linker_inference. Run the 2.2 sweep to "
        f"lock it (beam diversity_penalty for a local model, sampling temperature for API)."
    )


def _resolve_prompt_style(kind: str) -> str:
    """The SL prompt style for the active backend (8.1/8.2). An `kind: api` model uses the
    additive instruct prompt (explicit output contract + few-shots); a local fine-tuned model
    uses the shared train/inference completion prompt (byte-identical to the pre-8.1 path)."""
    return "instruct" if kind == "api" else "completion"


def _resolve_model_specs(entry: dict, key: str, adapter_suffix: str = "") -> tuple[dict, dict, dict, str]:
    """Build (base_spec, sl_spec, qg_spec, kind) from a registry entry.

    local → HuggingFace base + the namespaced SL/QG adapters, carrying the registry's
    4-bit/dtype so inference loads the base the way training did (QLoRA 4-bit + fp16 on V100;
    full precision OOMs a 32 GB 2×16 GB V100 node — decisions-log 2026-06-23). `adapter_suffix`
    (from the dataset version — '' for v2, '_v3' for v3) selects the substrate-matched adapters
    so a v3 run loads `{sl,qg}_adapter_v3`, not the frozen v2 pair (7.5 G4).
    api   → the same API spec for all three (no adapters, no fine-tuning).
    """
    kind = entry.get("kind", "local")
    if kind == "api":
        api_spec = {"backend": entry["backend"], "model": entry["model"]}
        return dict(api_spec), dict(api_spec), dict(api_spec), kind
    quant = {"load_in_4bit": entry.get("load_in_4bit", False),
             "torch_dtype": entry.get("dtype", "bfloat16")}
    base_spec = {"backend": "huggingface", "model_name_or_path": entry["base"], **quant}
    sl_spec = {**base_spec, "peft_adapter_path": f"checkpoints/{key}/sl_adapter{adapter_suffix}"}
    qg_spec = {**base_spec, "peft_adapter_path": f"checkpoints/{key}/qg_adapter{adapter_suffix}"}
    return base_spec, sl_spec, qg_spec, kind


def main(config_path: str = "config/pipeline.yaml") -> None:
    cfg = yaml.safe_load(Path(config_path).read_text())
    neo4j_uri = cfg["neo4j"]["uri"]
    neo4j_auth = (cfg["neo4j"]["user"], os.environ["NEO4J_PASSWORD"])
    database = cfg["neo4j"].get("database")

    # Version-specific objects (schema repr, entity registry, AD/Dis prompts, adapter suffix,
    # results_tag) — 7.3/7.5. Resolved first so the adapter suffix reaches the model specs below.
    ds = resolve_dataset(cfg)

    # Resolve the active model from the registry (2.1; local base+adapter, or an `kind: api` entry).
    # A local model loads the substrate-matched adapters (v3 → `{sl,qg}_adapter_v3`) via ds["adapter_suffix"].
    registry = yaml.safe_load(Path(cfg["models_registry"]).read_text())
    key = cfg["active_model"]
    if key not in registry:
        raise SystemExit(f"active_model '{key}' not in registry. Known: {list(registry)}")
    base_spec, sl_spec, qg_spec, kind = _resolve_model_specs(registry[key], key, ds["adapter_suffix"])

    # AD/Dis swap points (config). ad null → the active model (one model the whole way through);
    # dis null → share the AD backend. A given spec is passed through verbatim.
    ad_spec = cfg.get("ad") or dict(base_spec)
    dis_spec = cfg.get("dis")

    # Locked SL decoding from 2.2 (fail loudly if missing — don't silently default)
    sli = yaml.safe_load(Path(cfg["schema_linker_inference"]).read_text())
    sl_decoding = _resolve_sl_decoding(sli, key, kind)

    # SL prompt style, derived from the same registry `kind` (8.1/8.2): instruct for an API
    # model, completion for the local fine-tuned model. C1 has no Schema Linker.
    prompt_style = _resolve_prompt_style(kind)

    # `ds` (schema repr, entity registry, AD/Dis prompts, adapter suffix, results_tag) resolved above.
    schema = ds["schema"]
    benchmark = load_benchmark(ds["benchmark"])

    embedding_model = None
    if cfg.get("use_embedding_model"):
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    bundles: dict[Condition, MetricBundle] = {}

    with build_condition1(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          base_model_spec=dict(base_spec),
                          schema=schema) as c1:
        c1.embedding_model = embedding_model
        results, _ = run_condition(benchmark, c1, "baseline")
        bundles["baseline"] = compute_metrics(results, ad_predictions=None)

    with build_condition2(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          sl_spec=dict(sl_spec), qg_spec=dict(qg_spec), schema=schema,
                          prompt_style=prompt_style) as c2:
        c2.embedding_model = embedding_model
        results, _ = run_condition(benchmark, c2, "schema_grounded")
        bundles["schema_grounded"] = compute_metrics(results, ad_predictions=None)

    with build_condition3(neo4j_uri=neo4j_uri, neo4j_auth=neo4j_auth, database_name=database,
                          base_spec=dict(base_spec), sl_spec=dict(sl_spec), qg_spec=dict(qg_spec),
                          schema=schema, sl_decoding=sl_decoding,
                          ad_spec=ad_spec, dis_spec=dis_spec,
                          embedding_model=embedding_model,
                          entity_registry=ds["entity_registry"],
                          ad_system_prompt=ds["ad_system_prompt"],
                          dis_system_prompt=ds["dis_system_prompt"],
                          prompt_style=prompt_style) as c3:
        results, ad_preds = run_condition(benchmark, c3, "disambiguation_enhanced")
        bundles["disambiguation_enhanced"] = compute_metrics(results, ad_predictions=ad_preds)

    tables = format_metric_tables(bundles)
    print(tables)
    _persist(cfg["results_dir"], key, bundles, tables, ds["results_tag"])


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "config/pipeline.yaml")
