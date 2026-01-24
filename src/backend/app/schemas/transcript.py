"""Audio Transcript Pydantic schemas - NO user tracking (fully shared)."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class AudioTranscriptRequest(BaseModel):
    """Schema for audio transcription processing request."""

    audio_ids: list[int] = Field(..., min_length=1, description="List of audio IDs to transcribe")
    detected_language: Optional[str] = Field(None, description="Override detected language")
    model: str = Field("lower", description="Model to use: 'higher' (more accurate, slower) or 'lower' (faster, cost-effective)")
    custom_prompt: Optional[str] = Field(None, description="Optional custom prompt to be appended to the default transcription prompt")


class AudioTranscriptUpdateRequest(BaseModel):
    """Schema for manual audio transcript update request."""
    
    text_with_formatting: str = Field(..., description="Corrected transcript with markdown formatting")
    plain_text: Optional[str] = Field(None, description="Corrected plain text (auto-extracted if not provided)")


class AudioTranscriptSchema(BaseModel):
    """Schema for audio transcript response - NO extracted_by, NO extracted_at (uses created_at)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    audio_id: int
    raw_text_with_formatting: str  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text_for_search: str  # Plain text without formatting tags
    detected_language: Optional[str] = None
    processing_time_ms: Optional[int] = None  # Time Gemini took to transcribe
    model_used: Optional[str] = None  # Which model was used for transcription
    created_at: datetime  # When the transcript was extracted
    # Manual edit fields
    edited_text_with_formatting: Optional[str] = None  # User-edited text with formatting
    edited_plain_text: Optional[str] = None  # User-edited plain text
    edited_at: Optional[datetime] = None  # When user last edited


class AudioTranscriptResponseSchema(BaseModel):
    """Schema for audio transcription processing response."""

    task_id: str = Field(..., description="Task ID for polling status")
    audio_count: int = Field(..., description="Number of audio files submitted for transcription")
    message: str = "Audio files submitted for transcription"


class AudioTranscriptStatusSchema(BaseModel):
    """Schema for audio transcription processing status."""

    task_id: str
    status: str  # pending, processing, completed, failed
    completed_count: int = 0
    total_count: int = 0
    errors: list[dict] = Field(default_factory=list)  # List of {audio_id, error_message}
