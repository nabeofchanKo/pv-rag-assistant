"""Hybrid MedDRA PT retriever (ADR 0003, Level B).

Fuses the lexical signal (exact match + char-bigram BM25, from ``MeddraDictionary``)
with a dense-vector signal (a ``meddra_pt`` Chroma collection over the Japanese PT
names) via Reciprocal Rank Fusion. Exact matches are prepended (the deterministic
fast path); the rest is the RRF of BM25 and vector rankings.
"""

import logging

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma

from app.schemas import MeddraTerm
from app.services.meddra import MeddraDictionary, rrf_fuse

logger = logging.getLogger(__name__)


class HybridMeddraRetriever:
    """Return candidate PTs for an adverse-event term via lexical+vector fusion."""

    def __init__(
        self,
        dictionary: MeddraDictionary,
        embeddings: Embeddings,
        persist_dir: str,
        collection_name: str = "meddra_pt",
        vector_pool: int = 15,
    ) -> None:
        self.dic = dictionary
        self.vector_pool = vector_pool
        self._index_by_code = {t.pt_code: i for i, t in enumerate(dictionary.terms)}
        self.store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def ensure_indexed(self) -> int:
        """Embed the PT names into the collection once (idempotent). Returns count added."""
        if len(self.store.get(limit=1)["ids"]) > 0:
            return 0
        docs = [
            Document(page_content=t.pt_name_ja, metadata={"pt_code": t.pt_code})
            for t in self.dic.terms
        ]
        self.store.add_documents(docs, ids=[t.pt_code for t in self.dic.terms])
        logger.info("Indexed %d MedDRA PTs", len(docs))
        return len(docs)

    def _vector_rank(self, term: str) -> list[int]:
        results = self.store.similarity_search(term, k=self.vector_pool)
        ranked = []
        for doc in results:
            i = self._index_by_code.get(doc.metadata.get("pt_code"))
            if i is not None:
                ranked.append(i)
        return ranked

    def exact_matches(self, term: str) -> list[MeddraTerm]:
        return [self.dic.terms[i] for i in self.dic.exact_matches(term)]

    def search(self, term: str, top_k: int = 5) -> list[MeddraTerm]:
        """Top-k candidate PTs: exact matches first, then BM25⊕vector fused by RRF."""
        exact = self.dic.exact_matches(term)
        fused = rrf_fuse([self.dic.bm25_rank(term), self._vector_rank(term)])
        order: list[int] = []
        for i in [*exact, *fused]:
            if i not in order:
                order.append(i)
        return [self.dic.terms[i] for i in order[:top_k]]
