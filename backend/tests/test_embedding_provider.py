"""Phase 5a: embedding-provider switch wiring.

Locks the behaviour of the ``get_embeddings`` factory + the provider-scoped Chroma
dir. No network: both LangChain embedding classes construct lazily (they only reach
their backend on the first embed call), so we can assert the *type* the factory
returns for each provider without a live OpenAI key or a running Ollama.
"""

import pytest
from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app import dependencies


@pytest.fixture(autouse=True)
def _clear_embeddings_cache():
    """get_embeddings is lru_cached; clear it around each test so the provider
    monkeypatch actually takes effect."""
    dependencies.get_embeddings.cache_clear()
    yield
    dependencies.get_embeddings.cache_clear()


def test_openai_provider_returns_openai_embeddings(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "embedding_provider", "openai")
    emb = dependencies.get_embeddings()
    assert isinstance(emb, OpenAIEmbeddings)


def test_ollama_provider_returns_ollama_embeddings(monkeypatch):
    from langchain_ollama import OllamaEmbeddings

    monkeypatch.setattr(dependencies.settings, "embedding_provider", "ollama")
    monkeypatch.setattr(dependencies.settings, "ollama_embedding_model", "bge-m3")
    emb = dependencies.get_embeddings()
    assert isinstance(emb, OllamaEmbeddings)
    assert emb.model == "bge-m3"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "embedding_provider", "nope")
    with pytest.raises(ValueError, match="Unknown embedding_provider"):
        dependencies.get_embeddings()


def test_chroma_dir_is_scoped_by_embedding_id():
    """Different embedding models must not share a Chroma dir (different dims)."""
    openai = Settings(
        openai_api_key="x", embedding_provider="openai",
        chroma_persist_dir="./chroma_db",
    )
    ollama = Settings(
        openai_api_key="x", embedding_provider="ollama",
        ollama_embedding_model="bge-m3", chroma_persist_dir="./chroma_db",
    )
    assert openai.embedding_id == "openai__text-embedding-3-small"
    assert ollama.embedding_id == "ollama__bge-m3"
    assert openai.chroma_dir != ollama.chroma_dir
    # A model name with a ':' tag (e.g. bge-m3:latest) stays filesystem-safe.
    tagged = Settings(
        openai_api_key="x", embedding_provider="ollama",
        ollama_embedding_model="ruri:latest", chroma_persist_dir="./chroma_db",
    )
    assert ":" not in tagged.embedding_id
