"""OCR Pipeline — rozhodovací strom dle kvality dokumentu.

Tok:
  PDF s textovou vrstvou → pdfplumber (přímá extrakce)
  Score 60-79 → Tesseract s preprocessingem (Hough de-skew, Otsu, noise removal)
  Score ≥ 80 NEBO Tesseract confidence < 70% → Google Vision API
  Fallback → Claude Vision API pro složité rozvržení

Klíčové vylepšení pro nakřivo naskenované dokumenty:
  - Detekce úhlu náklonu pomocí Hough line detection (přesnější než minAreaRect)
  - Pokud je náklon > SKEW_THRESHOLD, dokument jde automaticky na Claude Vision
    (Claude vidí vizuální layout a záhlaví tabulky správně identifikuje vždy)
  - Post-OCR normalizace: _normalize_ocr_text() slučuje záhlaví tabulek
    rozbitá na více řádků
"""
import io
import re
import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_READABILITY_THRESHOLD = 60
TESSERACT_CONFIDENCE_THRESHOLD = 70

# Pokud je detekovaný náklon větší než tento práh (ve stupních),
# dokument přeskočí Tesseract a jde rovnou na Claude/Google Vision.
# Tesseract PSM 6 spolehlivě zvládne < ~5°, nad tím se záhlaví tabulky
# může rozbít na dva řádky.
SKEW_THRESHOLD_DEGREES = 3.0

# Klíčová slova záhlaví tabulky česky/anglicky (pro _normalize_ocr_text)
_HEADER_KEYWORDS = {
    "množství", "mnozstvi", "mno2stvi",
    "dph", "vat",
    "cena", "price",
    "sleva", "discount",
    "jedn", "jednotka", "unit",
    "materiál", "material", "materil",
    "název", "nazev", "name",
    "kód", "kod", "code",
    "ks", "kus",
    "střed", "stred",
    "spz",
}


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
            native_result.text = _normalize_ocr_text(native_result.text)
            return native_result

    # --- Readability check ---
    if readability_score < readability_threshold:
        raise ValueError(
            f"Čitelnost dokumentu je příliš nízká (skóre {readability_score}/100, "
            f"minimum {readability_threshold}). Nahrajte kvalitnější sken."
        )

    # --- Detekce náklonu ---
    img_bytes_for_skew = file_bytes
    if fn.endswith(".pdf"):
        try:
            img_bytes_for_skew = await _pdf_to_image_bytes(file_bytes)
        except Exception:
            pass
    skew_angle = _detect_skew_angle(img_bytes_for_skew)
    logger.info("Detekovaný náklon dokumentu: %.2f°", skew_angle)

    # --- Tesseract (score 60-79 A náklon není příliš velký) ---
    if readability_score < 80 and abs(skew_angle) <= SKEW_THRESHOLD_DEGREES:
        tesseract_result = await _try_tesseract(file_bytes, filename, skew_angle)
        if tesseract_result and tesseract_result.confidence >= TESSERACT_CONFIDENCE_THRESHOLD:
            logger.info("Using Tesseract OCR (confidence: %.1f%%)", tesseract_result.confidence)
            tesseract_result.text = _normalize_ocr_text(tesseract_result.text)
            return tesseract_result
        logger.info(
            "Tesseract confidence too low (%.1f%%), falling back to Vision API",
            tesseract_result.confidence if tesseract_result else 0,
        )
    elif abs(skew_angle) > SKEW_THRESHOLD_DEGREES:
        logger.info(
            "Náklon %.2f° překračuje práh %.1f° → přeskočení Tesseractu, přechod na Vision API",
            skew_angle,
            SKEW_THRESHOLD_DEGREES,
        )

    # --- Google Vision API (score ≥ 80 NEBO příliš velký náklon) ---
    if settings.GOOGLE_VISION_API_KEY:
        vision_result = await _try_google_vision(file_bytes, filename)
        if vision_result:
            logger.info("Using Google Vision API")
            vision_result.text = _normalize_ocr_text(vision_result.text)
            return vision_result

    # --- Claude Vision API (fallback — nejlepší pro nakřivo naskenované dokumenty) ---
    if settings.CLAUDE_API_KEY:
        logger.info("Using Claude Vision API (fallback)")
        result = await _try_claude_vision(file_bytes, filename, skew_angle)
        result.text = _normalize_ocr_text(result.text)
        return result

    raise RuntimeError("Žádná OCR metoda není dostupná. Kontaktujte podporu.")


# ---------------------------------------------------------------------------
# Detekce náklonu (Hough line detection)
# ---------------------------------------------------------------------------

