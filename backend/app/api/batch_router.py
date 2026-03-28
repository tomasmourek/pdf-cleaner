"""Batch upload API — hromadný upload + ořez + spojení PDF (Sprint 4, PRO+)."""
import uuid
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.config import settings
from ..models.document import Document, DocumentBatch
from ..services.auth_client import get_current_user, require_plan
from ..services.minio_service import upload_file, download_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pdf/batch", tags=["batch"])

MAX_BATCH_PAGES = 20
MAX_BATCH_SIZE_MB = 50


@router.post("/upload")
async def batch_upload(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Hromadný upload více souborů — pouze PRO/BUSINESS uživatelé."""
    await require_plan(current_user, "pro")

    if len(files) > MAX_BATCH_PAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BATCH_PAGES} souborů v dávce.")

    total_size = 0
    uploaded_docs = []

    for file in files:
        content = await file.read()
        total_size += len(content)

        if total_size > MAX_BATCH_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Celková velikost dávky přesáhla {MAX_BATCH_SIZE_MB} MB.")

        storage_key = f"pdf/{current_user['id']}/batch/{uuid.uuid4()}/{file.filename}"
        await upload_file(storage_key, content, content_type=file.content_type or "application/octet-stream")

        doc = Document(
            user_id=uuid.UUID(current_user["id"]),
            original_filename=file.filename,
            file_type=file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin",
            file_size_bytes=len(content),
            storage_key=storage_key,
            storage_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            status="pending",
            is_batch=True,
        )
        db.add(doc)
        await db.flush()
        uploaded_docs.append({
            "document_id": str(doc.id),
            "filename": file.filename,
            "size_bytes": len(content),
        })

    # Create batch record
    batch = DocumentBatch(
        user_id=uuid.UUID(current_user["id"]),
        page_count=len(files),
        status="pending",
    )
    db.add(batch)
    await db.flush()

    # Link documents to batch
    for i, doc_info in enumerate(uploaded_docs):
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_info["document_id"])))
        doc = result.scalar_one()
        doc.batch_id = batch.id

    return {
        "batch_id": str(batch.id),
        "document_count": len(files),
        "documents": uploaded_docs,
        "message": "Soubory nahrány. Použijte /pdf/batch/{batch_id}/merge pro spojení a analýzu.",
    }


class MergeRequest(BaseModel):
    document_ids: List[str]
    page_order: List[int] = []  # Optional reordering (indices into document_ids)


@router.post("/{batch_id}/merge")
async def merge_batch(
    batch_id: str,
    data: MergeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Spojení stránek z dávky do jednoho PDF a spuštění OCR analýzy."""
    await require_plan(current_user, "pro")

    result = await db.execute(
        select(DocumentBatch).where(
            DocumentBatch.id == uuid.UUID(batch_id),
            DocumentBatch.user_id == uuid.UUID(current_user["id"]),
        )
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Dávka nenalezena.")

    # Fetch all documents in requested order
    ordered_ids = [data.document_ids[i] for i in data.page_order] if data.page_order else data.document_ids

    batch.status = "processing"
    await db.flush()

    background_tasks.add_task(
        _merge_and_process, batch.id, ordered_ids, current_user["id"], settings.DATABASE_URL
    )

    return {
        "batch_id": str(batch.id),
        "status": "processing",
        "message": "Spojování a analýza spuštěna. Sledujte stav přes /pdf/batch/{batch_id}/status",
    }


async def _merge_and_process(
    batch_id: uuid.UUID,
    document_ids: List[str],
    user_id: str,
    db_url: str,
):
    """Background task — merge PDFs + run OCR on merged document."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as AS
    from ..ocr.readability import compute_readability
    from ..ocr.pipeline import run_ocr
    from ..ocr.extractor import extract_data_from_text

    engine = create_async_engine(db_url)
    SessionLocal = async_sessionmaker(engine, class_=AS, expire_on_commit=False)

    async with SessionLocal() as db:
        try:
            # Collect file bytes
            pdf_bytes_list = []
            for doc_id in document_ids:
                result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
                doc = result.scalar_one_or_none()
                if doc and doc.storage_key:
                    try:
                        content = await download_file(doc.storage_key)
                        pdf_bytes_list.append(content)
                    except Exception:
                        pass

            if not pdf_bytes_list:
                raise RuntimeError("Žádné soubory k sloučení.")

            # Merge PDFs using pdf-lib equivalent in Python (pypdf)
            try:
                from pypdf import PdfWriter
                writer = PdfWriter()
                for pdf_bytes in pdf_bytes_list:
                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(io.BytesIO(pdf_bytes))
                        for page in reader.pages:
                            writer.add_page(page)
                    except Exception:
                        pass

                merged_buf = io.BytesIO()
                writer.write(merged_buf)
                merged_bytes = merged_buf.getvalue()
            except ImportError:
                # Fallback: use first PDF
                merged_bytes = pdf_bytes_list[0]

            # Upload merged PDF
            merged_key = f"pdf/{user_id}/merged/{batch_id}/merged.pdf"
            await upload_file(merged_key, merged_bytes, content_type="application/pdf")

            # Update batch
            result = await db.execute(select(DocumentBatch).where(DocumentBatch.id == batch_id))
            batch = result.scalar_one()
            batch.merged_storage_key = merged_key

            # Run OCR on merged document
            readability = compute_readability(merged_bytes)
            ocr_result = await run_ocr(merged_bytes, "merged.pdf", readability.score)

            extracted = None
            if settings.CLAUDE_API_KEY:
                from ..ocr.extractor import extract_data_from_text
                extracted = await extract_data_from_text(ocr_result.text, settings.CLAUDE_API_KEY)

            # Create result document
            result_doc = Document(
                user_id=uuid.UUID(user_id),
                original_filename=f"batch_{batch_id}_merged.pdf",
                file_type="pdf",
                file_size_bytes=len(merged_bytes),
                storage_key=merged_key,
                storage_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                readability_score=readability.score,
                ocr_method=ocr_result.method,
                ocr_confidence=round(ocr_result.confidence, 2),
                detected_type=extracted.document_type if extracted else "unknown",
                detected_language=extracted.language if extracted else None,
                extracted_data={
                    "header": extracted.header if extracted else {},
                    "rows": extracted.rows if extracted else [],
                    "totals": extracted.totals if extracted else {},
                } if extracted else {"raw_text": ocr_result.text[:5000]},
                status="done",
                is_batch=True,
                batch_id=batch_id,
            )
            db.add(result_doc)
            batch.status = "done"
            await db.commit()

        except Exception as e:
            logger.error("Batch processing failed: %s", e, exc_info=True)
            result = await db.execute(select(DocumentBatch).where(DocumentBatch.id == batch_id))
            batch = result.scalar_one_or_none()
            if batch:
                batch.status = "failed"
                await db.commit()
        finally:
            await engine.dispose()


@router.get("/{batch_id}/status")
async def batch_status(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(DocumentBatch).where(
            DocumentBatch.id == uuid.UUID(batch_id),
            DocumentBatch.user_id == uuid.UUID(current_user["id"]),
        )
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Dávka nenalezena.")

    return {
        "batch_id": str(batch.id),
        "status": batch.status,
        "page_count": batch.page_count,
        "created_at": batch.created_at.isoformat(),
    }
