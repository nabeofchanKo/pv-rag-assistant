"""Split texts into chunks.

The chunking *strategy* is kept behind an interface (portfolio design choice),
but the token-window mechanics are delegated to LangChain's ``TokenTextSplitter``
instead of being hand-rolled, so alternative LangChain splitters can be swapped in.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from langchain_text_splitters import TokenTextSplitter

from app.schemas import Chunk, ProcessedDocument

logger = logging.getLogger(__name__)


class ChunkingStrategy(ABC):
    """Base class for chunking strategy."""

    @abstractmethod
    def chunk_document(self, document: ProcessedDocument) -> list[Chunk]:
        """Split a document's text into chunks.

        Args:
            document: The processed document to chunk.

        Returns:
            List of chunks generated from the document.
        """
        ...


class FixedLengthChunker(ChunkingStrategy):
    """Fixed-length token-based chunking strategy with overlap (LangChain-backed)."""

    def __init__(
            self,
            chunk_size: int = 500,
            overlap: int = 100,
            encoding_name: str = "cl100k_base"
            ):
        if overlap >= chunk_size:
            raise ValueError(f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size}).")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.splitter = TokenTextSplitter(
            encoding_name=encoding_name,
            chunk_size=chunk_size,
            chunk_overlap=overlap,
        )

    def chunk_document(self, document: ProcessedDocument) -> list[Chunk]:
        chunks = []

        for page in document.pages:
            page_chunks = self._chunk_page(
                page_text=page.text,
                page_number=page.page_number,
                document_name=document.document_name,
                chunk_index_start=len(chunks),
            )
            chunks.extend(page_chunks)

        total_chunks = len(chunks)

        final_chunks = []
        for chunk in chunks:
            final_chunk = chunk.model_copy(update={"total_chunks": total_chunks})
            final_chunks.append(final_chunk)

        return final_chunks

    def _chunk_page(
            self,
            page_text: str,
            page_number: int,
            document_name: str,
            chunk_index_start: int,
    ) -> list[Chunk]:
        if not page_text:
            return []

        # LangChain handles the token windowing (encode -> slide -> decode).
        texts = self.splitter.split_text(page_text)

        chunks = []
        search_start = 0

        for chunk_position, chunk_text in enumerate(texts):
            char_start = page_text.find(chunk_text, search_start)
            if char_start == -1:
                logger.warning(
                    "Chunk text not found in page text: document=%s, page=%d",
                    document_name,
                    page_number,
                )
                char_end = -1
            else:
                char_end = char_start + len(chunk_text)

            chunk = Chunk(
                document_name=document_name,
                chunk_index=chunk_index_start + chunk_position,
                page_number=page_number,
                total_chunks=0,
                char_start=char_start,
                char_end=char_end,
                text=chunk_text,
                created_at=datetime.now(timezone.utc),
            )
            chunks.append(chunk)
            if char_start != -1:
                search_start = char_start + 1

        return chunks
