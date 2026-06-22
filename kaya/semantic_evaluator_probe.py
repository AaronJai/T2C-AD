"""Criterion-6 probe for step 4.1 (Semantic Evaluator).

Runs `semantic_evaluator` end-to-end against the live SyntheticPoliceKG (POLE) graph:
`_execute_ground_truth` hits the real driver and a benchmark question's gold result set is
compared for real. Confirms the three failure-mode branches against live data:

  - pipeline result == gold default            → is_correct=True,  failure_mode=None
  - pipeline result == a non-default interp    → is_correct=False, matches_any=True,
                                                  failure_mode='valid_non_default'
  - pipeline result == neither (garbage rows)  → is_correct=False, matches_any=False,
                                                  failure_mode='wrong_result'
  - execution failed / CyVer not accepted      → failure_mode='invalid_query'

The "pipeline result" is produced by executing real Cypher with the SAME executor/driver
the orchestrator uses (db_executor / .data()), so both sides of the comparison line up.

Run inside a job with Neo4j up on bolt://localhost:7687 (see kaya/61_semantic_evaluator_probe.slurm).
"""
from __future__ import annotations

import os
import sys

import neo4j

from pipeline.data.benchmark_loader import ambiguous_items, load_benchmark
from pipeline.evaluation import semantic_evaluator
from pipeline.evaluation.semantic_evaluator import _run_query
from pipeline.execution import db_executor
from pipeline.types import ExecutionResult, ValidationResult

BENCHMARK_PATH = "data/benchmark-updated.json"


def _accept() -> ValidationResult:
    return ValidationResult(
        syntax_valid=True, schema_score=1.0, properties_score=1.0,
        error_type=None, route_to="accept",
    )


def _exec(driver: neo4j.Driver, cypher: str) -> ExecutionResult:
    """Run cypher with the real executor → ExecutionResult (matches orchestrator path)."""
    return db_executor(cypher, driver)


def main() -> int:
    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    driver.verify_connectivity()

    items = load_benchmark(BENCHMARK_PATH)
    all_ok = True

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        all_ok &= ok
        print(f"{label:<44} {'YES' if ok else 'NO':<4} {detail}")

    print(f"{'case':<44} {'ok':<4} detail")
    print("-" * 110)

    # ── 1. Correct: run an item's own gold default → must match default exactly. ──
    unambig = next(it for it in items if not it.is_ambiguous)
    gold = _exec(driver, unambig.cypher_default)
    res = semantic_evaluator(
        execution_result=gold, benchmark_item=unambig,
        generated_cypher=unambig.cypher_default, cyver_result=_accept(),
        condition="schema_grounded", retry_count=0,
        driver=driver, database_name=None, is_first_attempt=True,
    )
    check(f"default==default → correct [{unambig.question_id}]",
          res.is_correct and res.matches_any_interpretation and res.failure_mode is None,
          f"is_correct={res.is_correct} matches_any={res.matches_any_interpretation} "
          f"mode={res.failure_mode} n={len(gold.result_set)}")

    # ── 2. valid_non_default: run a non-default interpretation whose live result set ──
    #     differs from the default; must be matches_any=True, is_correct=False.
    found_vnd = False
    for it in ambiguous_items(items):
        default_rows = _run_query(it.cypher_default, driver, None)
        for interp in it.interpretations:
            interp_rows = _run_query(interp["cypher"], driver, None)
            # Need a genuinely non-default interpretation (differing live result set).
            from pipeline.evaluation.semantic_evaluator import _result_sets_equal
            if _result_sets_equal(interp_rows, default_rows):
                continue
            exec_res = ExecutionResult(success=True, result_set=interp_rows,
                                       error=None, execution_time_ms=1.0)
            res = semantic_evaluator(
                execution_result=exec_res, benchmark_item=it,
                generated_cypher=interp["cypher"], cyver_result=_accept(),
                condition="disambiguation_enhanced", retry_count=0,
                driver=driver, database_name=None,
            )
            check(f"non-default interp → valid_non_default [{it.question_id}]",
                  (not res.is_correct) and res.matches_any_interpretation
                  and res.failure_mode == "valid_non_default",
                  f"is_correct={res.is_correct} matches_any={res.matches_any_interpretation} "
                  f"mode={res.failure_mode}")
            found_vnd = True
            break
        if found_vnd:
            break
    if not found_vnd:
        check("non-default interp → valid_non_default", False,
              "no ambiguous item had an interpretation with a differing live result set")

    # ── 3. wrong_result: a clearly-fabricated result set matches nothing. ──
    garbage = ExecutionResult(success=True,
                              result_set=[{"__nope__": "___definitely_not_a_real_row___"}],
                              error=None, execution_time_ms=1.0)
    res = semantic_evaluator(
        execution_result=garbage, benchmark_item=unambig,
        generated_cypher="MATCH (x) RETURN x LIMIT 0", cyver_result=_accept(),
        condition="schema_grounded", retry_count=0,
        driver=driver, database_name=None,
    )
    check(f"garbage rows → wrong_result [{unambig.question_id}]",
          (not res.is_correct) and (not res.matches_any_interpretation)
          and res.failure_mode == "wrong_result",
          f"is_correct={res.is_correct} matches_any={res.matches_any_interpretation} "
          f"mode={res.failure_mode}")

    # ── 4. invalid_query: execution failed → never executes ground truth. ──
    failed = ExecutionResult(success=False, result_set=[], error="boom", execution_time_ms=1.0)
    res = semantic_evaluator(
        execution_result=failed, benchmark_item=unambig,
        generated_cypher="FOO BAR", cyver_result=_accept(),
        condition="schema_grounded", retry_count=0,
        driver=driver, database_name=None,
    )
    check(f"exec failed → invalid_query [{unambig.question_id}]",
          (not res.is_correct) and (not res.matches_any_interpretation)
          and res.failure_mode == "invalid_query",
          f"is_correct={res.is_correct} matches_any={res.matches_any_interpretation} "
          f"mode={res.failure_mode}")

    driver.close()
    print("-" * 110)
    print("ALL CHECKS PASSED" if all_ok else "FAILURE — see rows above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
