"""Phase 5b: chat/generation provider switch wiring.

Locks build_chat_model + the per-step factories. No network: ChatOpenAI and
ChatOllama both construct lazily (they only reach their backend on first invoke),
so we assert the type/config the factory returns per provider without a live key
or a running Ollama.
"""

import pytest
from langchain_openai import ChatOpenAI

from app import dependencies


def test_openai_provider_builds_chatopenai_with_step_model(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "chat_provider", "openai")
    llm = dependencies.build_chat_model("gpt-4o")
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "gpt-4o"


def test_ollama_provider_ignores_step_model_uses_single_local(monkeypatch):
    from langchain_ollama import ChatOllama

    monkeypatch.setattr(dependencies.settings, "chat_provider", "ollama")
    monkeypatch.setattr(dependencies.settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(dependencies.settings, "ollama_num_ctx", 8192)
    # A different per-step OpenAI name is passed, but ollama uses the single local model.
    llm = dependencies.build_chat_model("gpt-4o")
    assert isinstance(llm, ChatOllama)
    assert llm.model == "qwen2.5:7b"
    assert llm.num_ctx == 8192


def test_unknown_chat_provider_raises(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "chat_provider", "nope")
    with pytest.raises(ValueError, match="Unknown chat_provider"):
        dependencies.build_chat_model("gpt-4o")


def test_per_step_factory_follows_provider(monkeypatch):
    """A per-step factory (seriousness) must route through the provider switch."""
    from langchain_ollama import ChatOllama

    monkeypatch.setattr(dependencies.settings, "chat_provider", "ollama")
    monkeypatch.setattr(dependencies.settings, "ollama_chat_model", "qwen2.5:7b")
    dependencies.get_seriousness_model.cache_clear()
    try:
        assert isinstance(dependencies.get_seriousness_model(), ChatOllama)
    finally:
        dependencies.get_seriousness_model.cache_clear()


def test_hybrid_routes_only_local_steps_to_ollama(monkeypatch):
    """hybrid: steps in local_generation_steps go local, judgments stay on OpenAI."""
    from langchain_ollama import ChatOllama

    monkeypatch.setattr(dependencies.settings, "chat_provider", "hybrid")
    monkeypatch.setattr(dependencies.settings, "local_generation_steps", "extraction,narrative,meddra")
    # transcription/coding -> local
    assert isinstance(dependencies.build_chat_model("gpt-4o-mini", step="extraction"), ChatOllama)
    assert isinstance(dependencies.build_chat_model("gpt-4o-mini", step="meddra"), ChatOllama)
    # the three clinical judgments -> OpenAI with their own per-step model
    ser = dependencies.build_chat_model("gpt-4o", step="seriousness")
    assert isinstance(ser, ChatOpenAI) and ser.model_name == "gpt-4o"
    assert isinstance(dependencies.build_chat_model("gpt-4o", step="causality"), ChatOpenAI)
    assert isinstance(dependencies.build_chat_model("gpt-4o-mini", step="expectedness"), ChatOpenAI)
    # a step with no name (or 'chat') is never local
    assert isinstance(dependencies.build_chat_model("gpt-4o-mini", step="chat"), ChatOpenAI)
