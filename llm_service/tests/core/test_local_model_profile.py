"""The Mac handoff must offer local generation without unrelated model choices."""

from pathlib import Path

import yaml

from src.core.model_registry import ModelRegistry


def test_local_profile_menu_and_routing(monkeypatch):
    # An inherited remote setting must not populate this profile's menu.
    monkeypatch.setenv("REMOTE_OLLAMA_BASE_URL", "http://remote.example.invalid:11434")
    monkeypatch.setenv("LLM_DEFAULT_ALIAS", "remote")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    path = Path(__file__).resolve().parents[2] / "models.local.yaml"
    registry = ModelRegistry(yaml.safe_load(path.read_text(encoding="utf-8")))

    assert registry.aliases() == ["default"]
    assert registry.describe_endpoints() == []
    assert registry.describe_providers() == []
    resolved = registry.resolve(None, None)
    assert resolved.model == "ollama/qwen3:8b"
    assert resolved.api_base == "http://host.docker.internal:11434"
    assert resolved.timeout == 600
    assert registry.fallback_chain(resolved) == [resolved]


def test_local_profile_honors_another_installed_qwen(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
    path = Path(__file__).resolve().parents[2] / "models.local.yaml"
    registry = ModelRegistry(yaml.safe_load(path.read_text(encoding="utf-8")))

    assert registry.resolve(None, None).model == "ollama/qwen3:14b"
