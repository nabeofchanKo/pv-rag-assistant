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
    language: str = "en"
    created_at: datetime