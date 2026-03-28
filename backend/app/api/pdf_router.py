"""PDF API — /pdf/* endpointy pro upravpdf.eu."""
import uuid
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.config import settings
from ..models.document import Document, DocumentBatch
from ..ocr.readability import compute_readability
from ..ocr.pipeline import run_ocr
from ..ocr.extractor import extract_data_from_text
from ..services.auth_client import get_current_user, require_plan
from ..services.minio_service import upload_file, download_file, delete_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pdf", tags=["pdf"])

MAX_FILE_SIZE_MB = 20
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
DEFAULT_READABILITY_THRESHOLD = 60


def _get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    return ext


async def _process_document(
    doc_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    readability_threshold: int,
    db_url: str,
):
    """Background task — OCR + extrakce."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as AS

    engine = create_async_engine(db_url)
    SessionLocal = async_sessionmaker(engine, class_=AS, expire_on_commit=False)

    async with SessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        start_time = time.monotonic()
        try:
            doc.status = "processing"
            await db.flush()
            await db.commit()

            # Readability check
            readability = compute_readability(file_bytes)
            doc.readability_score = readability.score

            # OCR pipeline
            ocr_result = await run_ocr(
                file_bytes, filename, readability.score, readability_threshold
            )
            doc.ocr_method = ocr_result.method
            doc.ocr_confidence = round(ocr_result.confidence, 2)
            doc.detected_language = ocr_result.language

            # AI extraction
            if settings.CLAUDE_API_KEY:
                extraction = await extract_data_from_text(ocr_result.text, settings.CLAUDE_API_KEY)
                doc.detected_type = extraction.document_type
                doc.detected_language = extraction.language
                doc.extracted_data = {
                    "header": extraction.header,
                    "rows": extraction.rows,
                    "totals": extraction.totals,
                    "confidence": extraction.confidence,
                }
            else:
                doc.extracted_data = {"raw_text": ocr_result.text[:5000]}

            doc.status = "done"
            doc.processing_time_ms = int((time.monotonic() - start_time) * 1000)
            await db.commit()

        except ValueError as e:
            # Readability too low
            doc.status = "rejected_quality"
            doc.extracted_data = {"error": str(e)}
            await db.commit()
        except Exception as e:
            logger.error("Document processing failed: %s", e, exc_info=True)
            doc.status = "failed"
            doc.extracted_data = {"error": str(e)}
            await db.commit()
        finally:
            await engine.dispose()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Nahrání jednoho souboru ke zpracování (OCR + AI extrakce)."""
    await require_plan(current_user, "pro")  # PDF access requires PRO+

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Nepodporovaný formát: {ext}. Povoleno: PDF, JPG, PNG")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Soubor je příliš velký (max {MAX_FILE_SIZE_MB} MB).")

    # Upload to MinIO
    storage_key = f"pdf/{current_user['id']}/{uuid.uuid4()}/{file.filename}"
    await upload_file(storage_key, content, content_type=file.content_type or "application/octet-stream")

    # Create document record
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    doc = Document(
        user_id=uuid.UUID(current_user["id"]),
        original_filename=file.filename,
        file_type=_get_file_type(file.filename),
        file_size_bytes=len(content),
        storage_key=storage_key,
        storage_expires_at=expires_at,
        status="pending",
    )
    db.add(doc)
    await db.flush()
    await db.commit()

    # Start background processing
    background_tasks.add_task(
        _process_document,
        doc.id, content, file.filename,
        DEFAULT_READABILITY_THRESHOLD, settings.DATABASE_URL
    )

    return {
        "document_id": str(doc.id),
        "status": "pending",
        "message": "Dokument byl nahrán a čeká na zpracování.",
    }


@router.get("/jobs/{document_id}")
async def get_job_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Polling — stav zpracování dokumentu."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.user_id == uuid.UUID(current_user["id"]),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nenalezen.")

    return {
        "document_id": str(doc.id),
        "status": doc.status,
        "readability_score": doc.readability_score,
        "ocr_method": doc.ocr_method,
        "ocr_confidence": float(doc.ocr_confidence) if doc.ocr_confidence else None,
        "detected_type": doc.detected_type,
        "detected_language": doc.detected_language,
        "processing_time_ms": doc.processing_time_ms,
        "created_at": doc.created_at.isoformat(),
    }


@router.get("/jobs/{document_id}/result")
async def get_job_result(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Výsledek extrakce — plná strukturovaná data."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.user_id == uuid.UUID(current_user["id"]),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nenalezen.")
    if doc.status != "done":
        raise HTTPException(status_code=202, detail=f"Dokument ještě není zpracován (stav: {doc.status}).")

    return {
        "document_id": str(doc.id),
        "status": doc.status,
        "document_type": doc.detected_type,
        "language": doc.detected_language,
        "readability_score": doc.readability_score,
        "ocr_method": doc.ocr_method,
        "ocr_confidence": float(doc.ocr_confidence) if doc.ocr_confidence else None,
        "data": doc.extracted_data,
        "processing_time_ms": doc.processing_time_ms,
    }


@router.post("/handoff/{document_id}")
async def handoff_to_csv(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Předání výsledku do upravcsv.eu pomocí Redis tokenu (one-time use, TTL 10 min)."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.user_id == uuid.UUID(current_user["id"]),
            Document.status == "done",
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nenalezen nebo ještě není zpracován.")

    # Generate one-time token and store in Redis
    import redis.asyncio as aioredis
    token = str(uuid.uuid4())

    handoff_data = json.dumps({
        "document_id": str(doc.id),
        "filename": doc.original_filename,
        "user_id": current_user["id"],
        "header": doc.extracted_data.get("header", {}),
        "rows": doc.extracted_data.get("rows", []),
        "totals": doc.extracted_data.get("totals", {}),
    })

    redis_client = await aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await redis_client.setex(f"handoff:{token}", 600, handoff_data)  # TTL 10 minutes

    redirect_url = f"https://upravcsv.eu/import?token={token}&source=pdf"

    return {
        "token": token,
        "redirect_url": redirect_url,
        "expires_in_seconds": 600,
        "row_count": len(doc.extracted_data.get("rows", [])),
        "total_amount": doc.extracted_data.get("totals", {}).get("total_incl_vat"),
    }


@router.get("/history")
async def document_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = select(Document).where(Document.user_id == uuid.UUID(current_user["id"]))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(Document.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    docs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(d.id),
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "status": d.status,
                "detected_type": d.detected_type,
                "readability_score": d.readability_score,
                "ocr_method": d.ocr_method,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ],
        "total": total,
        "page": page,
    }


@router.delete("/history/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.user_id == uuid.UUID(current_user["id"]),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nenalezen.")

    if doc.storage_key:
        await delete_file(doc.storage_key)

    await db.delete(doc)
    return {"message": "Dokument byl smazán."}
