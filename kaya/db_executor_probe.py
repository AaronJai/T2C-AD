"""Criterion-4 probe for step 3.8 (DB Executor).

Runs `db_executor` against the live SyntheticPoliceKG (POLE) graph and confirms:
  - real POLE queries return the expected rows (and an empty result is a success, not a
    failure; nested nodes come back as plain property dicts);
  - a deliberately heavy variable-length traversal hits the server-side timeout and returns
    `success=False` with `execution_time_ms` still set (the pathological-traversal guard).

Run inside a job with Neo4j up on bolt://localhost:7687 (see kaya/59_db_executor_probe.slurm).
"""
from __future__ import annotations

import os
import sys

import neo4j

from pipeline.execution import db_executor


def main() -> int:
    password = os.environ.get("NEO4J_PASSWORD", "pole-dev-password")
    driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    driver.verify_connectivity()

    all_ok = True

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        all_ok &= ok
        print(f"{label:<40} {'YES' if ok else 'NO':<4} {detail}")

    print(f"{'case':<40} {'ok':<4} detail")
    print("-" * 100)

    # 1. Simple query returns rows.
    r = db_executor("MATCH (p:Person) RETURN p.name AS name ORDER BY name LIMIT 5", driver)
    check("rows / success",
          r.success and len(r.result_set) > 0 and r.error is None,
          f"success={r.success} n={len(r.result_set)} t_ms={r.execution_time_ms:.2f} "
          f"sample={r.result_set[:1]}")

    # 2. Empty result is a legitimate success (empty != failure).
    r = db_executor(
        "MATCH (p:Person) WHERE p.name = '___definitely_no_such_person___' RETURN p", driver)
    check("empty result / success",
          r.success and r.result_set == [] and r.error is None,
          f"success={r.success} result_set={r.result_set} t_ms={r.execution_time_ms:.2f}")

    # 3. Relationship query: nested node comes back as a plain property dict.
    r = db_executor(
        "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident) RETURN p.name AS suspect, i LIMIT 3",
        driver)
    nested_ok = (r.success and len(r.result_set) > 0
                 and isinstance(r.result_set[0].get("i"), dict))
    check("relationship+node / nested dict",
          nested_ok,
          f"success={r.success} n={len(r.result_set)} sample={r.result_set[:1]}")

    # 4. Pathological variable-length traversal must hit the server-side timeout.
    heavy = "MATCH path=(a)-[*1..30]-(b) RETURN count(path) AS c"
    r = db_executor(heavy, driver, timeout_s=2.0)
    timeout_ok = (r.success is False and r.result_set == []
                  and r.error is not None and r.execution_time_ms is not None)
    check("heavy var-length / timeout fail",
          timeout_ok,
          f"success={r.success} t_ms={r.execution_time_ms:.2f} error={r.error!r}")

    driver.close()
    print("-" * 100)
    print("ALL CHECKS PASSED" if all_ok else "FAILURE — see rows above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
