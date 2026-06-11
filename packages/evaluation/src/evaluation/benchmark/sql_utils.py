from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any

from mcp_server import DatabaseSettings, ExecuteSqlRequest, execute_sql

DEFAULT_EVALUATION_SQL_TIMEOUT_MS = 30_000


@dataclass(frozen=True)
class ComparisonResult:
    matches: bool
    order_required: bool
    order_exact: bool | None
    projection_exact: bool | None
    extra_columns: bool
    missing_expected_columns: bool
    matched_by_projection: bool
    matched_by_name_reorder: bool = False
    result_truncated: bool = False


def execute_for_evaluation(database_path: str | Path, sql: str) -> dict[str, Any]:
    settings = DatabaseSettings.from_path(database_path)
    return execute_sql(
        settings,
        ExecuteSqlRequest(
            sql=sql,
            max_rows=1000,
            timeout_ms=_evaluation_timeout_ms(),
        ),
    ).model_dump(mode="json")


def compare_results(
    actual_result: Any,
    expected_result: Any,
    *,
    tolerance: float = 1e-6,
    check_columns: bool = False,
    expected_columns: list[str] | None = None,
    respect_row_order: bool = False,
    allow_projection_match: bool = False,
) -> bool:
    return compare_result_details(
        actual_result,
        expected_result,
        tolerance=tolerance,
        check_columns=check_columns,
        expected_columns=expected_columns,
        respect_row_order=respect_row_order,
        allow_projection_match=allow_projection_match,
    ).matches


def compare_result_details(
    actual_result: Any,
    expected_result: Any,
    *,
    tolerance: float = 1e-6,
    check_columns: bool = False,
    expected_columns: list[str] | None = None,
    respect_row_order: bool = False,
    allow_projection_match: bool = False,
) -> ComparisonResult:
    actual_columns = _result_columns(actual_result)
    expected_column_names = expected_columns or _result_columns(expected_result)
    expected_width = len(expected_column_names)
    actual_width = len(actual_columns)
    projection_exact = actual_columns == expected_column_names if expected_column_names else None
    extra_columns = bool(expected_width and actual_width > expected_width)
    missing_expected_columns = bool(
        expected_column_names and not set(expected_column_names).issubset(set(actual_columns))
    )
    result_truncated = _result_truncated(actual_result) or _result_truncated(expected_result)

    if result_truncated:
        return ComparisonResult(
            matches=False,
            order_required=respect_row_order,
            order_exact=None,
            projection_exact=projection_exact,
            extra_columns=extra_columns,
            missing_expected_columns=missing_expected_columns,
            matched_by_projection=False,
            result_truncated=True,
        )

    if check_columns and not _columns_match(actual_result, expected_result, expected_columns):
        return ComparisonResult(
            matches=False,
            order_required=respect_row_order,
            order_exact=None,
            projection_exact=projection_exact,
            extra_columns=extra_columns,
            missing_expected_columns=missing_expected_columns,
            matched_by_projection=False,
            result_truncated=result_truncated,
        )

    actual = _normalize_result(
        actual_result,
        sort_rows=not respect_row_order,
        sort_columns=check_columns,
    )
    expected = _normalize_result(
        expected_result,
        sort_rows=not respect_row_order,
        sort_columns=check_columns,
    )
    direct_match = _normalized_results_equal(actual, expected, tolerance)
    order_exact = None
    if direct_match and not respect_row_order:
        ordered_actual = _normalize_result(
            actual_result,
            sort_rows=False,
            sort_columns=check_columns,
        )
        ordered_expected = _normalize_result(
            expected_result,
            sort_rows=False,
            sort_columns=check_columns,
        )
        order_exact = _normalized_results_equal(ordered_actual, ordered_expected, tolerance)
    if direct_match:
        return ComparisonResult(
            matches=True,
            order_required=respect_row_order,
            order_exact=True if respect_row_order else order_exact,
            projection_exact=projection_exact,
            extra_columns=extra_columns,
            missing_expected_columns=missing_expected_columns,
            matched_by_projection=False,
            result_truncated=result_truncated,
        )

    named_reorder_match = False
    if _can_compare_by_column_name(actual_columns, expected_column_names):
        named_actual = _normalize_result_to_columns(
            actual_result,
            expected_column_names,
            sort_rows=not respect_row_order,
        )
        named_expected = _normalize_result(
            expected_result,
            sort_rows=not respect_row_order,
            sort_columns=False,
        )
        named_reorder_match = _normalized_results_equal(named_actual, named_expected, tolerance)
        if named_reorder_match:
            ordered_named_actual = _normalize_result_to_columns(
                actual_result,
                expected_column_names,
                sort_rows=False,
            )
            ordered_expected = _normalize_result(
                expected_result,
                sort_rows=False,
                sort_columns=False,
            )
            return ComparisonResult(
                matches=True,
                order_required=respect_row_order,
                order_exact=True
                if respect_row_order
                else _normalized_results_equal(ordered_named_actual, ordered_expected, tolerance),
                projection_exact=projection_exact,
                extra_columns=extra_columns,
                missing_expected_columns=missing_expected_columns,
                matched_by_projection=False,
                matched_by_name_reorder=True,
                result_truncated=result_truncated,
            )

    projected_match = False
    if allow_projection_match and not check_columns:
        projected_match = _projection_matches(
            actual_result,
            expected_result,
            expected_column_names,
            tolerance,
            respect_row_order,
        )
    return ComparisonResult(
        matches=projected_match,
        order_required=respect_row_order,
        order_exact=None if projected_match and respect_row_order else False,
        projection_exact=projection_exact,
        extra_columns=extra_columns,
        missing_expected_columns=missing_expected_columns,
        matched_by_projection=projected_match,
        result_truncated=result_truncated,
    )


