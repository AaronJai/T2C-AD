# pipeline/execution/db_executor.py
"""Execute validated Cypher against Neo4j; capture results, timing, and errors."""
from __future__ import annotations

import time

import neo4j
from neo4j.exceptions import DriverError, Neo4jError

from pipeline.types import ExecutionResult


def db_executor(
    cypher: str,
    driver: neo4j.Driver,
    database: str = "neo4j",
    timeout_s: float = 10.0,
) -> ExecutionResult:
    """Run cypher in a managed read transaction; collect records; time it; map errors.

    The transaction carries a server-side timeout of ``timeout_s`` (set via
    ``neo4j.unit_of_work`` — the version-appropriate mechanism for ``execute_read`` in the
    installed driver, which reads the timeout off the transaction-function attribute and
    applies it at BEGIN), so a pathological traversal aborts server-side instead of hanging
    the run.

    CONTRACT (matches ``ExecutionResult``, 0.1):
      - Success: ``success=True``, ``result_set`` = ``[record.data() ...]`` (each a plain
        dict; nested nodes/relationships become their property dicts). An empty result set
        is a *legitimate* success, not a failure.
      - Any neo4j error — syntax/constraint/transient, or a transaction timeout (server-side
        ``Neo4jError``; client-side/driver issues are ``DriverError``): ``success=False``,
        ``result_set=[]``, ``error=str(e)``. ``execution_time_ms`` is set on both paths.
    """
    start = time.perf_counter()

    @neo4j.unit_of_work(timeout=timeout_s)
    def _run(tx: neo4j.ManagedTransaction) -> list[dict]:
        result = tx.run(cypher)
        return [record.data() for record in result]

    try:
        with driver.session(database=database) as session:
            records = session.execute_read(_run)
        elapsed = (time.perf_counter() - start) * 1000.0
        return ExecutionResult(
            success=True,
            result_set=records,
            error=None,
            execution_time_ms=elapsed,
        )
    except (Neo4jError, DriverError) as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return ExecutionResult(
            success=False,
            result_set=[],
            error=str(e),
            execution_time_ms=elapsed,
        )
