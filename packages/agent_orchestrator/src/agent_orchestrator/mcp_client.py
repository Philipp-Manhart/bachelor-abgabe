from __future__ import annotations

import asyncio
import json
import queue
import threading
from concurrent.futures import Future
from typing import Any, Protocol, TypeVar, cast

from fastmcp import Client
from mcp.types import PromptMessage, TextContent, TextResourceContents

from agent_orchestrator.config import get_mcp_server_url

T = TypeVar("T")


class McpClient(Protocol):
    def schema_overview(self) -> list[dict[str, Any]]: ...

    def table_dictionary(self, table_name: str) -> dict[str, Any]: ...

    def schema_relationships(self) -> list[dict[str, Any]]: ...

    def business_glossary_term(self, term: str) -> dict[str, Any]: ...

    def sample_data(self, table_name: str, limit: int = 3) -> list[dict[str, Any]]: ...

    def categorical_values(self, table_name: str, column: str) -> list[str]: ...

    def numeric_summary(self, table_name: str, column: str) -> dict[str, Any]: ...

    def validate_sql(self, query: str) -> dict[str, Any]: ...

    def execute_sql(self, query: str) -> dict[str, Any]: ...

    def prompt(self, name: str) -> str: ...

    def close(self) -> None: ...


class FastMcpClient:
    """Synchronous facade over one persistent FastMCP protocol session."""

    def __init__(self, transport: Any = None) -> None:
        self.transport = transport or get_mcp_server_url()
        self._requests: queue.Queue[tuple[str | None, tuple[Any, ...], Future[Any]]] = queue.Queue()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run_session,
            name="fastmcp-client-loop",
            daemon=True,
        )
        self._closed = False
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise ConnectionError("Failed to connect to the MCP server.") from self._startup_error

    def schema_overview(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._read_resource_json("dwh://schema/overview"))

    def table_dictionary(self, table_name: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._read_resource_json(f"dwh://schema/tables/{table_name}"),
        )

    def schema_relationships(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._read_resource_json("dwh://schema/relationships"),
        )

    def business_glossary_term(self, term: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._read_resource_json(f"dwh://business_glossary/{term}"),
        )

    def sample_data(self, table_name: str, limit: int = 3) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._call_tool_json(
                "get_sample_data",
                {"table_name": table_name, "limit": limit},
            ),
        )

    def categorical_values(self, table_name: str, column: str) -> list[str]:
        return cast(
            list[str],
            self._call_tool_json(
                "get_categorical_values",
                {"table_name": table_name, "column": column},
            ),
        )

    def numeric_summary(self, table_name: str, column: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._call_tool_json(
                "get_numeric_summary",
                {"table_name": table_name, "column": column},
            ),
        )

    def validate_sql(self, query: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._call_tool_json("validate_sql", {"query": query}))

    def execute_sql(self, query: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._call_tool_json("execute_sql", {"query": query}))

    def prompt(self, name: str) -> str:
        messages = cast(list[PromptMessage], self._submit("get_prompt", name))
        return "\n".join(_prompt_message_text(message) for message in messages)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._requests.put((None, (), Future()))
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("MCP client session did not close within 5 seconds.")

    def __enter__(self) -> FastMcpClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _run_session(self) -> None:
        try:
            asyncio.run(self._serve_requests())
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()

    async def _serve_requests(self) -> None:
        async with Client(self.transport) as client:
            self._ready.set()
            while True:
                try:
                    operation, arguments, future = self._requests.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.001)
                    continue
                if operation is None:
                    return
                try:
                    result = await _execute_request(client, operation, arguments)
                except BaseException as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(result)

    def _read_resource_json(self, uri: str) -> Any:
        contents = cast(list[TextResourceContents], self._submit("read_resource", uri))
        if len(contents) != 1 or not isinstance(contents[0], TextResourceContents):
            msg = f"Expected one text resource for {uri}, received {len(contents)} items."
            raise ValueError(msg)
        return json.loads(contents[0].text)

    def _call_tool_json(self, name: str, arguments: dict[str, Any]) -> Any:
        contents = cast(list[TextContent], self._submit("call_tool", name, arguments))
        if len(contents) != 1 or not isinstance(contents[0], TextContent):
            msg = f"Expected one text result from MCP tool {name}, received {len(contents)} items."
            raise ValueError(msg)
        return json.loads(contents[0].text)

    def _submit(self, operation: str, *arguments: Any) -> T:
        if self._closed:
            raise RuntimeError("MCP client is closed.")
        future: Future[T] = Future()
        self._requests.put((operation, arguments, cast(Future[Any], future)))
        return future.result()


def _prompt_message_text(message: PromptMessage) -> str:
    content = message.content
    if not isinstance(content, TextContent):
        raise ValueError("MCP prompt returned non-text content.")
    return content.text


async def _execute_request(client: Client, operation: str, arguments: tuple[Any, ...]) -> Any:
    if operation == "read_resource":
        return await client.read_resource(arguments[0])
    if operation == "call_tool":
        return await client.call_tool(arguments[0], arguments[1])
    if operation == "get_prompt":
        return await client.get_prompt(arguments[0])
    raise ValueError(f"Unsupported MCP client operation: {operation}")