def extract_tables(sql: str | None) -> set[str]:
    if not sql:
        return set()
    tokens = _sql_tokens(sql)
    cte_names = _cte_names(tokens)
    tables: set[str] = set()
    for index, token in enumerate(tokens):
        if token.value.lower() not in {"from", "join"}:
            continue
        table = _next_table_identifier(tokens, index + 1)
        if table is not None:
            tables.add(table)
    return tables - cte_names


def table_f1(
    sql: str | None, expected_tables: list[str]
) -> tuple[float | None, float | None, float | None]:
    if not expected_tables:
        return None, None, None
    predicted = extract_tables(sql)
    expected = set(expected_tables)
    if not predicted:
        return 0.0, 0.0, 0.0
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted)
    recall = true_positive / len(expected)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def _normalize_result(
    result: Any,
    *,
    sort_rows: bool,
    sort_columns: bool,
) -> list[tuple[Any, ...]] | None:
    if isinstance(result, dict) and "rows" in result:
        if result.get("success") is False:
            return None
        columns = [str(column) for column in result.get("columns") or []]
        rows = result.get("rows") or []
        if not isinstance(rows, list):
            return None
        order = (
            sorted(range(len(columns)), key=lambda index: columns[index])
            if sort_columns
            else list(range(len(columns)))
        )
        normalized_rows = [
            tuple(_normalize_value(row[index]) for index in order)
            for row in rows
            if isinstance(row, list) and len(row) >= len(columns)
        ]
        return sorted(normalized_rows, key=repr) if sort_rows else normalized_rows
    if isinstance(result, list):
        normalized_rows = [tuple(_normalize_value(value) for value in row) for row in result]
        return sorted(normalized_rows, key=repr) if sort_rows else normalized_rows
    return None


def _projection_matches(
    actual_result: Any,
    expected_result: Any,
    expected_columns: list[str],
    tolerance: float,
    respect_row_order: bool,
) -> bool:
    actual_columns = _result_columns(actual_result)
    expected_width = len(expected_columns)
    if not expected_width or len(actual_columns) < expected_width:
        return False

    named_indexes = _expected_column_indexes(actual_columns, expected_columns)
    candidate_indexes: list[tuple[int, ...]] = []
    if named_indexes is not None:
        candidate_indexes.append(named_indexes)
    if len(actual_columns) <= 8:
        candidate_indexes.extend(
            indexes
            for indexes in combinations(range(len(actual_columns)), expected_width)
            if indexes not in candidate_indexes
        )

    expected = _normalize_result(
        expected_result,
        sort_rows=not respect_row_order,
        sort_columns=False,
    )
    if expected is None:
        return False
    for indexes in candidate_indexes:
        projected_actual = _normalize_projected_result(
            actual_result,
            indexes,
            sort_rows=not respect_row_order,
        )
        if _normalized_results_equal(projected_actual, expected, tolerance):
            return True
    return False


