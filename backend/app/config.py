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

    # Extraction is a two-call decomposition (see ExtractionService).
    # - reported-events call: simple structured extraction -> mini is enough.
    # - narrative-diff call: must de-duplicate rephrasings, respect negation, and
    #   not infer. Evaluated result: mini leaks ~1 false event/case here, gpt-4o is
    #   clean -> use gpt-4o for this step only (per-step model selection).
    openai_extraction_model: str = "gpt-4o-mini"   # reported-events call
    openai_narrative_model: str = "gpt-4o"          # narrative-diff call

    # Vector store
    chroma_persist_dir: str = "./chroma_db"
    collection_name: str = "pv_documents"

    # Own-company product master (used for company-product matching / 自社品判定)
    product_master_path: str = str(PROJECT_ROOT / "data" / "product_master" / "products.yaml")

    # Chunking
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Retrieval
    top_k_retrieval: int = 3


settings = Settings()
