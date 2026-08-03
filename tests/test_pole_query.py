"""Offline contract tests for the ad hoc query CLI (step 9.2).

No Neo4j: exercises the pure row-printing/summary logic against a fake ExecutionResult
(success and failure paths), per acceptance criterion 2 — never opens a real driver.
"""
from __future__ import annotations

from experiments.pole_query import format_output, format_success_lines
from pipeline.types import ExecutionResult


def _success(rows: list[dict], elapsed: float = 12.5) -> ExecutionResult:
    return ExecutionResult(success=True, result_set=rows, error=None, execution_time_ms=elapsed)


def _failure(error: str = "Neo.ClientError.Statement.SyntaxError: boom") -> ExecutionResult:
    return ExecutionResult(success=False, result_set=[], error=error, execution_time_ms=3.0)


def test_success_prints_one_json_line_per_row_plus_summary():
    result = _success([{"a": 1}, {"a": 2}])
    lines = format_success_lines(result)
    assert lines[0] == '{"a": 1}'
    assert lines[1] == '{"a": 2}'
    assert lines[2] == "# n_rows=2 elapsed_ms=12.5"


def test_success_empty_result_set_prints_only_summary():
    result = _success([])
    lines = format_success_lines(result)
    assert lines == ["# n_rows=0 elapsed_ms=12.5"]


def test_limit_truncates_display_but_not_true_row_count():
    result = _success([{"a": 1}, {"a": 2}, {"a": 3}])
    lines = format_success_lines(result, limit=1)
    assert lines == ['{"a": 1}', "# n_rows=3 elapsed_ms=12.5"]


def test_limit_none_prints_every_row():
    result = _success([{"a": n} for n in range(5)])
    lines = format_success_lines(result, limit=None)
    assert len(lines) == 6  # 5 rows + summary


def test_default_str_handles_non_json_native_values():
    result = _success([{"d": object()}])
    # Must not raise — default=str stringifies anything json can't serialise natively.
    lines = format_success_lines(result)
    assert lines[0].startswith('{"d": ')


def test_format_output_success_returns_exit_code_zero():
    lines, code = format_output(_success([{"a": 1}]))
    assert code == 0
    assert lines == ['{"a": 1}', "# n_rows=1 elapsed_ms=12.5"]


def test_format_output_failure_returns_error_and_nonzero_exit():
    err = "Neo.ClientError.Statement.SyntaxError: boom"
    lines, code = format_output(_failure(err))
    assert code == 1
    assert lines == [err]


def test_format_output_failure_ignores_limit():
    lines, code = format_output(_failure("oops"), limit=5)
    assert code == 1
    assert lines == ["oops"]
