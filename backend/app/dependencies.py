from functools import lru_cache
import chromadb

from openai import OpenAI
from app.config import settings

from app.services.embedding import EmbeddingService
from app.services.generator import GeneratorService
from app.services.retriever import RetrieverService
from app.services.pdf_processor import PDFProcessor
from app.services.chunking import FixedLengthChunker


@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)

@lru_cache
def get_chroma_client():
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)

def get_pdf_processor() -> PDFProcessor:
    return PDFProcessor()

def get_chunker() -> FixedLengthChunker:
    return FixedLengthChunker(
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
    )

def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(
        client=get_openai_client(),
        model=settings.openai_embedding_model,
    )

def get_retriever_service() -> RetrieverService:
    return RetrieverService(client=get_chroma_client())

def get_generator_service() -> GeneratorService:
    return GeneratorService(
        client=get_openai_client(),
        model=settings.openai_chat_model,
    )