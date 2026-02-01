"""Pydantic schemas for export/import functionality."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ExportImportRequest(BaseModel):
    """Request schema for export/import operations."""

    book_ids: Optional[List[int]] = Field(None, description="List of book IDs to export/import")
    chapter_ids: Optional[List[int]] = Field(None, description="List of chapter IDs to export/import")
    include_binary_files: bool = Field(True, description="Embed base64-encoded binary files")

    class Config:
        json_schema_extra = {
            "example": {
                "book_ids": [1, 2],
                "chapter_ids": None,
                "include_binary_files": True,
            }
        }


class ImportRequest(BaseModel):
    """Request schema for import operations."""

    merge_strategy: str = Field(
        "skip_duplicates",
        description="Merge strategy: 'replace', 'merge', or 'skip_duplicates'",
    )
    preserve_uuids: bool = Field(
        False,
        description="Preserve UUIDs from import (useful for migrations)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "merge_strategy": "skip_duplicates",
                "preserve_uuids": False,
            }
        }


class ImportSummary(BaseModel):
    """Summary of import operation results."""

    books_created: int = 0
    books_updated: int = 0
    books_skipped: int = 0
    chapters_created: int = 0
    chapters_updated: int = 0
    chapters_skipped: int = 0
    images_created: int = 0
    images_skipped: int = 0
    audios_created: int = 0
    audios_skipped: int = 0
    errors: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "books_created": 2,
                "books_updated": 0,
                "books_skipped": 0,
                "chapters_created": 5,
                "chapters_updated": 1,
                "chapters_skipped": 0,
                "images_created": 120,
                "images_skipped": 0,
                "audios_created": 3,
                "audios_skipped": 0,
                "errors": [],
            }
        }


class ExportMetadata(BaseModel):
    """Metadata about the export."""

    format_version: str = Field("1.0", description="Export format version")
    exported_at: datetime = Field(default_factory=datetime.utcnow, description="Export timestamp")
    application_version: str = Field(description="Application version")
    total_books: int = Field(0, description="Total number of books")
    total_chapters: int = Field(0, description="Total number of chapters")
    total_images: int = Field(0, description="Total number of images")
    total_audios: int = Field(0, description="Total number of audio files")
    estimated_size_bytes: Optional[int] = Field(None, description="Estimated JSON size in bytes")
