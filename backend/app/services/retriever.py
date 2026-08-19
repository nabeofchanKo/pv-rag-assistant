"""Store and retrieve chunks using a LangChain Chroma vector store.

The vector store owns the embed + store + search steps: it is constructed with a
LangChain ``Embeddings`` object (injected via DI), so the embedding model can be
swapped (OpenAI now, a local model later) without touching this service.
"""

import logging
from datetime import datetime

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.schemas import Chunk

logger = logging.getLogger(__name__)


class RetrieverService:
    """Store and search chunk embeddings via a LangChain Chroma vector store."""

    def __init__(
        self,
        embeddings: Embeddings,
        persist_dir: str,
        collection_name: str = "pv_documents",
    ) -> None:
        self.store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Embed and store chunks in the Chroma collection."""

        if not chunks:
            return

        documents, ids = [], []
        for chunk in chunks:
            ids.append(f"{chunk.document_name}_{chunk.chunk_index}")
            documents.append(
                Document(
                    page_content=chunk.text,
                    metadata={
                        "document_name": chunk.document_name,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "total_chunks": chunk.total_chunks,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "language": chunk.language,
                        "created_at": chunk.created_at.isoformat(),
                    },
                )
            )

        self.store.add_documents(documents=documents, ids=ids)
        logger.info("Added %d chunks to collection", len(chunks))

    def search(self, query: str, top_k: int = 3) -> list[Chunk]:
        """Embed the query and return the most similar chunks."""

        results = self.store.similarity_search(query, k=top_k)
        return [self._to_chunk(doc) for doc in results]

    def _to_chunk(self, doc: Document) -> Chunk:
        """Reconstruct the internal Chunk model from a stored Document."""

        metadata = doc.metadata
        return Chunk(
            document_name=metadata["document_name"],
            chunk_index=metadata["chunk_index"],
            page_number=metadata["page_number"],
            total_chunks=metadata["total_chunks"],
            char_start=metadata["char_start"],
            char_end=metadata["char_end"],
            text=doc.page_content,
            language=metadata["language"],
            created_at=datetime.fromisoformat(metadata["created_at"]),
        )
