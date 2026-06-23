"""Step 5.3 acceptance criterion 5 — build each condition for real and confirm it returns
a working PipelineComponents.

NOT a pipeline module: a Kaya verification harness. Calls the three condition builders
(experiments/build_condition{1,2,3}.py) with real config — base model + adapters from
config/models.yaml + checkpoints/{model_key}/, the locked diversity_penalty from
config/schema_linker_inference.yaml, and the live Neo4j on bolt://localhost:7687 — then
asserts the wiring each one promises and runs a minimal smoke call to prove the loaded
model(s) generate. Each condition is built inside its own `with` block so its driver is
closed and its model(s) freed before the next.

Hardware note (recorded for the handoff): the spec's build_condition2/3 take a bare
`base_model: str` and hardcode the build_llm spec WITHOUT load_in_4bit/torch_dtype, so
C2/C3 load at the HuggingFaceLLM default (bf16, full precision). The signatures are fixed
(5.4 consumes them; the spec says "none change these signatures"), so this probe cannot
inject 4-bit there. Only C1 takes a full base_model_spec, so it is loaded in 4-bit/fp16.
On Kaya's 2×16 GB V100s C3's three separate 7B models (~42 GB) will not fit; each
condition is attempted independently and the outcome reported honestly.

Run inside a GPU job that also has Neo4j up on bolt://localhost:7687 (see
kaya/63_build_condition_probe.slurm).
"""
from __future__ import annotations

import argparse
import gc
import os
import sys
import traceback

# Run from repo root so the experiments/ package (not pip-installed, unlike pipeline) imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from experiments.build_condition1 import build_condition1
from experiments.build_condition2 import build_condition2
from experiments.build_condition3 import build_condition3
from pipeline.schema import build_pole_schema_repr
from pipeline.types import SchemaMapping


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="mistral7b")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--sl_inference_config", default="config/schema_linker_inference.yaml")
    args = ap.parse_args()

    import torch

    from pipeline.entity_lookup import entity_lookup

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    with open(args.sl_inference_config) as fh:
        diversity_penalty = yaml.safe_load(fh)["diversity_penalty"]

    base = registry["base"]
    dtype = registry.get("dtype", "float16")
    load_in_4bit = registry.get("load_in_4bit", True)

    uri = "bolt://localhost:7687"
    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    auth = ("neo4j", password)
    schema = build_pole_schema_repr()
    sl_adapter = f"checkpoints/{args.model_key}/sl_adapter"
    qg_adapter = f"checkpoints/{args.model_key}/qg_adapter"

    question = "Who is suspected of the Operation Ironside incident?"
    print(f"base={base} dtype={dtype} 4bit={load_in_4bit} dp={diversity_penalty}\n")

    def _free() -> None:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    results: dict[str, str] = {}

    # ── Condition 1 — baseline (single model; 4-bit/fp16 via its full spec) ────────
    print("==================== CONDITION 1 (baseline) ====================")
    try:
        spec = {"backend": "huggingface", "model_name_or_path": base,
                "load_in_4bit": load_in_4bit, "torch_dtype": dtype}
        with build_condition1(neo4j_uri=uri, neo4j_auth=auth, database_name=None,
                              base_model_spec=spec, schema=schema) as c:
            assert c.schema_linker is None
            assert c.ad_llm is None and c.dis_llm is None
            assert c.entity_cache is None
            assert c.neo4j_driver is not None
            assert c.syntax_validator and c.schema_validator and c.properties_validator
            zero = SchemaMapping(question=question, committed={}, cypher_syntax="",
                                 resolution_mode="automated")
            cypher = c.query_generator.generate(question, zero, schema)
            print(f"  wiring OK; zero-shot cypher: {cypher!r}")
        results["C1"] = "PASS"
    except Exception:
        traceback.print_exc()
        results["C1"] = "FAIL"
    _free()

    # ── Condition 2 — schema-grounded (SL beam_k=1 + QG; bf16, 2 models) ───────────
    print("\n==================== CONDITION 2 (schema_grounded) ====================")
    try:
        with build_condition2(neo4j_uri=uri, neo4j_auth=auth, database_name=None,
                              base_model=base, sl_adapter=sl_adapter, qg_adapter=qg_adapter,
                              schema=schema) as c:
            assert c.schema_linker is not None and c.schema_linker.beam_k == 1
            assert c.ad_llm is None and c.dis_llm is None
            assert c.entity_cache is None
            cm = c.schema_linker.link(question, schema)
            cypher = c.query_generator.generate(question, cm.top1_mapping(), schema)
            print(f"  wiring OK; SL+QG cypher: {cypher!r}")
        results["C2"] = "PASS"
    except Exception:
        traceback.print_exc()
        results["C2"] = "FAIL"
    _free()

    # ── Condition 3 — disambiguation-enhanced (SL beam_k=5 + QG + AD/Dis; cache) ───
    print("\n==================== CONDITION 3 (disambiguation_enhanced) ====================")
    try:
        with build_condition3(neo4j_uri=uri, neo4j_auth=auth, database_name=None,
                              base_model=base, sl_adapter=sl_adapter, qg_adapter=qg_adapter,
                              schema=schema, diversity_penalty=diversity_penalty) as c:
            assert c.schema_linker is not None and c.schema_linker.beam_k == 5
            assert c.schema_linker.diversity_penalty == diversity_penalty
            assert c.ad_llm is not None and c.dis_llm is not None
            assert c.dis_llm is c.ad_llm                      # shared default backend
            assert c.entity_cache is not None and len(c.entity_cache.nodes) > 0
            print(f"  entity_cache loaded: {len(c.entity_cache.nodes)} nodes")
            cm = c.schema_linker.link(question, schema)
            el = entity_lookup(question, cm, c.entity_cache)
            print(f"  wiring OK; SL mentions={list(cm.mentions)};"
                  f" entity mentions={list(el.entity_mentions)}")
        results["C3"] = "PASS"
    except Exception:
        traceback.print_exc()
        results["C3"] = "FAIL"
    _free()

    print("\n==================== SUMMARY ====================")
    for k in ("C1", "C2", "C3"):
        print(f"  {k}: {results.get(k, 'SKIP')}")


if __name__ == "__main__":
    main()
