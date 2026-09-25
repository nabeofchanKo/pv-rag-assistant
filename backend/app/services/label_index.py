"""Index drug labels (添付文書) into their own vector collection.

The labels in ``data/drug_labels/`` are the RAG reference source for expectedness
(既知/未知). They are curated and static, so they are indexed once into a
dedicated collection (separate from case documents). Each label's chunks keep
``document_name`` = the file name (e.g. ``drugx_label.md``), which is the same
token stored as ``label_document`` in the product master — so a matched product
can scope the search to exactly its own insert.
"""

import logging
from pathlib import Path

from app.services.chunking import ChunkingStrategy
from app.services.ingestion import IngestionService
from app.services.retriever import RetrieverService

logger = logging.getLogger(__name__)


class LabelIndexService:
    """Load, chunk, and index the drug-label files into the label collection."""

    def __init__(
        self,
        ingestion: IngestionService,
        chunker: ChunkingStrategy,
        retriever: RetrieverService,
        labels_dir: str,
    ) -> None:
        self.ingestion = ingestion
        self.chunker = chunker
        self.retriever = retriever
        self.labels_dir = Path(labels_dir)

    def ensure_indexed(self) -> int:
        """Index all labels if the collection is empty; otherwise do nothing.

        Idempotent: safe to call on every startup. Returns the number of chunks
        added (0 if the collection was already populated).
        """
        if not self.retriever.is_empty():
            logger.info("Drug-label collection already populated; skipping indexing.")
            return 0
        return self.index_all()

    def index_all(self) -> int:
        """(Re)index every ``*.md`` label file. Returns total chunks added."""
        if not self.labels_dir.exists():
            logger.warning("Drug-labels directory not found: %s", self.labels_dir)
            return 0

        total = 0
        for path in sorted(self.labels_dir.glob("*.md")):
            doc = self.ingestion.load(path)
            chunks = self.chunker.chunk_document(doc)
            self.retriever.add_chunks(chunks)
            total += len(chunks)
            logger.info("Indexed label %s (%d chunks)", path.name, len(chunks))

        logger.info("Indexed %d label chunks from %s", total, self.labels_dir)
        return total
