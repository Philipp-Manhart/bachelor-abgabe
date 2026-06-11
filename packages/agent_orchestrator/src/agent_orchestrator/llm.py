from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

import litellm

from agent_orchestrator.config import OrchestratorSettings, load_settings


@dataclass(frozen=True)
class LlmResponse:
    content: str
    usage: dict[str, int | None]


class LlmClient(Protocol):
    def complete(self, *, system: str, user: str) -> LlmResponse: ...


class LiteLlmClient:
    def __init__(self, settings: OrchestratorSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def complete(self, *, system: str, user: str) -> LlmResponse:
        response = cast(
            Any,
            litellm.completion(
                model=self.settings.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.settings.temperature,
                api_key=self.settings.api_key,
                api_base=self.settings.base_url,
            ),
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LlmResponse(
            content=content,
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        )
