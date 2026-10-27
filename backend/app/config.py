"""Application settings, loaded from environment variables (12-factor)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- infrastructure ---
    database_url: str = "postgresql+psycopg://docintel:docintel@db:5432/docintel"
    redis_url: str = "redis://redis:6379/0"
    storage_dir: Path = Path("/data/uploads")

    # --- security ---
    # Comma-separated list of accepted API keys. Empty = auth disabled (local dev only).
    api_keys: str = ""
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 100
    max_files_per_request: int = 50
    rate_limit_per_minute: int = 600

    # --- processing ---
    max_pdf_pages: int = 5000
    ocr_dpi: int = 300
    ocr_workers: int = Field(default_factory=lambda: max(1, (os.cpu_count() or 2) - 1))
    max_ocr_pages: int = 0  # 0 = unlimited; small hosts cap OCR work per document
    ocr_page_timeout_s: int = 90
    ocr_languages: str = "eng"
    min_text_chars_per_page: int = 25  # below this a PDF page is treated as scanned
    low_ocr_confidence: float = 60.0
    max_sheet_rows: int = 200_000

    # --- AI extraction ---
    # "auto" -> Claude if ANTHROPIC_API_KEY is set, otherwise the deterministic rules extractor.
    extraction_provider: str = "auto"  # auto | anthropic | rules
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"
    llm_max_concurrency: int = 4
    llm_timeout_s: float = 120.0
    llm_max_input_chars: int = 120_000
    llm_server_fallbacks: bool = True

    # --- semantic search ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_cache_dir: str = "/models"
    embeddings_enabled: bool = True
    chunk_chars: int = 1500  # ~350 tokens, within bge-small's 512-token window
    chunk_overlap: int = 200

    # --- deployment shape ---
    # queue: Celery workers process documents in the background (docker-compose, Kubernetes, ...)
    # inline: process inside the upload request (serverless, e.g. Vercel Functions; no worker/Redis)
    processing_mode: str = "queue"
    # local: shared volume (STORAGE_DIR) | db: file bytes in Postgres (stateless serverless instances)
    storage_backend: str = "local"
    cron_secret: str = ""  # Vercel Cron sends "Authorization: Bearer <CRON_SECRET>"
    demo_samples_dir: Path = Path("/app/demo_samples")

    # --- public demo ---
    demo_mode: bool = False  # shows a "public demo" banner in the UI
    demo_reset_hours: int = 24
    demo_max_documents: int = 250  # public demo: cap stored documents (disk protection)
    demo_seed_budget_s: float = 900.0
    demo_seed_set: str = "full"  # full | light (skips the slowest OCR samples on tiny CPUs)

    # --- validation ---
    amount_tolerance_abs: float = 0.02
    amount_tolerance_rel: float = 0.001
    low_field_confidence: float = 0.6

    @field_validator("database_url")
    @classmethod
    def _sqlalchemy_url(cls, v: str) -> str:
        # Managed Postgres providers (Neon, Supabase, Heroku) hand out postgres:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_provider(self) -> str:
        if self.extraction_provider != "auto":
            return self.extraction_provider
        return "anthropic" if self.anthropic_api_key else "rules"


@lru_cache
def get_settings() -> Settings:
    return Settings()
