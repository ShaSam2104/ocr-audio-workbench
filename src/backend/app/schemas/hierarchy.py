"""Book and Chapter Pydantic schemas - fully shared across all users."""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any


class BookCreateSchema(BaseModel):
    """Schema for creating a new book."""

    name: str = Field(..., min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")
    languages: Optional[List[str]] = Field(None, description="List of language codes (e.g., ['en', 'hi', 'gu'])", min_length=1)


class BookUpdateSchema(BaseModel):
    """Schema for updating a book."""

    name: Optional[str] = Field(None, min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")
    languages: Optional[List[str]] = Field(None, description="List of language codes (e.g., ['en', 'hi', 'gu'])")


class BookSchema(BaseModel):
    """Schema for book response - NO user_id (fully shared)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    languages: Optional[List[str]] = None  # Parsed from comma-separated string
    created_at: datetime
    updated_at: datetime
    
    @field_validator('languages', mode='before')
    @classmethod
    def parse_languages(cls, v: Optional[str | List[str]]) -> Optional[List[str]]:
        """Convert comma-separated string to list of languages."""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [lang.strip() for lang in v.split(",") if lang.strip()]
        return None


class ChapterCreateSchema(BaseModel):
    """Schema for creating a new chapter."""

    name: str = Field(..., min_length=1, description="Chapter name")
    description: Optional[str] = Field(None, description="Chapter description")
    sequence_order: Optional[int] = Field(None, description="Sequence order in book")


class ChapterUpdateSchema(BaseModel):
    """Schema for updating a chapter."""

    name: Optional[str] = Field(None, min_length=1, description="Chapter name")
    description: Optional[str] = Field(None, description="Chapter description")
    sequence_order: Optional[int] = Field(None, description="Sequence order in book")


class ChapterSchema(BaseModel):
    """Schema for chapter response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    name: str
    description: Optional[str] = None
    sequence_order: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class BookDetailSchema(BookSchema):
    """Extended schema for book with chapters."""

    chapters: list[ChapterSchema] = Field(default_factory=list)


class ImageContentSchema(BaseModel):
    """Schema for image with OCR content in chapter details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence_number: int
    page_number: Optional[int] = None
    ocr_status: str
    image_url: Optional[str] = None  # Presigned URL for 30 mins
    ocr_text: Optional[Dict[str, Any]] = None  # OCRSchema when available


class AudioContentSchema(BaseModel):
    """Schema for audio with transcript content in chapter details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence_number: int
    duration_seconds: Optional[int] = None
    audio_format: Optional[str] = None
    transcription_status: str
    audio_url: Optional[str] = None  # Presigned URL for 30 mins
    transcript: Optional[Dict[str, Any]] = None  # AudioTranscriptSchema when available


class ChapterDetailSchema(ChapterSchema):
    """Extended schema for chapter with all associated images and audio content."""

    images: list[ImageContentSchema] = Field(default_factory=list)
    audios: list[AudioContentSchema] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")


class ImagesPaginatedResponse(BaseModel):
    """Paginated response for images."""

    items: list[ImageContentSchema] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class AudiosPaginatedResponse(BaseModel):
    """Paginated response for audio files."""

    items: list[AudioContentSchema] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class ChapterWithContentResponse(BaseModel):
    """Complete response for chapter with paginated images and audio content."""

    model_config = ConfigDict(from_attributes=True)

    chapter: ChapterSchema = Field(..., description="Chapter metadata")
    images: ImagesPaginatedResponse = Field(..., description="Paginated images in chapter with OCR content")
    audios: AudiosPaginatedResponse = Field(..., description="Paginated audio files in chapter with transcripts")
