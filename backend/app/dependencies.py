from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings
from app.services.chunking import FixedLengthChunker
from app.services.extraction import ExtractionService
from app.services.generator import GeneratorService
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
