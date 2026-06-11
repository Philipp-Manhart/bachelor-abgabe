from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatabaseSettings(StrictModel):
    database_path: Path
    read_only: bool = True

    @classmethod
    def from_path(cls, database_path: str | Path, *, read_only: bool = True) -> DatabaseSettings:
        return cls(database_path=Path(database_path), read_only=read_only)


class ColumnMetadata(StrictModel):
    name: str
    data_type: str
    nullable: bool
    comment: str | None = None

    @field_validator("name", "data_type")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "Value must not be empty"
            raise ValueError(msg)
        return value


class TableMetadata(StrictModel):
    name: str
    comment: str | None = None
    columns: list[ColumnMetadata]
    row_count: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def require_non_empty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "Table name must not be empty"
            raise ValueError(msg)
        return value


class SchemaMetadata(StrictModel):
    database_path: Path
    tables: list[TableMetadata]


class SchemaResponse(StrictModel):
    metadata: SchemaMetadata
    context: str


class ExecuteSqlRequest(StrictModel):
    sql: str
    max_rows: int = Field(default=5, ge=1, le=1000)
    timeout_ms: int | None = Field(default=None, ge=1)

    @field_validator("sql")
    @classmethod
    def require_sql(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "SQL must not be empty"
            raise ValueError(msg)
        return value


class SqlExecutionError(StrictModel):
    error_type: str
    message: str
    stacktrace: str | None = None


class ExecuteSqlResult(StrictModel):
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    elapsed_ms: int | None = Field(default=None, ge=0)
    error: SqlExecutionError | None = None

    @model_validator(mode="after")
    def validate_success_error_shape(self) -> ExecuteSqlResult:
        if self.success and self.error is not None:
            msg = "Successful SQL results must not include an error"
            raise ValueError(msg)
        if not self.success and self.error is None:
            msg = "Failed SQL results must include an error"
            raise ValueError(msg)
        return self


class SampleDataRequest(StrictModel):
    table_name: str
    limit: int = Field(default=3, ge=1, le=100)

    @field_validator("table_name")
    @classmethod
    def require_table_name(cls, value: str) -> str:
        return _require_identifier_text(value, "Table name")


class CategoricalValuesRequest(StrictModel):
    table_name: str
    column: str

    @field_validator("table_name", "column")
    @classmethod
    def require_identifier(cls, value: str) -> str:
        return _require_identifier_text(value, "Identifier")


class NumericSummaryRequest(StrictModel):
    table_name: str
    column: str

    @field_validator("table_name", "column")
    @classmethod
    def require_identifier(cls, value: str) -> str:
        return _require_identifier_text(value, "Identifier")


class NumericSummaryResult(StrictModel):
    table_name: str
    column: str
    data_type: str
    min: Any = None
    max: Any = None
    avg: float | None = None
    null_count: int = Field(ge=0)


class ValidateSqlRequest(StrictModel):
    query: str

    @field_validator("query")
    @classmethod
    def require_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "SQL query must not be empty"
            raise ValueError(msg)
        return value


class ValidateSqlResult(StrictModel):
    valid: bool
    error: SqlExecutionError | None = None

    @model_validator(mode="after")
    def validate_error_shape(self) -> ValidateSqlResult:
        if self.valid and self.error is not None:
            msg = "Valid SQL validation results must not include an error"
            raise ValueError(msg)
        if not self.valid and self.error is None:
            msg = "Invalid SQL validation results must include an error"
            raise ValueError(msg)
        return self


class ChartConfigRequest(StrictModel):
    type: Literal["bar", "line", "area", "scatter"]
    x_axis: str
    y_axis: str

    @field_validator("x_axis", "y_axis")
    @classmethod
    def require_axis(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "Axis must not be empty"
            raise ValueError(msg)
        return value


class ChartConfig(StrictModel):
    mark: str
    encoding: dict[str, dict[str, str]]


def _require_identifier_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        msg = f"{label} must not be empty"
        raise ValueError(msg)
    return value
