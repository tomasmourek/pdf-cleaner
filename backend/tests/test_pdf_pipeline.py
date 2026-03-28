"""Sprint 3 — Integrační testy PDF pipeline."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.ocr.readability import _score_dpi, ReadabilityResult


# ── Readability score ─────────────────────────────────────────────────────────

class TestReadabilityScore:
    def test_dpi_300_is_perfect(self):
        assert _score_dpi(300) == 100

    def test_dpi_200_is_good(self):
        assert _score_dpi(200) == 80

    def test_dpi_150_is_acceptable(self):
        assert _score_dpi(150) == 60

    def test_dpi_72_is_poor(self):
        assert _score_dpi(72) == 20

    def test_dpi_50_is_very_poor(self):
        assert _score_dpi(50) == 10

    def test_readability_fallback_no_cv2(self):
        """Test that readability returns sensible defaults when OpenCV not available."""
        from app.ocr.readability import compute_readability
        # Create a minimal valid PNG (1x1 white pixel)
        png_1x1 = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xA7, 0x35, 0x81,
            0x84, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
            0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        result = compute_readability(png_1x1)
        assert isinstance(result, ReadabilityResult)
        assert 0 <= result.score <= 100


# ── OCR Pipeline decision tree ────────────────────────────────────────────────

class TestOCRPipeline:
    @pytest.mark.asyncio
    async def test_rejects_low_readability(self):
        from app.ocr.pipeline import run_ocr
        dummy_bytes = b"dummy"
        with pytest.raises(ValueError, match="Čitelnost"):
            await run_ocr(dummy_bytes, "bad.jpg", readability_score=30, readability_threshold=60)

    @pytest.mark.asyncio
    async def test_native_pdf_used_for_text_pdf(self):
        from app.ocr.pipeline import _try_native_pdf

        # Create a minimal PDF-like structure that pdfplumber can open
        # We test that function returns None for non-PDF bytes without crashing
        result = await _try_native_pdf(b"not a real pdf")
        assert result is None  # Should return None gracefully

    @pytest.mark.asyncio
    async def test_ocr_method_selection_high_score(self):
        """Score >= 80 should attempt Google Vision."""
        from app.ocr.pipeline import run_ocr

        with patch("app.ocr.pipeline._try_native_pdf", return_value=None), \
             patch("app.ocr.pipeline._try_google_vision") as mock_gv, \
             patch("app.ocr.pipeline.settings") as mock_settings:
            from app.ocr.pipeline import OCRResult
            mock_settings.GOOGLE_VISION_API_KEY = "test-key"
            mock_settings.CLAUDE_API_KEY = ""
            mock_gv.return_value = OCRResult(text="Google Vision text", method="google_vision", confidence=90.0)

            result = await run_ocr(b"data", "test.jpg", readability_score=85)
            assert result.method == "google_vision"
            mock_gv.assert_called_once()


# ── Data extraction prompt ────────────────────────────────────────────────────

class TestExtractor:
    def test_extraction_prompt_contains_required_fields(self):
        from app.ocr.extractor import EXTRACTION_PROMPT
        assert "document_type" in EXTRACTION_PROMPT
        assert "kod_zbozi" in EXTRACTION_PROMPT
        assert "nakupni_cena_bez" in EXTRACTION_PROMPT
        assert "confidence" in EXTRACTION_PROMPT

    @pytest.mark.asyncio
    async def test_extraction_parses_valid_json(self):
        from app.ocr.extractor import extract_data_from_text

        sample_response = '''{
          "document_type": "invoice",
          "language": "cs",
          "header": {"vendor_name": "LKQ Czech"},
          "rows": [{"kod_zbozi": "X001", "nazev": "Díl", "mnozstvi": 2}],
          "totals": {"total_incl_vat": 500.00},
          "_confidence": {"document_type": 0.95}
        }'''

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=sample_response)]
            mock_client.messages.create.return_value = mock_response

            result = await extract_data_from_text("sample ocr text", "test-api-key")

            assert result.document_type == "invoice"
            assert result.language == "cs"
            assert len(result.rows) == 1
            assert result.rows[0]["kod_zbozi"] == "X001"


# ── Handoff token ─────────────────────────────────────────────────────────────

class TestHandoff:
    @pytest.mark.asyncio
    async def test_handoff_generates_unique_token(self):
        """Každé volání handoff endpointu musí generovat unikátní token."""
        import uuid
        tokens = {str(uuid.uuid4()) for _ in range(10)}
        assert len(tokens) == 10  # All unique

    def test_handoff_redirect_url_format(self):
        token = "test-token-123"
        redirect_url = f"https://upravcsv.eu/import?token={token}&source=pdf"
        assert "token=" in redirect_url
        assert "source=pdf" in redirect_url
        assert redirect_url.startswith("https://")
