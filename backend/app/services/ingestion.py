"""Ingestion layer: turn any supported input file into a ProcessedDocument.

Each input type has a ``DocumentLoader``; ``IngestionService`` dispatches by file
suffix. Everything downstream (chunk -> embed -> store -> retrieve -> generate)
only ever sees a ``ProcessedDocument``, so new input types can be added here
without touching the rest of the pipeline.
"""

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import ClassVar

from app.exceptions import UnsupportedFileTypeError
from app.schemas import PageContent, ProcessedDocument

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """NFKC-normalize, collapse 3+ blank lines, strip. Shared by all loaders."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _single_page_document(
    document_name: str, text: str, extraction_method: str
) -> ProcessedDocument:
    """Wrap a single block of text as a one-page ProcessedDocument."""
    page = PageContent(
        page_number=1,
        text=text,
        char_count=len(text),
        extraction_method=extraction_method,
    )
    return ProcessedDocument(
        document_name=document_name,
        page_count=1,
        pages=[page],
        processed_at=datetime.now(timezone.utc),
    )


class DocumentLoader(ABC):
    """Read one input file into a ProcessedDocument."""

    # File suffixes (lower-case, with dot) this loader handles, e.g. {".pdf"}.
    supported_suffixes: ClassVar[set[str]]

    @abstractmethod
    def load(self, path: Path) -> ProcessedDocument:
        """Read ``path`` and return a ProcessedDocument."""
        ...


class TextLoader(DocumentLoader):
    """Load plain-text (or email-format text) files as a single page."""

    supported_suffixes: ClassVar[set[str]] = {".txt", ".md"}

    def __init__(self, normalize: bool = True) -> None:
        self.normalize = normalize

    def load(self, path: Path) -> ProcessedDocument:
        if not path.exists():
            raise FileNotFoundError("File could not be found.")

        text = path.read_text(encoding="utf-8")
        if self.normalize:
            text = normalize_text(text)
        return _single_page_document(path.name, text, extraction_method="text")


class EmailLoader(DocumentLoader):
    """Load an email (.eml): key headers + body become searchable text (one page)."""

    supported_suffixes: ClassVar[set[str]] = {".eml"}

    # (header key, Japanese label) surfaced into the searchable text.
    _HEADER_LABELS: ClassVar[list[tuple[str, str]]] = [
        ("From", "差出人"),
        ("To", "宛先"),
        ("Date", "日付"),
        ("Subject", "件名"),
    ]

    def __init__(self, normalize: bool = True) -> None:
        self.normalize = normalize

    def load(self, path: Path) -> ProcessedDocument:
        if not path.exists():
            raise FileNotFoundError("File could not be found.")

        with path.open("rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        header_lines = [
            f"{label}（{key}）: {value}"
            for key, label in self._HEADER_LABELS
            if (value := msg.get(key))
        ]
        body = self._extract_body(msg)

        text = "\n".join(header_lines)
        text = f"{text}\n\n{body}" if (text and body) else (text or body)
        if self.normalize:
            text = normalize_text(text)
        return _single_page_document(path.name, text, extraction_method="email")

    def _extract_body(self, msg: EmailMessage) -> str:
        """Prefer the plain-text part; fall back to a naive HTML strip."""
        part = msg.get_body(preferencelist=("plain",))
        if part is not None:
            return part.get_content()

        part = msg.get_body(preferencelist=("html",))
        if part is not None:
            return re.sub(r"<[^>]+>", "", part.get_content())

        return ""


class IngestionService:
    """Dispatch an input file to the loader that supports its suffix."""

    def __init__(self, loaders: list[DocumentLoader]) -> None:
        self._by_suffix: dict[str, DocumentLoader] = {}
        for loader in loaders:
            for suffix in loader.supported_suffixes:
                self._by_suffix[suffix.lower()] = loader

    @property
    def supported_suffixes(self) -> set[str]:
        return set(self._by_suffix)

    def load(self, path: Path) -> ProcessedDocument:
        suffix = path.suffix.lower()
        loader = self._by_suffix.get(suffix)
        if loader is None:
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{suffix}'. "
                f"Supported: {sorted(self.supported_suffixes)}"
            )
        logger.info("Ingesting %s via %s", path.name, type(loader).__name__)
        return loader.load(path)
