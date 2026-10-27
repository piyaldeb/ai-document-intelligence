"""Local sentence embeddings (BAAI/bge-small-en-v1.5 via fastembed / ONNX Runtime).

Runs on CPU with no external API, so document text never leaves the deployment for
indexing. The model is baked into the Docker image at build time.
"""

from __future__ import annotations

import logging
import threading

from app.config import get_settings

log = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding

            s = get_settings()
            _model = TextEmbedding(model_name=s.embedding_model, cache_dir=s.embedding_cache_dir)
        return _model


def embed_passages(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    return [v.tolist() for v in model.passage_embed(texts, batch_size=batch_size)]


def embed_query(text: str) -> list[float]:
    model = _get_model()
    return next(iter(model.query_embed(text))).tolist()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # Prefer to cut at a line break inside the last third of the window.
            cut = text.rfind("\n", start + size * 2 // 3, end)
            if cut > start:
                end = cut
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
