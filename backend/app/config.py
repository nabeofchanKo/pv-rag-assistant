from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, case_sensitive=False)

    openai_api_key: str

    # Embedding model (swappable: "openai" now, local e.g. "huggingface" later)
    embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"

    # Chat / generation model (swappable: "openai" now, local e.g. "medllama" later)
    chat_provider: str = "openai"
    openai_chat_model: str = "gpt-4o-mini"

    # Vision model used for image OCR (gpt-4o is stronger on handwriting; mini is cheaper)
    openai_vision_model: str = "gpt-4o"

    # Vector store
    chroma_persist_dir: str = "./chroma_db"
    collection_name: str = "pv_documents"

    # Chunking
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Retrieval
    top_k_retrieval: int = 3


settings = Settings()
