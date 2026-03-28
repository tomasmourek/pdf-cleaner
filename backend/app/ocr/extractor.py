"""Claude API — strukturovaná extrakce dat z OCR textu.

Výstup: JSON s hlavičkou, řádky, souhrny a confidence skóre per pole.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyzuj tento text dodacího listu nebo faktury a extrahuj data ve formátu JSON.

Text dokumentu:
{text}

Vrať JSON s touto strukturou (všechna pole jsou volitelná, vynech pokud chybí):
{{
  "document_type": "invoice | delivery_note | order | unknown",
  "language": "cs | en | de",
  "header": {{
    "vendor_name": "",
    "vendor_ico": "",
    "vendor_dic": "",
    "client_name": "",
    "client_ico": "",
    "document_number": "",
    "document_date": "",
    "due_date": "",
    "currency": "CZK",
    "payment_method": ""
  }},
  "rows": [
    {{
      "kod_zbozi": "",
      "nazev": "",
      "mnozstvi": null,
      "jednotka": "",
      "nakupni_cena_bez": null,
      "nakupni_cena_s": null,
      "prodejni_cena_bez": null,
      "prodejni_cena_s": null,
      "dan_sazba": null,
      "sleva": null,
      "poznamka": "",
      "_confidence": {{
        "kod_zbozi": 0.95,
        "nazev": 0.98,
        "mnozstvi": 0.99
      }}
    }}
  ],
  "totals": {{
    "subtotal_excl_vat": null,
    "vat_amount": null,
    "total_incl_vat": null
  }},
  "_confidence": {{
    "document_type": 0.95,
    "language": 0.99,
    "header": 0.90
  }}
}}

Pravidla:
- Ceny jako float (desetinná tečka)
- Confidence score 0.0-1.0 per pole
- document_type: "invoice" = faktura, "delivery_note" = dodací list, "order" = objednávka
- Vrať POUZE JSON, bez komentářů"""


@dataclass
class ExtractionResult:
    document_type: str
    language: str
    header: Dict[str, Any]
    rows: List[Dict[str, Any]]
    totals: Dict[str, Any]
    confidence: Dict[str, Any]
    raw_json: str = ""


async def extract_data_from_text(ocr_text: str, claude_api_key: str) -> ExtractionResult:
    """Zavolá Claude API a extrahuje strukturovaná data z OCR textu."""
    import anthropic

    client = anthropic.Anthropic(api_key=claude_api_key)

    prompt = EXTRACTION_PROMPT.format(text=ocr_text[:8000])  # Limit tokens

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_json = response.content[0].text.strip()

    # Strip markdown code blocks if present
    if raw_json.startswith("```"):
        lines = raw_json.split("\n")
        raw_json = "\n".join(lines[1:-1])

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error from Claude: %s\nRaw: %s", e, raw_json[:500])
        raise ValueError(f"Chyba parsování JSON výstupu z AI: {e}")

    return ExtractionResult(
        document_type=data.get("document_type", "unknown"),
        language=data.get("language", "cs"),
        header=data.get("header", {}),
        rows=data.get("rows", []),
        totals=data.get("totals", {}),
        confidence=data.get("_confidence", {}),
        raw_json=raw_json,
    )
