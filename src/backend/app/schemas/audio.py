"""Audio Pydantic schemas - NO user_id (fully shared across all users)."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class AudioCreateSchema(BaseModel):
    """Schema for creating audio files (from multipart upload)."""

    sequence_number: Optional[int] = Field(None, description="Sequence number (auto-assigned if not provided)")


class AudioReorderSchema(BaseModel):
    """Schema for reordering a single audio file by sequence position."""

    current_sequence_number: int = Field(..., description="Current sequence number (position)")
    new_sequence_number: int = Field(..., description="New sequence number (position)")


class BatchAudioReorderSchema(BaseModel):
    """Schema for batch reordering multiple audio files by sequence positions."""

    audios: list[AudioReorderSchema] = Field(..., description="List of reorder operations with current and new sequence numbers")


class AudioUpdateSchema(BaseModel):
    """Schema for updating audio metadata."""

    sequence_number: Optional[int] = Field(None, description="Sequence number")
    detected_language: Optional[str] = Field(None, description="Detected language code")


class AudioSchema(BaseModel):
    """Schema for audio response - NO user_id, NO uploader_id (fully shared)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    object_key: str
    filename: str
    sequence_number: int
    duration_seconds: Optional[int] = None
    audio_format: Optional[str] = None  # mp3, wav, m4a, ogg, flac
    file_size: Optional[int] = None
    detected_language: Optional[str] = None
    transcription_status: str  # pending, processing, completed, failed
    created_at: datetime
    updated_at: datetime


class AudioListSchema(BaseModel):
    """Schema for paginated audio list response."""

    items: list[AudioSchema]
    total: int
    page: int
    page_size: int


class AudioDetailSchema(AudioSchema):
    """Extended schema for audio with transcript."""

    transcript: Optional[dict] = None  # Will be populated with AudioTranscriptSchema if available
