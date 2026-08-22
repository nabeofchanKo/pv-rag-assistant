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

    # Drug labels (添付文書) — separate collection, RAG source for expectedness (既知/未知).
    drug_labels_dir: str = str(PROJECT_ROOT / "data" / "drug_labels")
    label_collection_name: str = "drug_labels"
    label_top_k: int = 4

    # Expectedness judgment model (grounded 既知/未知 call; swappable per step).
    openai_expectedness_model: str = "gpt-4o-mini"

    # MedDRA PT coding (hybrid retrieval: char-bigram BM25 + vector, RRF-fused).
    meddra_path: str = str(PROJECT_ROOT / "data" / "meddra_sample" / "meddra_pt.csv")
    meddra_collection_name: str = "meddra_pt"
    meddra_top_k: int = 5
    openai_meddra_model: str = "gpt-4o-mini"

    # Seriousness assessment (企業評価 / ICH E2A). IME = PT-keyed medically-important
    # events list, used for criterion 6; HITL-appendable.
    ime_path: str = str(PROJECT_ROOT / "data" / "reference" / "ime_pt.csv")
    # Seriousness needs careful narrative attribution (which event caused the
    # hospitalization?) — the same hard-narrative class where mini leaked in
    # extraction, so this step defaults to gpt-4o (per-step model selection).
    openai_seriousness_model: str = "gpt-4o"

    # Causality (temporal) also needs date/narrative reasoning (onset vs
    # administration) — gpt-4o for the same reason.
    openai_causality_model: str = "gpt-4o"

    # Chunking
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Retrieval
    top_k_retrieval: int = 3


settings = Settings()
