"""8.3 follow-up ablation (decisions-log 2026-07-16) — full 120-item C3-ONLY run, swapping SL and
QG TOGETHER to the same training tier, to test "detected AND resolved" (DSR, ambiguous EA), not
just binary detection.

NOT a pipeline module: a Kaya verification harness, mirroring experiments/run_evaluation.py's v3
path but restricted to Condition 3 (disambiguation_enhanced) only — C1/C2 don't exercise the
Disambiguator and would just reproduce the already-recorded v3-mistral numbers. SL and QG are
swapped together (both generic-Ozsoy-only, or both no-adapter), matching the claude-sonnet run's
design of one uniform capability level across every stage (no mixed tiers). AD/Dis stay at the
default base model throughout (same as the recorded v3-mistral G4 run). This tests what the
ad-probe ablation (10-item, detection-only) couldn't speak to: whether the Disambiguator + QG +
CyVer + execution chain still resolves ambiguous questions correctly at a weaker training tier, not
just whether the AD's binary classification holds up.

Run inside a GPU job that also has the v3 Neo4j up on bolt://localhost:7687 (kaya/91-style runner).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from experiments.build_condition3 import build_condition3
from experiments.run_evaluation import run_condition
from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT_V3
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT_V3
from pipeline.entity_lookup.registry import registry_for_version
from pipeline.evaluation.metrics import compute_metrics
from pipeline.schema import build_pole_v3_schema_repr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    ap.add_argument("--adapter_suffix", default="_v3",
                    help="SL *and* QG adapter suffix (swapped together): default '_v3' (7.4 "
                         "in-domain SFT, the recorded run). Pass '' for generic-Ozsoy-only on "
                         "both. No effect if --no_adapters is set.")
    ap.add_argument("--no_adapters", action="store_true",
                    help="Load the raw base model for BOTH SL and QG, no PEFT adapter at all.")
    ap.add_argument("--qg_include_properties", action="store_true",
                    help="Show the QG the schema's property list (decisions-log 2026-07-17). "
                         "The local QG is the ONLY stage never shown it, and 14/24 v3 properties "
                         "appear zero times in its SFT completions, so it cannot name them at "
                         "all. Appends '_qgprops' to the results tag.")
    ap.add_argument("--results", default=None,
                    help="default results/c3_only_{model_key}_v3_{tag}.json")
    ap.add_argument("--neo4j_uri", default="bolt://localhost:7687")
    args = ap.parse_args()

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        sli = yaml.safe_load(fh)

    quant = {"load_in_4bit": registry.get("load_in_4bit", True),
             "torch_dtype": registry.get("dtype", "float16")}
    base_spec = {"backend": "huggingface", "model_name_or_path": registry["base"], **quant}
    # SL and QG are swapped TOGETHER, matched to the same training tier — mirroring the
    # claude-sonnet run, which uses one model uniformly across every stage (no mixed capability
    # tiers). Holding QG at qg_adapter_v3 while only degrading SL (an earlier version of this
    # script) would test a narrower, different question (SL's marginal contribution in isolation);
    # this version recreates "what the whole pipeline looks like at each training tier," directly
    # comparable in spirit to the API run's single-capability-level design.
    sl_adapter = None if args.no_adapters else f"checkpoints/{args.model_key}/sl_adapter{args.adapter_suffix}"
    qg_adapter = None if args.no_adapters else f"checkpoints/{args.model_key}/qg_adapter{args.adapter_suffix}"
    sl_spec = {**base_spec, "peft_adapter_path": sl_adapter}
    qg_spec = {**base_spec, "peft_adapter_path": qg_adapter}

    sl_decoding_cfg = sli.get("decoding", {}).get(
        args.model_key, {"strategy": "beam", "diversity_penalty": sli["diversity_penalty"], "k": 5})

    schema = build_pole_v3_schema_repr()
    benchmark = load_benchmark(args.benchmark)
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")

    tag = "noadapter" if args.no_adapters else ("genericonly" if args.adapter_suffix == "" else "full7p4")
    if args.qg_include_properties:
        tag += "_qgprops"
    sl_adapter_desc = "none" if args.no_adapters else f"sl_adapter{args.adapter_suffix}"
    qg_adapter_desc = "none" if args.no_adapters else f"qg_adapter{args.adapter_suffix}"
    print(f"C3-only ablation: model_key={args.model_key} sl_adapter={sl_adapter_desc} "
          f"qg_adapter={qg_adapter_desc} qg_include_properties={args.qg_include_properties} "
          f"ad=base (fixed, never fine-tuned) tag={tag}")

    with build_condition3(
        neo4j_uri=args.neo4j_uri, neo4j_auth=("neo4j", neo4j_password), database_name="neo4j",
        base_spec=dict(base_spec), sl_spec=dict(sl_spec), qg_spec=dict(qg_spec),
        schema=schema, sl_decoding=sl_decoding_cfg,
        ad_spec=None, dis_spec=None,          # both default to base_spec (the recorded run's setup)
        entity_registry=registry_for_version("v3"),
        ad_system_prompt=AD_SYSTEM_PROMPT_V3, dis_system_prompt=DIS_SYSTEM_PROMPT_V3,
        prompt_style="completion",            # local fine-tuned path throughout
        qg_include_properties=True if args.qg_include_properties else None,
    ) as c3:
        results, ad_preds = run_condition(benchmark, c3, "disambiguation_enhanced")
        bundle = compute_metrics(results, ad_predictions=ad_preds)

    payload = {
        "model_key": args.model_key, "sl_adapter": sl_adapter_desc, "qg_adapter": qg_adapter_desc,
        "ad_backend": "base", "qg_include_properties": bool(args.qg_include_properties),
        "tag": tag, "metrics": {
            k: (None if isinstance(v, float) and v != v else v)   # NaN -> null for valid JSON
            for k, v in vars(bundle).items()
        },
    }
    results_path = Path(args.results or f"results/c3_only_{args.model_key}_v3_{tag}.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n==================== C3-ONLY ABLATION ({tag}) ====================")
    print(f"  EX={bundle.ex:.3f} EA={bundle.ea:.3f} ambiguous_EA={bundle.ambiguous_ea:.3f}")
    print(f"  DSR={bundle.dsr} Detection F1={bundle.detection_f1} "
          f"Prec={bundle.detection_prec} Rec={bundle.detection_rec}")
    print(f"  Wrote -> {results_path}")


if __name__ == "__main__":
    main()
