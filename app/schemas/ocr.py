"""OCR Text Pydantic schemas - NO user tracking (fully shared)."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class OCRProcessRequest(BaseModel):
    """Schema for OCR processing request."""

    image_ids: list[int] = Field(..., min_length=1, description="List of image IDs to process")
    detected_language: Optional[str] = Field(None, description="Override detected language")


class OCRSchema(BaseModel):
    """Schema for OCR text response - NO extracted_by, NO extracted_at (uses created_at)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    image_id: int
    raw_text_with_formatting: str  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text_for_search: str  # Plain text without formatting tags
    detected_language: Optional[str] = None
    processing_time_ms: Optional[int] = None  # Time Gemini took to extract
    created_at: datetime  # When the text was extracted


class OCRResponseSchema(BaseModel):
    """Schema for OCR processing response."""

    task_id: str = Field(..., description="Task ID for polling status")
    image_count: int = Field(..., description="Number of images submitted for processing")
    message: str = "Images submitted for OCR processing"


class OCRStatusSchema(BaseModel):
    """Schema for OCR processing status."""

    task_id: str
    status: str  # pending, processing, completed, failed
    completed_count: int = 0
    total_count: int = 0
    errors: list[dict] = Field(default_factory=list)  # List of {image_id, error_message}
