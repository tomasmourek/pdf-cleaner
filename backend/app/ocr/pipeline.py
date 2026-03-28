"""OCR Pipeline — rozhodovací strom dle kvality dokumentu.

Tok:
  PDF s textovou vrstvou → pdfplumber (přímá extrakce)
  Score 60-79 → Tesseract s preprocessingem (de-skew, Otsu, noise removal)
  Score ≥ 80 NEBO Tesseract confidence < 70% → Google Vision API
  Fallback → Claude Vision API pro složité rozvržení
"""
import io
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_READABILITY_THRESHOLD = 60
TESSERACT_CONFIDENCE_THRESHOLD = 70


@dataclass
class OCRResult:
    text: str
    method: str  # native_pdf | tesseract | google_vision | claude_vision
    confidence: float  # 0-100
    language: Optional[str] = None
    page_count: int = 1


async def run_ocr(
    file_bytes: bytes,
    filename: str,
    readability_score: int,
    readability_threshold: int = DEFAULT_READABILITY_THRESHOLD,
) -> OCRResult:
    """Spustí OCR dle rozhodovacího stromu."""
    from ..core.config import settings

    fn = filename.lower()

    # --- PDF s textovou vrstvou ---
    if fn.endswith(".pdf"):
        native_result = await _try_native_pdf(file_bytes)
        if native_result and len(native_result.text.strip()) > 50:
            logger.info("Using native PDF text extraction")
            return native_result

    # --- Readability check ---
    if readability_score < readability_threshold:
        raise ValueError(
            f"Čitelnost dokumentu je příliš nízká (skóre {readability_score}/100, "
            f"minimum {readability_threshold}). Nahrajte kvalitnější sken."
        )

    # --- Tesseract (score 60-79) ---
    if readability_score < 80:
        tesseract_result = await _try_tesseract(file_bytes, filename)
        if tesseract_result and tesseract_result.confidence >= TESSERACT_CONFIDENCE_THRESHOLD:
            logger.info("Using Tesseract OCR (confidence: %.1f%%)", tesseract_result.confidence)
            return tesseract_result
        logger.info("Tesseract confidence too low (%.1f%%), falling back to Vision API",
                    tesseract_result.confidence if tesseract_result else 0)

    # --- Google Vision API (score ≥ 80) ---
    if settings.GOOGLE_VISION_API_KEY:
        vision_result = await _try_google_vision(file_bytes, filename)
        if vision_result:
            logger.info("Using Google Vision API")
            return vision_result

    # --- Claude Vision API (fallback) ---
    if settings.CLAUDE_API_KEY:
        logger.info("Using Claude Vision API (fallback)")
        return await _try_claude_vision(file_bytes, filename)

    raise RuntimeError("Žádná OCR metoda není dostupná. Kontaktujte podporu.")


async def _try_native_pdf(file_bytes: bytes) -> Optional[OCRResult]:
    try:
        import pdfplumber
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
        texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        if texts:
            return OCRResult(
                text="\n\n".join(texts),
                method="native_pdf",
                confidence=95.0,
                page_count=len(pdf.pages),
            )
    except Exception as e:
        logger.warning("Native PDF extraction failed: %s", e)
    return None


async def _try_tesseract(file_bytes: bytes, filename: str) -> Optional[OCRResult]:
    try:
        import pytesseract
        from PIL import Image
        import cv2
        import numpy as np

        # Load image
        if filename.lower().endswith(".pdf"):
            # Convert PDF page to image
            img_bytes = await _pdf_to_image_bytes(file_bytes)
        else:
            img_bytes = file_bytes

        img = Image.open(io.BytesIO(img_bytes))
        img_array = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Preprocessing
        # 1. De-skew
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            (h, w) = gray.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # 2. Binarization (Otsu threshold)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 3. Noise removal
        denoised = cv2.medianBlur(binary, 3)

        processed_img = Image.fromarray(denoised)

        # Run Tesseract with Czech + English + German
        config = "--oem 3 --psm 6 -l ces+eng+deu"
        data = pytesseract.image_to_data(processed_img, config=config, output_type=pytesseract.Output.DICT)

        # Calculate confidence
        confidences = [int(c) for c in data["conf"] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        text = pytesseract.image_to_string(processed_img, config=config)

        return OCRResult(
            text=text,
            method="tesseract",
            confidence=avg_confidence,
        )
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)
        return None


async def _try_google_vision(file_bytes: bytes, filename: str) -> Optional[OCRResult]:
    try:
        from google.cloud import vision
        from ..core.config import settings

        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=file_bytes)
        response = client.document_text_detection(image=image)

        if response.error.message:
            logger.error("Google Vision error: %s", response.error.message)
            return None

        text = response.full_text_annotation.text
        confidence = response.full_text_annotation.pages[0].confidence * 100 if response.full_text_annotation.pages else 85.0

        return OCRResult(
            text=text,
            method="google_vision",
            confidence=confidence,
        )
    except Exception as e:
        logger.warning("Google Vision failed: %s", e)
        return None


async def _try_claude_vision(file_bytes: bytes, filename: str) -> OCRResult:
    """Claude Vision API — fallback pro složité rozvržení dokumentů."""
    import anthropic
    import base64
    from ..core.config import settings

    client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)

    # Determine media type
    fn = filename.lower()
    if fn.endswith(".pdf"):
        media_type = "application/pdf"
    elif fn.endswith(".png"):
        media_type = "image/png"
    else:
        media_type = "image/jpeg"

    encoded = base64.standard_b64encode(file_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                },
                {
                    "type": "text",
                    "text": (
                        "Přepiš veškerý text z tohoto dokumentu přesně tak, jak je uveden. "
                        "Zachovej strukturu tabulek. Odpovídej pouze textem dokumentu, bez komentářů."
                    )
                }
            ],
        }],
    )

    return OCRResult(
        text=response.content[0].text,
        method="claude_vision",
        confidence=85.0,
    )


async def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """Konvertuje první stránku PDF na PNG bytes."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        mat = fitz.Matrix(2, 2)  # 2x zoom = ~144 DPI
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    except ImportError:
        # Fallback: use pdfplumber → pillow
        import pdfplumber
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        if pdf.pages:
            img = pdf.pages[0].to_image(resolution=150)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        raise RuntimeError("Cannot convert PDF to image")