def _expected_column_indexes(
    actual_columns: list[str],
    expected_columns: list[str],
) -> tuple[int, ...] | None:
    indexes: list[int] = []
    for column in expected_columns:
        try:
            indexes.append(actual_columns.index(column))
        except ValueError:
            return None
    return tuple(indexes)


def _normalize_projected_result(
    result: Any,
    indexes: tuple[int, ...],
    *,
    sort_rows: bool,
) -> list[tuple[Any, ...]] | None:
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    rows = result.get("rows") or []
    if not isinstance(rows, list):
        return None
    normalized_rows = [
        tuple(_normalize_value(row[index]) for index in indexes)
        for row in rows
        if isinstance(row, list) and len(row) > max(indexes, default=-1)
    ]
    return sorted(normalized_rows, key=repr) if sort_rows else normalized_rows


def _normalize_result_to_columns(
    result: Any,
    expected_columns: list[str],
    *,
    sort_rows: bool,
) -> list[tuple[Any, ...]] | None:
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    indexes = _expected_column_indexes(_result_columns(result), expected_columns)
    if indexes is None:
        return None
    return _normalize_projected_result(result, indexes, sort_rows=sort_rows)


def _can_compare_by_column_name(
    actual_columns: list[str],
    expected_columns: list[str],
) -> bool:
    return (
        bool(actual_columns)
        and len(actual_columns) == len(expected_columns)
        and set(actual_columns) == set(expected_columns)
        and actual_columns != expected_columns
    )


def _normalized_results_equal(
    actual: list[tuple[Any, ...]] | None,
    expected: list[tuple[Any, ...]] | None,
    tolerance: float,
) -> bool:
    if actual is None or expected is None:
        return False
    if len(actual) != len(expected):
        return False
    return all(
        _rows_equal(left, right, tolerance) for left, right in zip(actual, expected, strict=True)
    )


def _columns_match(
    actual_result: Any,
    expected_result: Any,
    expected_columns: list[str] | None,
) -> bool:
    expected = expected_columns or _result_columns(expected_result)
    if not expected:
        return True
    return _result_columns(actual_result) == expected


def _result_columns(result: Any) -> list[str]:
    if isinstance(result, dict) and "columns" in result:
        return [str(column) for column in result.get("columns") or []]
    return []


def _result_truncated(result: Any) -> bool:
    return bool(result.get("truncated")) if isinstance(result, dict) else False


def _rows_equal(left: tuple[Any, ...], right: tuple[Any, ...], tolerance: float) -> bool:
    if len(left) != len(right):
        return False
    return all(
        _values_equal(left_value, right_value, tolerance)
        for left_value, right_value in zip(left, right, strict=True)
    )


def _values_equal(left: Any, right: Any, tolerance: float) -> bool:
    if left is None and right is None:
        return True
    if _is_number(left) and _is_number(right):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    return left == right


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _evaluation_timeout_ms() -> int:
    raw_value = os.getenv("EVALUATION_SQL_TIMEOUT_MS")
    if raw_value is None or raw_value == "":
        return DEFAULT_EVALUATION_SQL_TIMEOUT_MS
    return max(1, int(raw_value))


class _Token:
    def __init__(self, value: str) -> None:
        self.value = value


