import inspect
import sqlite3
from functools import lru_cache
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app import schemas

from app.config import settings
from app.services.chunking import FixedLengthChunker
from app.services.expectedness import ExpectednessService
from app.services.extraction import ExtractionService
from app.services.generator import GeneratorService
from app.services.label_index import LabelIndexService
from app.services.causality import CausalityService
from app.services.ime import ImeReference
from app.services.meddra import MeddraDictionary
from app.services.meddra_coding import MeddraCodingService
from app.services.meddra_retriever import HybridMeddraRetriever
from app.services.seriousness import SeriousnessService
from app.services.ingestion import (
    EmailLoader,
    ImageLoader,
    IngestionService,
    TextLoader,
)
from app.services.ocr import OcrEngine, VisionLLMOcrEngine
from app.services.pdf_processor import PDFProcessor
from app.services.product_master import ProductMasterService
from app.services.retriever import RetrieverService
from app.services.triage_graph import build_triage_graph


@lru_cache
def get_embeddings() -> Embeddings:
    """Return the embedding model. Swappable via settings.embedding_provider."""
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_chat_model() -> BaseChatModel:
    """Return the chat model. Swappable via settings.chat_provider."""
    return ChatOpenAI(
        model=settings.openai_chat_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_vision_model() -> BaseChatModel:
    """Return the vision-capable model used for image OCR."""
    return ChatOpenAI(
        model=settings.openai_vision_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_ocr_engine() -> OcrEngine:
    """Return the OCR engine. Swappable (Vision LLM now, local later)."""
    return VisionLLMOcrEngine(llm=get_vision_model())


def get_ingestion_service() -> IngestionService:
    """Dispatch PDF / email / text / image inputs to the right loader."""
    return IngestionService(
        loaders=[
            PDFProcessor(),
            EmailLoader(),
            TextLoader(),
            ImageLoader(ocr=get_ocr_engine()),
        ],
    )


def get_chunker() -> FixedLengthChunker:
    return FixedLengthChunker(
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
    )


@lru_cache
def get_retriever_service() -> RetrieverService:
    return RetrieverService(
        embeddings=get_embeddings(),
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.collection_name,
    )


def get_generator_service() -> GeneratorService:
    return GeneratorService(llm=get_chat_model())


@lru_cache
def get_extraction_model() -> BaseChatModel:
    """Model for the reported-events extraction call (swappable via settings)."""
    return ChatOpenAI(
        model=settings.openai_extraction_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_narrative_model() -> BaseChatModel:
    """Model for the narrative-diff call (harder semantic step; swappable)."""
    return ChatOpenAI(
        model=settings.openai_narrative_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_extraction_service() -> ExtractionService:
    """Structured extraction of patient + adverse events from case text."""
    return ExtractionService(
        reported_llm=get_extraction_model(),
        narrative_llm=get_narrative_model(),
    )


@lru_cache
def get_product_master_service() -> ProductMasterService:
    """Own-company product matching (自社品判定) from the YAML master."""
    return ProductMasterService(master_path=settings.product_master_path)


# --- Phase 3: expectedness (既知/未知) over drug labels ---


@lru_cache
def get_label_retriever_service() -> RetrieverService:
    """Retriever over the drug-label collection (separate from case documents)."""
    return RetrieverService(
        embeddings=get_embeddings(),
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.label_collection_name,
    )


def get_label_index_service() -> LabelIndexService:
    """One-time indexer for the drug-label files (run at startup)."""
    return LabelIndexService(
        ingestion=get_ingestion_service(),
        chunker=get_chunker(),
        retriever=get_label_retriever_service(),
        labels_dir=settings.drug_labels_dir,
    )


@lru_cache
def get_expectedness_model() -> BaseChatModel:
    """Model for the grounded 既知/未知 judgment call (swappable via settings)."""
    return ChatOpenAI(
        model=settings.openai_expectedness_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_expectedness_service() -> ExpectednessService:
    """Assess expectedness of adverse events against a drug's package insert."""
    return ExpectednessService(
        llm=get_expectedness_model(),
        retriever=get_label_retriever_service(),
        top_k=settings.label_top_k,
    )


# --- Phase 3: MedDRA PT coding (hybrid retrieval + LLM select) ---


@lru_cache
def get_meddra_dictionary() -> MeddraDictionary:
    """Load the MedDRA PT dictionary (+ build its char-bigram BM25 index)."""
    return MeddraDictionary(csv_path=settings.meddra_path)


@lru_cache
def get_meddra_retriever() -> HybridMeddraRetriever:
    """Hybrid MedDRA retriever (exact + BM25 ⊕ vector, RRF-fused)."""
    return HybridMeddraRetriever(
        dictionary=get_meddra_dictionary(),
        embeddings=get_embeddings(),
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.meddra_collection_name,
    )


@lru_cache
def get_meddra_model() -> BaseChatModel:
    """Model for the MedDRA candidate-selection call (swappable via settings)."""
    return ChatOpenAI(
        model=settings.openai_meddra_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_meddra_coding_service() -> MeddraCodingService:
    """Suggest a MedDRA PT for each adverse-event term."""
    return MeddraCodingService(
        llm=get_meddra_model(),
        retriever=get_meddra_retriever(),
        top_k=settings.meddra_top_k,
    )


# --- Phase 3: seriousness assessment (企業評価 / ICH E2A) ---


@lru_cache
def get_ime_reference() -> ImeReference:
    """PT-keyed important-medical-events list (E2A criterion 6, HITL-appendable)."""
    return ImeReference(csv_path=settings.ime_path)


@lru_cache
def get_seriousness_model() -> BaseChatModel:
    """Model for the E2A criteria interpretation call (swappable via settings)."""
    return ChatOpenAI(
        model=settings.openai_seriousness_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_seriousness_service() -> SeriousnessService:
    """Assess company seriousness (ICH E2A) per adverse event."""
    return SeriousnessService(llm=get_seriousness_model(), ime=get_ime_reference())


# --- Phase 3: causality (temporal, conservative) ---


@lru_cache
def get_causality_model() -> BaseChatModel:
    """Model for the temporal causality call (swappable via settings)."""
    return ChatOpenAI(
        model=settings.openai_causality_model,
        temperature=0.0,
        api_key=settings.openai_api_key,
    )


def get_causality_service() -> CausalityService:
    """Assess temporal causality (conservative) per adverse event."""
    return CausalityService(llm=get_causality_model())


# --- Phase 4a/4b: LangGraph orchestration of the triage pipeline ---


def _schema_serde() -> JsonPlusSerializer:
    """Serializer that explicitly allow-lists our Pydantic schema models.

    The triage state holds Pydantic objects (ProductMatchResult, CaseExtraction,
    the assessments, ReviewOutcome, …). LangGraph will block deserializing
    unregistered types from a checkpoint in a future version, so register every
    model defined in ``app.schemas`` up front (future-proof + silences warnings).
    """
    models = [
        obj
        for _, obj in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == schemas.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=models)


@lru_cache
def get_checkpointer() -> SqliteSaver:
    """Persistent LangGraph checkpointer for the HITL interrupt/resume flow.

    A single SQLite connection (check_same_thread=False so LangGraph's parallel
    fan-out threads may share it; SqliteSaver serializes access with its own
    lock). Persists paused triage drafts across restarts.
    """
    db_path = Path(settings.checkpoint_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn, serde=_schema_serde())
    saver.setup()
    return saver


@lru_cache
def get_triage_graph() -> CompiledStateGraph:
    """Build + compile the triage graph once, wiring the six services together
    plus the SqliteSaver checkpointer (needed for the HITL review interrupt).

    Cached so the graph is compiled a single time and reused across requests.
    """
    return build_triage_graph(
        product_master=get_product_master_service(),
        extraction=get_extraction_service(),
        meddra=get_meddra_coding_service(),
        seriousness=get_seriousness_service(),
        causality=get_causality_service(),
        expectedness=get_expectedness_service(),
        checkpointer=get_checkpointer(),
    )
