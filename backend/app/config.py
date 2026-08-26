from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, case_sensitive=False)

    openai_api_key: str

    # Embedding model (swappable: "openai" now, local "ollama" for on-prem/privacy).
    embedding_provider: str = "openai"          # "openai" | "ollama"
    openai_embedding_model: str = "text-embedding-3-small"  # 1536-dim
    ollama_embedding_model: str = "bge-m3"                  # 1024-dim, multilingual (strong JP)

    # Chat / generation model provider. Phase 5b:
    #   "openai" — every step on OpenAI (default).
    #   "ollama" — every step on the single ollama_chat_model (whole-pipeline-local;
    #              the mode the model-comparison bench drives).
    #   "hybrid" — steps in local_generation_steps run local; the rest run OpenAI.
    # The per-step comparison (ADR 0012) found no local 7-8B preserves 過小0 on the
    # judgment axes, but extraction/coding hold — so hybrid keeps the three judgments
    # (seriousness/causality/expectedness) on OpenAI and moves the rest local.
    chat_provider: str = "openai"          # "openai" | "ollama" | "hybrid"
    openai_chat_model: str = "gpt-4o-mini"
    # Best local generation model per the 5b bench (ELYZA-JP-8B; JP-tuned Llama-3).
    ollama_chat_model: str = "hf.co/elyza/Llama-3-ELYZA-JP-8B-GGUF:latest"
    # Which steps run on the local model when chat_provider="hybrid" (comma-separated).
    # Default = transcription + coding (no clinical judgment); judgments stay on OpenAI.
    local_generation_steps: str = "extraction,narrative,meddra"

    # Local model runtime (Ollama exposes an OpenAI-compatible server + bundles its
    # own CUDA runtime, so no torch install is needed in this venv). Phase 5.
    ollama_base_url: str = "http://localhost:11434"
    # Ollama's default context window is only 2048 tokens — too small for a full ICSR
    # plus our long system prompts, which would be silently truncated. qwen2.5 handles
    # 32k; 8192 comfortably fits a case + prompt without wasting VRAM.
    ollama_num_ctx: int = 8192
    # Cap generation length + request time so a local model can't run away (constrained
    # decoding can loop) or wedge Ollama's request queue. 2048 fits any of our
    # structured outputs; a truncated/failed call surfaces as an error, not a hang.
    ollama_num_predict: int = 2048
    ollama_request_timeout: int = 120

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

    # Phase 4b HITL: LangGraph checkpointer. The triage graph pauses at a human
    # review step (interrupt) and resumes on approval; SqliteSaver persists the
    # paused state across restarts so a review can be resumed later.
    checkpoint_db_path: str = str(PROJECT_ROOT / "backend" / "checkpoints" / "triage.sqlite")

    # Phase 4d: past-case precedent store (structured per-(drug, PT) lookup).
    # Seed = curated tracked examples; runtime = approved cases auto-saved here.
    past_cases_seed_dir: str = str(PROJECT_ROOT / "data" / "past_cases")
    past_cases_runtime_dir: str = str(PROJECT_ROOT / "backend" / "past_cases")

    # Chunking
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Retrieval
    top_k_retrieval: int = 3

    # --- Phase 5: embedding-provider-scoped vector store ---
    # Different embedding models produce different-dimensioned vectors (OpenAI 1536,
    # BGE-M3 1024), so a Chroma collection is bound to one model. Scope the persist
    # dir by embedding id so providers coexist on disk and the A/B is a flag flip;
    # the startup lifespan re-indexes the reference collections into an empty dir.
    @property
    def embedding_id(self) -> str:
        """Filesystem-safe id for the active embedding model (provider + name)."""
        name = (
            self.openai_embedding_model
            if self.embedding_provider == "openai"
            else self.ollama_embedding_model
        )
        slug = f"{self.embedding_provider}__{name}"
        return slug.replace(":", "-").replace("/", "-")

    @property
    def chroma_dir(self) -> str:
        """Provider-scoped persist dir, e.g. ./chroma_db/openai__text-embedding-3-small."""
        return str(Path(self.chroma_persist_dir) / self.embedding_id)

    @property
    def local_steps(self) -> set[str]:
        """Step names that run on the local model in hybrid mode (parsed set)."""
        return {s.strip() for s in self.local_generation_steps.split(",") if s.strip()}


settings = Settings()
