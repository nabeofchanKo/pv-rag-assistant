from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings
from app.services.chunking import FixedLengthChunker
from app.services.generator import GeneratorService
from app.services.pdf_processor import PDFProcessor
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


def get_pdf_processor() -> PDFProcessor:
    return PDFProcessor()


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
