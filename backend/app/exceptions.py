class PDFProcessingError(Exception):
    """Base class for PDF-related errors."""
    pass

class PDFCorruptedError(PDFProcessingError):
    """Error when PDF is corrupted and cannot be opened."""
    pass

class PDFEncryptedError(PDFProcessingError):
    """Error when PDF is encrypted with password."""
    pass