"""Test configuration.

Tests run inside the backend container against a dedicated `docintel_test` database.
Background jobs run synchronously (the Celery enqueue function is replaced by a direct
call into the pipeline), so API tests exercise the full processing path end to end.
"""

from __future__ import annotations

import os
import tempfile

_storage = tempfile.mkdtemp(prefix="docintel-test-")
_db = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://docintel:docintel@db:5432/docintel"
).rsplit("/", 1)[0] + "/docintel_test"
os.environ.update({
    "DATABASE_URL": _db,
    "STORAGE_DIR": _storage,
    "API_KEYS": "test-key",
    "EXTRACTION_PROVIDER": "rules",
    "ANTHROPIC_API_KEY": "",
    "RATE_LIMIT_PER_MINUTE": "0",
    "OCR_WORKERS": "2",
})

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import engine  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def clean_db():
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE reconciliation_items, reconciliations, chunks, corrections, processing_events, "
            "validation_issues, line_items, invoices, document_pages, documents CASCADE"
        ))
    yield


@pytest.fixture()
def client(clean_db, monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.documents as documents_api
    from app.main import app
    from app.pipeline.processor import run

    monkeypatch.setattr(documents_api, "enqueue", lambda doc_id: run(doc_id))
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        yield c


@pytest.fixture()
def samples(tmp_path):
    from tests import factories

    return factories.Samples(tmp_path)
