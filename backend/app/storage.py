"""Local file storage for uploads (a shared volume between API and workers).

Files are stored under random UUID names in a two-level fan-out directory, never under
the client-supplied filename, which is only kept as metadata.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

CHUNK = 1024 * 1024


class UploadTooLarge(Exception):
    pass


def save_stream(stream: BinaryIO, max_bytes: int, suffix: str) -> tuple[Path, int, str, bytes]:
    """Stream an upload to disk while hashing it. Returns (path, size, sha256, first 8 KiB)."""
    root = get_settings().storage_dir
    name = uuid.uuid4().hex
    directory = root / name[:2]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}{suffix}"
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with open(path, "wb") as out:
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                size += len(block)
                if size > max_bytes:
                    raise UploadTooLarge(f"file exceeds {max_bytes // (1024 * 1024)} MB")
                if len(head) < 8192:
                    head += block[: 8192 - len(head)]
                digest.update(block)
                out.write(block)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o640)
    return path, size, digest.hexdigest(), head


def delete_file(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
