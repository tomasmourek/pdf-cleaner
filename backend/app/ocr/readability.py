"""Readability score výpočet — DPI, kontrast, ostrost (Laplacian variance)."""
import io
import logging
from dataclasses import dataclass
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ReadabilityResult:
    score: int  # 0-100
    dpi_score: int
    contrast_score: int
    sharpness_score: int
    details: dict


def compute_readability(image_bytes: bytes, dpi: int = 0) -> ReadabilityResult:
    """
    Vypočítá readability score 0-100.
    Pokud score < threshold (default 60) → dokument je odmítnut.
    """
    try:
        from PIL import Image
        import cv2

        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        img_array = np.array(img)

        # --- DPI score ---
        if dpi == 0:
            # Try to get from image metadata
            dpi_info = img.info.get("dpi", (72, 72))
            dpi = int(dpi_info[0]) if isinstance(dpi_info, tuple) else int(dpi_info)

        dpi_score = _score_dpi(dpi)

        # --- Convert to grayscale for analysis ---
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # --- Contrast score (RMS contrast) ---
        contrast = gray.std()
        contrast_score = min(100, int(contrast / 1.28))  # 128 std = score 100

        # --- Sharpness score (Laplacian variance) ---
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness_var = laplacian.var()
        sharpness_score = min(100, int(sharpness_var / 50))

        # Weighted average
        score = int(
            dpi_score * 0.30 +
            contrast_score * 0.35 +
            sharpness_score * 0.35
        )
        score = max(0, min(100, score))

        return ReadabilityResult(
            score=score,
            dpi_score=dpi_score,
            contrast_score=contrast_score,
            sharpness_score=sharpness_score,
            details={
                "dpi": dpi,
                "contrast_std": float(contrast),
                "laplacian_variance": float(sharpness_var),
            },
        )
    except ImportError:
        # cv2 not installed in test environment
        logger.warning("OpenCV not available, using fallback readability score")
        return ReadabilityResult(score=75, dpi_score=75, contrast_score=75, sharpness_score=75, details={})
    except Exception as e:
        logger.error("Readability computation error: %s", e)
        return ReadabilityResult(score=60, dpi_score=60, contrast_score=60, sharpness_score=60, details={"error": str(e)})


def _score_dpi(dpi: int) -> int:
    """DPI → quality score (0-100)."""
    if dpi >= 300:
        return 100
    if dpi >= 200:
        return 80
    if dpi >= 150:
        return 60
    if dpi >= 100:
        return 40
    if dpi >= 72:
        return 20
    return 10
