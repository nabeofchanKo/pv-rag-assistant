import logging
from datetime import datetime

import chromadb

from app.schemas import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


class RetrieverService:
    """Store and retrieve chunk embeddings using ChromaDB."""

    def __init__(self, client, collection_name: str = "pv_documents"):
        self.client = client
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """Store embedded chunks in the ChromaDB collection."""

        if not embedded_chunks:
            return
        
        ids, embeddings, documents, metadatas = [], [], [], []

        for embedded in embedded_chunks:
            chunk = embedded.chunk
            chunk_id = f"{chunk.document_name}_{chunk.chunk_index}"
            embedding = embedded.embedding
            document = chunk.text
            metadata = {
                "document_name": chunk.document_name,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "total_chunks": chunk.total_chunks,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "language": chunk.language,
                "created_at": chunk.created_at.isoformat(),
            }

            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(document)
            metadatas.append(metadata)

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info("Added %d chunks to collection", len(embedded_chunks))

    def search(self, query_embedding: list[float], top_k: int = 3) -> list[Chunk]:
        """Search and retrieve the results from ChromaDB."""

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"]
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        chunks = []

        for document, metadata in zip(documents, metadatas):
            chunk = Chunk(
                document_name=metadata["document_name"],
                chunk_index=metadata["chunk_index"],
                page_number=metadata["page_number"],
                total_chunks=metadata["total_chunks"],
                char_start=metadata["char_start"],
                char_end=metadata["char_end"],
                text=document,
                language=metadata["language"],
                created_at=datetime.fromisoformat(metadata["created_at"]),
            )

            chunks.append(chunk)

        return chunks