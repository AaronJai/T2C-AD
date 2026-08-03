# experiments/pole_query.py
"""Ad hoc query CLI (9.2) — one-off exploratory/verification Cypher against a live graph.

Thin, testable wrapper around the existing execution engine (`pipeline.execution.db_executor`,
3.8). Not a new execution engine: no write capability, no query rewriting, no retry. Exists to
remove friction from the 9.2 authoring loop (verifying ties/divergences/counts against the real
POLE-external graph) and for later spot-checks during 9.3's run.

CLI:
    python -m experiments.pole_query "MATCH (o:Officer {rank:'Sergeant'}) RETURN o.surname, o.name, count(*) AS n ORDER BY n DESC LIMIT 10"
    python -m experiments.pole_query "<cypher>" --limit 5

Reads the same NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE env contract as
validate_benchmark.py (the driver-opening helper is factored there and imported here, rather
than duplicated).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from experiments.validate_benchmark import _open_driver
from pipeline.execution import db_executor
from pipeline.types import ExecutionResult


def format_success_lines(result: ExecutionResult, limit: Optional[int] = None) -> list[str]:
    """Row-printing/summary logic for a successful run — pure, unit-testable.

    ``limit`` only truncates *display*: the summary line's n_rows always reflects the true
    row count the query actually returned, not the truncated print count.
    """
    rows = result.result_set
    printed = rows if limit is None else rows[:limit]
    lines = [json.dumps(row, default=str) for row in printed]
    lines.append(f"# n_rows={len(rows)} elapsed_ms={result.execution_time_ms}")
    return lines


def format_output(result: ExecutionResult, limit: Optional[int] = None) -> tuple[list[str], int]:
    """Pure success/failure dispatch — (lines, exit_code), no I/O. Unit-testable without a driver.

    Success lines are printed to stdout, the single failure line to stderr — the caller
    decides the stream; this only decides content and exit code.
    """
    if result.success:
        return format_success_lines(result, limit), 0
    return [result.error], 1


def run_query(cypher: str, limit: Optional[int] = None) -> int:
    """Open a driver, run ``cypher``, print rows/summary or the error. Returns exit code."""
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    driver = _open_driver()
    try:
        result = db_executor(cypher, driver, database=database)
    finally:
        driver.close()

    lines, code = format_output(result, limit)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ad hoc Cypher query CLI (9.2).")
    ap.add_argument("query", help="Cypher to run (executed as written, no rewriting).")
    ap.add_argument("--limit", type=int, default=None, help="Truncate printed rows only.")
    args = ap.parse_args(argv)
    return run_query(args.query, args.limit)


if __name__ == "__main__":
    sys.exit(main())
