from __future__ import annotations

from types import TracebackType

import duckdb

from mcp_server.models import DatabaseSettings

DatabaseConfig = DatabaseSettings


class DuckDBConnection:
    def __init__(self, config: DatabaseSettings) -> None:
        self.config = config
        self._connection: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> duckdb.DuckDBPyConnection:
        if not self.config.database_path.exists():
            msg = f"DuckDB database file does not exist: {self.config.database_path}"
            raise FileNotFoundError(msg)

        self._connection = duckdb.connect(
            str(self.config.database_path),
            read_only=self.config.read_only,
        )
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