def _sql_tokens(sql: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace() or char == ";":
            index += 1
            continue
        if char == ",":
            tokens.append(_Token(char))
            index += 1
            continue
        if char == "-" and index + 1 < len(sql) and sql[index + 1] == "-":
            index = _advance_to_line_end(sql, index + 2)
            continue
        if char == "/" and index + 1 < len(sql) and sql[index + 1] == "*":
            index = _advance_to_block_comment_end(sql, index + 2)
            continue
        if char == "'":
            index = _advance_quoted(sql, index, "'")
            continue
        if char == '"':
            value, index = _read_quoted_identifier(sql, index)
            value, index = _read_identifier_suffix(sql, index, value)
            tokens.append(_Token(value))
            continue
        if char in "()":
            tokens.append(_Token(char))
            index += 1
            continue
        if char.isalpha() or char == "_":
            value, index = _read_identifier(sql, index)
            value, index = _read_identifier_suffix(sql, index, value)
            tokens.append(_Token(value))
            continue
        index += 1
    return tokens


def _next_table_identifier(tokens: list[_Token], start: int) -> str | None:
    index = start
    while index < len(tokens):
        value = tokens[index].value
        lowered = value.lower()
        if value == "(":
            return None
        if lowered in {"lateral", "unnest", "select", "values"}:
            return None
        if lowered in {"only"}:
            index += 1
            continue
        if _is_identifier(value):
            return _normalize_table_name(value)
        index += 1
    return None


def _cte_names(tokens: list[_Token]) -> set[str]:
    if not tokens or tokens[0].value.lower() != "with":
        return set()
    names: set[str] = set()
    index = 1
    while index < len(tokens):
        value = tokens[index].value
        lowered = value.lower()
        if lowered in {"recursive"}:
            index += 1
            continue
        if value in {"(", ")"} or lowered == "select":
            return names
        if _is_identifier(value):
            names.add(_normalize_table_name(value))
            index += 1
            while index < len(tokens) and tokens[index].value.lower() != "as":
                if tokens[index].value.lower() == "select":
                    return names
                index += 1
            if index < len(tokens) and tokens[index].value.lower() == "as":
                index += 1
            if index < len(tokens) and tokens[index].value == "(":
                index = _skip_balanced_parentheses(tokens, index)
                if index < len(tokens) and tokens[index].value == ",":
                    index += 1
                    continue
            return names
        index += 1
    return names


def _skip_balanced_parentheses(tokens: list[_Token], start: int) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        value = tokens[index].value
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(tokens)


def _is_identifier(value: str) -> bool:
    return bool(value) and value not in {"(", ")"}


def _normalize_table_name(value: str) -> str:
    return value.split(".")[-1].strip('"')


def _advance_to_line_end(sql: str, index: int) -> int:
    while index < len(sql) and sql[index] != "\n":
        index += 1
    return index


def _advance_to_block_comment_end(sql: str, index: int) -> int:
    while index + 1 < len(sql):
        if sql[index] == "*" and sql[index + 1] == "/":
            return index + 2
        index += 1
    return len(sql)


def _advance_quoted(sql: str, index: int, quote: str) -> int:
    index += 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def _read_quoted_identifier(sql: str, index: int) -> tuple[str, int]:
    start = index + 1
    index += 1
    value = []
    while index < len(sql):
        if sql[index] == '"':
            if index + 1 < len(sql) and sql[index + 1] == '"':
                value.append('"')
                index += 2
                continue
            return "".join(value), index + 1
        value.append(sql[index])
        index += 1
    return sql[start:], len(sql)


def _read_identifier(sql: str, index: int) -> tuple[str, int]:
    value = []
    while index < len(sql):
        char = sql[index]
        if char.isalnum() or char == "_":
            value.append(char)
            index += 1
            continue
        break
    return "".join(value), index


def _read_identifier_suffix(sql: str, index: int, prefix: str) -> tuple[str, int]:
    value = prefix
    while index < len(sql) and sql[index] == ".":
        if index + 1 >= len(sql):
            return value, index
        next_char = sql[index + 1]
        if next_char == '"':
            next_value, index = _read_quoted_identifier(sql, index + 1)
        elif next_char.isalpha() or next_char == "_":
            next_value, index = _read_identifier(sql, index + 1)
        else:
            return value, index
        value = f"{value}.{next_value}"
    return value, index
