"""JPG / PNG / TIFF (incl. multi-page TIFF) OCR."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFile, ImageSequence, UnidentifiedImageError

from app.config import get_settings
from app.pipeline.errors import CorruptedFile, TooLarge
from app.pipeline.ocr import ocr_image
from app.pipeline.types import PageResult, ProgressFn, TextExtraction

MAX_FRAMES = 500


def _load_frames(path: Path) -> tuple[list[Image.Image], list[str]]:
    warnings: list[str] = []
    try:
        with Image.open(path) as img:
            frames = [f.copy() for _, f in zip(range(MAX_FRAMES), ImageSequence.Iterator(img))]
            for f in frames:
                f.load()
        return frames, warnings
    except Image.DecompressionBombError as exc:
        raise TooLarge(f"Image is too large: {exc}") from exc
    except UnidentifiedImageError as exc:
        raise CorruptedFile(f"Image could not be decoded: {exc}") from exc
    except OSError:
        pass  # typically a truncated file; try to salvage the readable part below

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        with Image.open(path) as img:
            img.load()
            frames = [img.copy()]
        warnings.append("image file is truncated; recovered the readable part")
        return frames, warnings
    except Exception as exc:
        raise CorruptedFile(f"Image is corrupted and could not be recovered: {exc}") from exc
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = False


def extract_image(path: Path, progress: ProgressFn | None = None) -> TextExtraction:
    frames, warnings = _load_frames(path)
    total = len(frames)
    pages: list[PageResult] = []
    with ThreadPoolExecutor(max_workers=get_settings().ocr_workers) as pool:
        for i, r in enumerate(pool.map(ocr_image, frames)):
            pages.append(PageResult(i + 1, r.text, "ocr", r.confidence, warnings=warnings + r.warnings))
            if progress:
                progress(i + 1, total)
    return TextExtraction(pages=pages, warnings=list(warnings), meta={"page_count": total, "ocr_pages": total})
