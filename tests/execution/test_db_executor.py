# tests/execution/test_db_executor.py
"""Contract tests for the DB Executor (step 3.8) — no live Neo4j required."""
from __future__ import annotations

from neo4j.exceptions import CypherSyntaxError

from pipeline.execution import db_executor
from pipeline.types import ExecutionResult


class _FakeSession:
    """Stands in for a neo4j read session; execute_read returns records or raises."""

    def __init__(self, records=None, exc=None):
        self._records = records
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute_read(self, transaction_function, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._records


class _FakeDriver:
    """Minimal stand-in for neo4j.Driver; records the database it was asked for."""

    def __init__(self, records=None, exc=None):
        self._records = records
        self._exc = exc
        self.database_seen = None

    def session(self, database="neo4j"):
        self.database_seen = database
        return _FakeSession(self._records, self._exc)


def test_contract_matches_types() -> None:
    """db_executor returns an ExecutionResult with the 0.1 fields."""
    driver = _FakeDriver(records=[])
    result = db_executor("MATCH (n) RETURN n", driver)  # type: ignore[arg-type]
    assert isinstance(result, ExecutionResult)
    assert hasattr(result, "success")
    assert hasattr(result, "result_set")
    assert hasattr(result, "error")
    assert hasattr(result, "execution_time_ms")


def test_success_returns_records_and_time() -> None:
    """Acceptance #2: execute_read returns rows → success with that result set."""
    driver = _FakeDriver(records=[{"name": "X"}])
    result = db_executor("MATCH (n:Person) RETURN n.name AS name", driver, database="pole")  # type: ignore[arg-type]

    assert result.success is True
    assert result.result_set == [{"name": "X"}]
    assert result.error is None
    assert isinstance(result.execution_time_ms, float)
    assert result.execution_time_ms > 0.0
    # database arg is threaded through to driver.session(...)
    assert driver.database_seen == "pole"


def test_empty_result_is_success() -> None:
    """An empty result set is a legitimate success, not a failure (edge case)."""
    driver = _FakeDriver(records=[])
    result = db_executor("MATCH (n:Person) WHERE n.name = 'nobody' RETURN n", driver)  # type: ignore[arg-type]

    assert result.success is True
    assert result.result_set == []
    assert result.error is None
    assert result.execution_time_ms is not None


def test_neo4j_error_is_captured_not_raised() -> None:
    """Acceptance #3: a Neo4jError → success=False, empty set, error message, time set."""
    driver = _FakeDriver(exc=CypherSyntaxError("Invalid syntax near 'FOO'"))
    result = db_executor("FOO BAR", driver)  # type: ignore[arg-type]

    assert result.success is False
    assert result.result_set == []
    assert result.error is not None
    assert "Invalid syntax" in result.error
    assert isinstance(result.execution_time_ms, float)
    assert result.execution_time_ms >= 0.0
