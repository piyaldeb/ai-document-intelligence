"""Typed processing errors. `retryable` errors are retried by the worker with backoff;
the rest fail the job immediately with a stable `code` that the UI/API can show."""

from __future__ import annotations


class ProcessingError(Exception):
    code = "PROCESSING_ERROR"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        if code:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class UnsupportedFileType(ProcessingError):
    code = "UNSUPPORTED_FILE_TYPE"


class CorruptedFile(ProcessingError):
    code = "CORRUPTED_FILE"


class EncryptedFile(ProcessingError):
    code = "ENCRYPTED_FILE"


class EmptyDocument(ProcessingError):
    code = "EMPTY_DOCUMENT"


class TooLarge(ProcessingError):
    code = "DOCUMENT_TOO_LARGE"


class TransientError(ProcessingError):
    code = "TRANSIENT_ERROR"
    retryable = True
