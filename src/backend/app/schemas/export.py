"""Export request/response schemas."""
from typing import List, Optional
from pydantic import BaseModel, Field


class ExportFolderRequest(BaseModel):
    """Request to export a book or chapter."""

    book_id: int = Field(..., description="Book ID to export")
    chapter_id: Optional[int] = Field(None, description="Optional chapter ID (if None, export all chapters in book)")
    format: str = Field(default="docx", description="Export format: 'docx' or 'txt'")
    include_images: bool = Field(default=True, description="Include images in export")
    include_audio_transcripts: bool = Field(default=True, description="Include audio transcripts in export")
    include_page_breaks: bool = Field(default=False, description="Include page breaks between chapters (docx only)")


class ExportSelectionRequest(BaseModel):
    """Request to export selected images and audios."""

    image_ids: Optional[List[int]] = Field(None, description="List of image IDs to export")
    audio_ids: Optional[List[int]] = Field(None, description="List of audio IDs to export")
    format: str = Field(default="docx", description="Export format: 'docx' or 'txt'")
    include_images: bool = Field(default=True, description="Include images in export")
