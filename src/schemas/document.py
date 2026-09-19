"""Pydantic schemas for document API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Full document details response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Document UUID")
    session_id: str = Field(description="Session the document belongs to")
    user_id: str = Field(description="Owner user ID")
    filename: str = Field(description="Stored filename")
    original_filename: str = Field(description="Original uploaded filename")
    file_type: str = Field(description="File type (pdf, docx, txt, md)")
    file_size: int = Field(description="File size in bytes")
    page_count: int | None = Field(default=None, description="Number of pages (PDFs only)")
    word_count: int | None = Field(default=None, description="Approximate word count")
    is_indexed: bool = Field(description="Whether document is indexed for search")
    created_at: datetime = Field(description="Upload timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class DocumentListItem(BaseModel):
    """Summary document information for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Document UUID")
    session_id: str = Field(description="Session the document belongs to")
    original_filename: str = Field(description="Original uploaded filename")
    file_type: str = Field(description="File type (pdf, docx, txt, md)")
    file_size: int = Field(description="File size in bytes")
    page_count: int | None = Field(default=None, description="Number of pages")
    word_count: int | None = Field(default=None, description="Approximate word count")
    is_indexed: bool = Field(description="Whether document is indexed for search")
    created_at: datetime = Field(description="Upload timestamp")


class DocumentListResponse(BaseModel):
    """Paginated list of documents response."""

    items: list[DocumentListItem] = Field(description="List of documents")
    total: int = Field(description="Total number of documents")
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=20, description="Maximum records returned")


class SessionDocumentsResponse(BaseModel):
    """Documents for a specific session."""

    session_id: str = Field(description="Session UUID")
    documents: list[DocumentListItem] = Field(description="Documents in the session")
    count: int = Field(description="Number of documents")
    max_documents: int = Field(default=5, description="Maximum documents allowed")
    can_add_more: bool = Field(description="Whether more documents can be added")


class DocumentSummary(BaseModel):
    """Minimal document summary for embedding in other responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Document UUID")
    original_filename: str = Field(description="Original uploaded filename")
    file_type: str = Field(description="File type")
    is_indexed: bool = Field(description="Whether document is indexed")


class DocumentUploadResponse(BaseModel):
    """Response after successful document upload."""

    document: DocumentResponse = Field(description="The uploaded document")
    message: str = Field(default="Document uploaded successfully")
