from __future__ import annotations

from agent_orchestrator.config import load_settings
from agent_orchestrator.llm import LiteLlmClient


def test_default_llm_model_is_deepseek_v4_flash(monkeypatch) -> None:
    monkeypatch.setattr("agent_orchestrator.config.load_dotenv", lambda: None)
    monkeypatch.delenv("TEXT_TO_SQL_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = load_settings()

    assert settings.model == "deepseek/deepseek-v4-flash"


def test_documented_llm_environment_variables_configure_litellm(monkeypatch) -> None:
    monkeypatch.setattr("agent_orchestrator.config.load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")

    settings = load_settings()

    assert settings.model == "deepseek/deepseek-v4-flash"
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://api.deepseek.com"


def test_litellm_client_passes_configured_provider_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Message:
        content = "SELECT 1"

    class Choice:
        message = Message()

    class Response:
        def __init__(self) -> None:
            self.choices = [Choice()]
            self.usage = None

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("agent_orchestrator.config.load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr("agent_orchestrator.llm.litellm.completion", fake_completion)

    LiteLlmClient().complete(system="system", user="user")

    assert captured["model"] == "deepseek/deepseek-v4-flash"
    assert captured["api_key"] == "test-key"
    assert captured["api_base"] == "https://api.deepseek.com"
    assert captured["temperature"] == 0.0
