"""Image Pydantic schemas - NO user_id (fully shared across all users)."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class ImageCreateSchema(BaseModel):
    """Schema for creating images (from multipart upload)."""

    sequence_number: Optional[int] = Field(None, description="Sequence number (auto-assigned if not provided)")
    page_number: Optional[int] = Field(None, description="Page number if from PDF")


class ImageReorderSchema(BaseModel):
    """Schema for reordering images."""

    image_id: int
    new_sequence_number: int


class ImageUpdateSchema(BaseModel):
    """Schema for updating image metadata."""

    sequence_number: Optional[int] = Field(None, description="Sequence number")
    page_number: Optional[int] = Field(None, description="Page number")
    detected_language: Optional[str] = Field(None, description="Detected language code")


class ImageSchema(BaseModel):
    """Schema for image response - NO user_id, NO uploaded_by (fully shared)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    filename: str
    sequence_number: int
    page_number: Optional[int] = None
    detected_language: Optional[str] = None
    ocr_status: str  # pending, processing, completed, failed
    is_cropped: bool
    created_at: datetime
    updated_at: datetime


class ImageListSchema(BaseModel):
    """Schema for paginated image list response."""

    items: list[ImageSchema]
    total: int
    page: int
    page_size: int


class ImageDetailSchema(ImageSchema):
    """Extended schema for image with OCR text."""

    ocr_text: Optional[dict] = None  # Will be populated with OCRSchema if available
