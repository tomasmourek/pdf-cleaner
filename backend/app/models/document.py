import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, Integer, Numeric, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | jpg | png
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    storage_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_type: Mapped[str | None] = mapped_column(String(50))  # invoice | delivery_note | order | unknown
    detected_language: Mapped[str | None] = mapped_column(String(5))
    readability_score: Mapped[int | None] = mapped_column(Integer)
    ocr_method: Mapped[str | None] = mapped_column(String(30))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | processing | done | failed | rejected_quality
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    is_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentBatch(Base):
    __tablename__ = "document_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    merged_storage_key: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
