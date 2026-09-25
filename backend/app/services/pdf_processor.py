"""Extract text from PDFs (the DocumentLoader for .pdf files)."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal

import pdfplumber

from app.exceptions import (
    PDFCorruptedError,
    PDFEncryptedError,
)
from app.schemas import PageContent, ProcessedDocument
from app.services.ingestion import DocumentLoader, normalize_text

logger = logging.getLogger(__name__)


class PDFProcessor(DocumentLoader):
    """Loader that extracts text from PDF files (kept custom for NFKC normalization)."""

    supported_suffixes: ClassVar[set[str]] = {".pdf"}

    def __init__(
            self,
            extraction_mode: Literal["text"] = "text",
            normalize: bool = True,
    ) -> None:
        self.extraction_mode = extraction_mode
        self.normalize = normalize

    def load(self, pdf_path: Path) -> ProcessedDocument:
        """Extract text from a PDF, one PageContent per page."""
        if not pdf_path.exists():
            raise FileNotFoundError("File could not be found.")

        pages = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    text = self._extract_page_text(page)
                    if not text:
                        logger.warning("Empty page detected: %s page %d", pdf_path.name, index)
                    pages.append(PageContent(page_number=index, text=text, char_count=len(text), extraction_method=self.extraction_mode))

        except FileNotFoundError:
            raise

        except Exception as e:
            error_message = str(e).lower()
            if "password" in error_message or "encrypted" in error_message:
                raise PDFEncryptedError("PDF is encrypted.") from e
            else:
                raise PDFCorruptedError("PDF is corrupted.") from e

        return ProcessedDocument(
            document_name=pdf_path.name,
            page_count=len(pages),
            pages=pages,
            processed_at=datetime.now(timezone.utc)
        )

    def _extract_page_text(self, page: pdfplumber.page.Page) -> str:
        """Extract one page's text, normalizing if enabled."""
        text = page.extract_text(layout=False) or ""
        if self.normalize:
            text = normalize_text(text)
        return text
