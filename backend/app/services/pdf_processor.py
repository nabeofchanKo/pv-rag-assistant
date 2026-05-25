"""Extract texts from PDFs"""

import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pdfplumber

from app.exceptions import (
    PDFCorruptedError,
    PDFEncryptedError,
)
from app.schemas import PageContent, ProcessedDocument

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Processor to extract texts from PDFs"""

    def __init__(
            self,
            extraction_mode: Literal["text"] = "text",
            normalize: bool = True,
    ) -> None:
        self.extraction_mode = extraction_mode
        self.normalize = normalize

    def process(self, pdf_path: Path) -> ProcessedDocument:
        """Process PDF"""
        if not pdf_path.exists():
            raise FileNotFoundError("File could not be found.")
        
        pages = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    text = self._extract_page_text(page)
                    if not text:
                        logger.warning(logger.warning("Empty page detected: %s page %d", pdf_path.name, index))
                    pages.append(PageContent(page_number=index, text=text, char_count=len(text), extraction_method=self.extraction_mode))

        except FileNotFoundError:
            raise
        
        except Exception as e:
            error_message = str(e).lower()
            if "password" in error_message or "excrypted" in error_message:
                raise PDFEncryptedError("PDF is excrypted.") from e
            else:
                raise PDFCorruptedError("PDF is corrupted.") from e

        return ProcessedDocument(
            document_name=pdf_path.name,
            page_count=len(pages),
            pages=pages,
            processed_at=datetime.now(timezone.utc)
        )
    
    def _extract_page_text(self, page: pdfplumber.page.Page) -> str:
        """Extract 1 page text, and normalize if needed."""
        text = page.extract_text(layout=False) or ""
        if self.normalize:
            text = self._normalize_text(text)
        return text

    def _normalize_text(self, text: str) -> str:
        """Normalize texts (NKFC, linebreak compression, strip)."""
        normalized = unicodedata.normalize("NFKC", text)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = normalized.strip()
        return normalized