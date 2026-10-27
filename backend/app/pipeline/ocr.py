"""OCR for scanned pages and photos: image clean-up + Tesseract with confidence-based
strategy selection.

Poor-quality input (low contrast, noise, skew, small/low-DPI images, rotated scans) is
handled by trying a cheap "basic" pass first and escalating to an "enhanced" pass
(deskew + denoise + CLAHE + binarisation) and finally an orientation-corrected pass only
when the previous result is weak. The pass with the most confidently-recognised text wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from app.config import get_settings
from app.pipeline.layout import words_to_text

log = logging.getLogger(__name__)

Image.MAX_IMAGE_PIXELS = 250_000_000  # decompression-bomb guard (PIL raises above this)

TARGET_MIN_WIDTH = 1700  # px; ~A4 at 200 DPI. Smaller images are upscaled.
TARGET_MAX_WIDTH = 3600
GOOD_CONFIDENCE = 78.0


@dataclass
class OcrResult:
    text: str
    confidence: float  # mean word confidence 0..100
    strategy: str
    word_count: int
    warnings: list[str] = field(default_factory=list)


def _to_gray(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    arr = np.asarray(img)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr


def _rescale(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    if w < TARGET_MIN_WIDTH:
        f = min(3.0, TARGET_MIN_WIDTH / w)
        return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    if w > TARGET_MAX_WIDTH:
        f = TARGET_MAX_WIDTH / w
        return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return gray


def _estimate_skew(gray: np.ndarray) -> float:
    """Projection-profile skew estimate in degrees (-6..6)."""
    small = gray
    if gray.shape[1] > 1000:
        f = 1000 / gray.shape[1]
        small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape
    centre = (w / 2, h / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-6.0, 6.01, 0.5):
        m = cv2.getRotationMatrix2D(centre, float(angle), 1.0)
        rotated = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        score = float(np.var(profile))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def _rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def _basic(gray: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(gray, (1, 99))
    if hi - lo < 10:
        return gray
    stretched = np.clip((gray.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
    return stretched.astype(np.uint8)


def _enhanced(gray: np.ndarray) -> np.ndarray:
    angle = _estimate_skew(gray)
    if abs(angle) >= 0.3:
        gray = _rotate(gray, angle)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    # Remove isolated specks left by binarising noisy scans.
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _osd_rotation(gray: np.ndarray) -> int:
    try:
        osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT, timeout=30)
        return int(osd.get("rotate", 0))
    except Exception:  # OSD fails on sparse pages; orientation is then left unchanged
        return 0


def _run_tesseract(img: np.ndarray, strategy: str) -> OcrResult:
    s = get_settings()
    data = pytesseract.image_to_data(
        img,
        lang=s.ocr_languages,
        config="--oem 1 --psm 3",
        output_type=pytesseract.Output.DICT,
        timeout=s.ocr_page_timeout_s,
    )
    words = []
    confs = []
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if conf < 0 or not text.strip():
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append((float(x), float(y), float(x + w), float(y + h), text))
        confs.append(conf)
    mean_conf = float(np.mean(confs)) if confs else 0.0
    return OcrResult(words_to_text(words), mean_conf, strategy, len(words))


def _score(r: OcrResult) -> float:
    # Prefer passes that recognise more words confidently.
    return r.confidence * min(1.0, r.word_count / 40.0) + r.word_count * 0.05


def ocr_image(img: Image.Image) -> OcrResult:
    gray = _rescale(_to_gray(img))
    warnings: list[str] = []
    if gray.size == 0:
        return OcrResult("", 0.0, "none", 0, ["empty image"])

    best = _run_tesseract(_basic(gray), "basic")
    if best.confidence < GOOD_CONFIDENCE or best.word_count < 5:
        enhanced = _run_tesseract(_enhanced(gray), "enhanced")
        if _score(enhanced) > _score(best):
            best = enhanced
    if best.confidence < 55 or best.word_count < 5:
        rotation = _osd_rotation(gray)
        if rotation:
            rotated = np.ascontiguousarray(np.rot90(gray, k=-rotation // 90))
            candidate = _run_tesseract(_enhanced(rotated), f"enhanced+rot{rotation}")
            if _score(candidate) > _score(best):
                best = candidate
                warnings.append(f"page was rotated {rotation} degrees")

    if best.confidence < get_settings().low_ocr_confidence:
        warnings.append(f"low OCR confidence ({best.confidence:.0f})")
    best.warnings = warnings + best.warnings
    return best
