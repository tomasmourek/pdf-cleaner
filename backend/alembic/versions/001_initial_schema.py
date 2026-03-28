"""Initial schema — documents + document_batches

Revision ID: b2c3d4e5f6a1
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── document_batches ─────────────────────────────────────────────────────
    op.create_table(
        "document_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending|processing|done|error
        sa.Column("total_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("merged_output_key", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),  # 24h auto-delete
    )
    op.create_index("ix_document_batches_user_id", "document_batches", ["user_id"])

    # ── documents ────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending|processing|done|error
        sa.Column("error_message", sa.Text, nullable=True),
        # MinIO reference (encrypted)
        sa.Column("object_key", sa.String(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        # OCR pipeline results
        sa.Column("ocr_method", sa.String(50), nullable=True),  # native|tesseract|google_vision|claude_vision
        sa.Column("readability_score", sa.Float, nullable=True),
        sa.Column("ocr_text", sa.Text, nullable=True),
        # AI extraction
        sa.Column("extracted_data", postgresql.JSONB, nullable=True),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        # Handoff to upravcsv.eu
        sa.Column("handoff_token", sa.String(100), nullable=True, unique=True),
        sa.Column("handoff_used_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), onupdate=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),  # 24h auto-delete
        # Foreign key
        sa.ForeignKeyConstraint(["batch_id"], ["document_batches.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_batch_id", "documents", ["batch_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("document_batches")
