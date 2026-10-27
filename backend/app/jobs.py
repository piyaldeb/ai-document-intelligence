"""Job dispatch: background queue (Celery) or inline execution (serverless)."""

from __future__ import annotations

import threading
import uuid

from app.config import get_settings

# Inline mode runs on small instances: process one document at a time per instance so that
# concurrent uploads queue instead of multiplying peak memory.
_inline_slot = threading.Semaphore(1)


def enqueue(document_id: uuid.UUID) -> None:
    if get_settings().processing_mode == "inline":
        from app.pipeline.processor import run

        with _inline_slot:
            run(document_id)
    else:
        from app.worker.celery_app import enqueue as celery_enqueue

        celery_enqueue(document_id)


def enqueue_index(document_id: uuid.UUID) -> None:
    if get_settings().processing_mode == "inline":
        from app.pipeline.processor import index_document

        index_document(document_id)  # called from run(), already inside the processing slot
    else:
        from app.worker.celery_app import enqueue_index as celery_enqueue_index

        celery_enqueue_index(document_id)
