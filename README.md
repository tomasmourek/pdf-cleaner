# upravpdf.eu — PDF OCR & AI extrakce

Backend a frontend pro analýzu PDF dokumentů a fotek.

## Součásti
- `upravpdf-backend/` — FastAPI, OCR pipeline (pdfplumber → Tesseract → Google Vision → Claude Vision), AI extrakce dat
- `frontend-upravpdf/` — React + Vite + PWA

## Závislost
Autentizace běží v repozitáři [CSV-Cleaner](https://github.com/tomasmourek/CSV-Cleaner-for-only-test) (auth-service).

## Spuštění
Viz `docker-compose.yml` v hlavním repozitáři.
