"""8.3 follow-up ablation (decisions-log 2026-07-16) — full 120-item C2-ONLY run, swapping SL and
QG TOGETHER to the same training tier, mirroring `kaya/c3_only_ablation_v3.py`.

NOT a pipeline module: a Kaya verification harness, mirroring experiments/run_evaluation.py's v3
path but restricted to Condition 2 (schema_grounded) only — C1 uses no adapter at all (see
build_condition1.py: `QueryGenerator(base)`, no Schema Linker), so it is structurally invariant to
this ablation and is skipped on those grounds, not as a judgment call. C2 shares the exact SL+QG
stage that the C3-only ablation varies, so it answers the open question that ablation left: does
the C3-over-C2 gap (success criterion #1) survive at a weaker SL/QG training tier, or does C2
degrade in step with C3 (leaving the gap, and DSR's collapse, essentially unexplained by C2 alone)?

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

from experiments.build_condition2 import build_condition2
from experiments.run_evaluation import run_condition
from pipeline.data.benchmark_loader import load_benchmark
from pipeline.evaluation.metrics import compute_metrics
from pipeline.schema import build_pole_v3_schema_repr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--adapter_suffix", default="_v3",
                    help="SL *and* QG adapter suffix (swapped together): default '_v3' (7.4 "
                         "in-domain SFT, the recorded run). Pass '' for generic-Ozsoy-only on "
                         "both. No effect if --no_adapters is set.")
    ap.add_argument("--no_adapters", action="store_true",
                    help="Load the raw base model for BOTH SL and QG, no PEFT adapter at all.")
    ap.add_argument("--results", default=None,
                    help="default results/c2_only_{model_key}_v3_{tag}.json")
    ap.add_argument("--neo4j_uri", default="bolt://localhost:7687")
    args = ap.parse_args()

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]

    quant = {"load_in_4bit": registry.get("load_in_4bit", True),
             "torch_dtype": registry.get("dtype", "float16")}
    base_spec = {"backend": "huggingface", "model_name_or_path": registry["base"], **quant}
    sl_adapter = None if args.no_adapters else f"checkpoints/{args.model_key}/sl_adapter{args.adapter_suffix}"
    qg_adapter = None if args.no_adapters else f"checkpoints/{args.model_key}/qg_adapter{args.adapter_suffix}"
    sl_spec = {**base_spec, "peft_adapter_path": sl_adapter}
    qg_spec = {**base_spec, "peft_adapter_path": qg_adapter}

    schema = build_pole_v3_schema_repr()
    benchmark = load_benchmark(args.benchmark)
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")

    tag = "noadapter" if args.no_adapters else ("genericonly" if args.adapter_suffix == "" else "full7p4")
    sl_adapter_desc = "none" if args.no_adapters else f"sl_adapter{args.adapter_suffix}"
    qg_adapter_desc = "none" if args.no_adapters else f"qg_adapter{args.adapter_suffix}"
    print(f"C2-only ablation: model_key={args.model_key} sl_adapter={sl_adapter_desc} "
          f"qg_adapter={qg_adapter_desc} tag={tag}")

    with build_condition2(
        neo4j_uri=args.neo4j_uri, neo4j_auth=("neo4j", neo4j_password), database_name="neo4j",
        sl_spec=dict(sl_spec), qg_spec=dict(qg_spec), schema=schema,
        prompt_style="completion",            # local fine-tuned path throughout
    ) as c2:
        results, _ = run_condition(benchmark, c2, "schema_grounded")
        bundle = compute_metrics(results, ad_predictions=None)

    payload = {
        "model_key": args.model_key, "sl_adapter": sl_adapter_desc, "qg_adapter": qg_adapter_desc,
        "tag": tag, "metrics": {
            k: (None if isinstance(v, float) and v != v else v)   # NaN -> null for valid JSON
            for k, v in vars(bundle).items()
        },
    }
    results_path = Path(args.results or f"results/c2_only_{args.model_key}_v3_{tag}.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n==================== C2-ONLY ABLATION ({tag}) ====================")
    print(f"  EX={bundle.ex:.3f} EA={bundle.ea:.3f} ambiguous_EA={bundle.ambiguous_ea:.3f}")
    print(f"  Wrote -> {results_path}")


if __name__ == "__main__":
    main()
