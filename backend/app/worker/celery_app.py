from __future__ import annotations

import logging
import uuid

from celery import Celery
from celery.signals import worker_process_init

from app.config import get_settings

settings = get_settings()

celery_app = Celery("docintel", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,  # a crashed worker's job is redelivered, not lost
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long OCR jobs: don't hoard tasks on one worker
    task_default_queue="documents",
    task_time_limit=60 * 60 * 3,
    task_soft_time_limit=60 * 60 * 3 - 60,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
)

log = logging.getLogger(__name__)


@worker_process_init.connect
def _warm_up(**_kwargs) -> None:
    """Load the embedding model once per worker process instead of on the first document."""
    if settings.embeddings_enabled:
        try:
            from app.search.embeddings import embed_passages

            embed_passages(["warm-up"])
        except Exception:  # never block worker start-up; indexing will retry lazily
            log.exception("embedding model warm-up failed")


@celery_app.task(bind=True, name="process_document", max_retries=3)
def process_document(self, document_id: str) -> str:
    from app.pipeline.errors import ProcessingError
    from app.pipeline.processor import run

    try:
        return run(uuid.UUID(document_id))
    except ProcessingError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(300, 15 * 2 ** self.request.retries)) from exc
        raise


def enqueue(document_id: uuid.UUID) -> None:
    process_document.delay(str(document_id))