def _detect_skew_angle(img_bytes: bytes) -> float:
    """Odhadne úhel náklonu dokumentu pomocí Hough line detection.

    Výrazně přesnější než minAreaRect — pracuje s detekovanými
    textovými čarami, ne s obálkou všech pixelů.
    Vrátí úhel ve stupních (záporný = otočeno po směru hodinových ručiček).
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        pil = Image.open(io.BytesIO(img_bytes))
        # Downscale pro rychlost (stačí 400px výška)
        scale = 400 / pil.height if pil.height > 400 else 1.0
        if scale < 1.0:
            pil = pil.resize((int(pil.width * scale), int(pil.height * scale)))

        gray = cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2GRAY)

        # Binarizace
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Hough probabilistic line detection
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=math.pi / 180,
            threshold=100,
            minLineLength=int(pil.width * 0.3),  # čára musí být aspoň 30% šířky
            maxLineGap=20,
        )

        if lines is None or len(lines) < 3:
            logger.debug("Hough: málo čar, náklon = 0°")
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            # Bereme jen téměř horizontální čáry (±20°)
            if abs(angle) <= 20:
                angles.append(angle)

        if not angles:
            return 0.0

        # Medián je robustní vůči outlierům
        angles.sort()
        median_angle = angles[len(angles) // 2]
        logger.debug("Hough: detekováno %d čar, medián úhlu = %.2f°", len(angles), median_angle)
        return median_angle

    except Exception as e:
        logger.warning("Detekce náklonu selhala: %s", e)
        return 0.0


# ---------------------------------------------------------------------------
# Post-OCR normalizace
# ---------------------------------------------------------------------------

def _normalize_ocr_text(text: str) -> str:
    """Post-OCR normalizace: slučuje záhlaví tabulek rozbitá nakloněním dokumentu.

    Algoritmus:
      - Prochází řádky, hledá krátké řádky (< 80 znaků) s klíčovými slovy záhlaví.
      - Pokud i následující řádek je krátký a obsahuje klíčová slova, oba sloučí.
      - Opakuje dokud nelze slučovat (umožňuje záhlaví rozdělené do 3+ řádků).
    """
    lines = text.splitlines()
    merged: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if _is_header_fragment(line):
            combined = line.rstrip()
            j = i + 1
            while j < len(lines) and _is_header_fragment(lines[j]):
                combined = combined + " " + lines[j].strip()
                j += 1
            if j > i + 1:
                logger.debug(
                    "Sloučeny %d fragmenty záhlaví tabulky → '%s'", j - i, combined[:80]
                )
            merged.append(combined)
            i = j
        else:
            merged.append(line)
            i += 1

    return "\n".join(merged)


def _is_header_fragment(line: str) -> bool:
    """Vrátí True, pokud řádek vypadá jako fragment záhlaví tabulky."""
    stripped = line.strip()
    if not stripped or len(stripped) >= 80:
        return False
    words = set(re.sub(r"[^a-záčďéěíňóřšťůúýž0-9]", " ", stripped.lower()).split())
    return bool(words & _HEADER_KEYWORDS)


# ---------------------------------------------------------------------------
# OCR metody
# ---------------------------------------------------------------------------

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


async def _try_tesseract(
    file_bytes: bytes, filename: str, skew_angle: float = 0.0
) -> Optional[OCRResult]:
    try:
        import pytesseract
        from PIL import Image
        import cv2
        import numpy as np

        if filename.lower().endswith(".pdf"):
            img_bytes = await _pdf_to_image_bytes(file_bytes)
        else:
            img_bytes = file_bytes

        img = Image.open(io.BytesIO(img_bytes))
        img_array = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # --- De-skew pomocí detekovaného úhlu (Hough) ---
        if abs(skew_angle) > 0.3:
            (h, w) = gray.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, -skew_angle, 1.0)
            gray = cv2.warpAffine(
                gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            logger.debug("Tesseract de-skew: opraveno %.2f°", skew_angle)

        # --- Binarizace (Otsu threshold) ---
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # --- Noise removal ---
        denoised = cv2.medianBlur(binary, 3)

        processed_img = Image.fromarray(denoised)

        config = "--oem 3 --psm 6 -l ces+eng+deu"
        data = pytesseract.image_to_data(
            processed_img, config=config, output_type=pytesseract.Output.DICT
        )

        confidences = [int(c) for c in data["conf"] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Standardní image_to_string — PSM 6 zvládá mírné náklony samo
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
        confidence = (
            response.full_text_annotation.pages[0].confidence * 100
            if response.full_text_annotation.pages
            else 85.0
        )

        return OCRResult(
            text=text,
            method="google_vision",
            confidence=confidence,
        )
    except Exception as e:
        logger.warning("Google Vision failed: %s", e)
        return None


async def _try_claude_vision(
    file_bytes: bytes, filename: str, skew_angle: float = 0.0
) -> OCRResult:
    """Claude Vision API — nejlepší pro nakřivo naskenované dokumenty."""
    import anthropic
    import base64
    from ..core.config import settings

    client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)

    fn = filename.lower()
    if fn.endswith(".pdf"):
        media_type = "application/pdf"
    elif fn.endswith(".png"):
        media_type = "image/png"
    else:
        media_type = "image/jpeg"

    encoded = base64.standard_b64encode(file_bytes).decode("utf-8")

    skew_note = (
        f" Dokument je naskenován pod úhlem přibližně {skew_angle:.1f}°."
        if abs(skew_angle) > 1.0
        else ""
    )

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
                        f"Přepiš veškerý text z tohoto dokumentu přesně tak, jak je uveden.{skew_note} "
                        "Zachovej strukturu tabulek — záhlaví sloupců tabulky (např. 'Množství', "
                        "'DPH [%]', 'Jedn. cena', 'Sleva [%]', 'Cena bez DPH') musí být vždy "
                        "na JEDNOM řádku, i když je dokument mírně nakloněný a slova záhlaví "
                        "jsou vizuálně na různých výškách. Odpovídej pouze textem dokumentu, "
                        "bez komentářů."
                    ),
                },
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
        import pdfplumber

        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        if pdf.pages:
            img = pdf.pages[0].to_image(resolution=150)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        raise RuntimeError("Cannot convert PDF to image")
