"""Define domain models for the PDF processing service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

class PageContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int
    text: str
    char_count: int
    extraction_method: str = "text"


class ProcessedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_name: str
    page_count: int
    pages: list[PageContent]
    processed_at: datetime

    @property
    def full_text(self) -> str:
        """Concatenate all page texts and return as a single string."""
        return "\n\n".join(page.text for page in self.pages)


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_name: str
    chunk_index: int
    page_number: int
    total_chunks: int
    char_start: int
    char_end: int
    text: str
    created_at: datetime
    language: str = "en"


class EmbeddedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    embedding: list[float]


class RAGResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    source_chunks: list[Chunk]
    query: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3


class SourceInfo(BaseModel):
    document_name: str
    page_number: int
    chunk_index: int
    text: str


class QueryResponse(BaseModel):
    answer: str
    query: str
    sources: list[SourceInfo]


class UploadResponse(BaseModel):
    document_name: str
    chunks_added: int
    message: str