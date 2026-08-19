class IngestionError(Exception):
    """Base class for document-ingestion errors."""
    pass


class UnsupportedFileTypeError(IngestionError):
    """Error when no registered loader supports the file's type."""
    pass


class PDFProcessingError(IngestionError):
    """Base class for PDF-related errors."""
    pass


class PDFCorruptedError(PDFProcessingError):
    """Error when PDF is corrupted and cannot be opened."""
    pass


class PDFEncryptedError(PDFProcessingError):
    """Error when PDF is encrypted with password."""
    pass
