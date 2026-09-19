"""SQLAlchemy model for uploaded documents."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Document(Base):
    """SQLAlchemy model for uploaded documents in chat sessions.

    Documents are session-scoped, with a maximum of 5 documents per session.
    They are chunked, embedded, and searchable via RAG alongside transcripts.
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    # File metadata
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf, docx, txt, md
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Content metadata
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Processing status
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Provenance: "upload" (user-uploaded reference file) or "artifact"
    # (auto-saved from a chat-generated artifact). The per-session document
    # cap only counts "upload" documents.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="upload", server_default="upload"
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id"), nullable=True, index=True
    )
    source_block_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session", back_populates="documents"
    )
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="documents"
    )

    def __repr__(self) -> str:
        """Return string representation of the document."""
        return f"<Document(id={self.id}, filename={self.original_filename!r}, type={self.file_type})>"
