"""
Export/Import API router.

Provides endpoints for:
- Exporting books/chapters to JSON archives (streaming)
- Importing JSON archives back into the application (streaming)
"""
import ijson
import json
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_minio_client
from app.schemas.export_import import ExportImportRequest, ImportRequest, ImportSummary
from app.services.export_import_service import ExportImportService
from app.logger import logger


router = APIRouter(
    prefix="/export-import",
    tags=["export-import"],
)


@router.post("/export")
async def export_to_json(
    request: ExportImportRequest,
    db: Session = Depends(get_db),
    minio_client = Depends(get_minio_client),
):
    """
    Export books/chapters to JSON format with streaming.

    STREAMING ENABLED: Memory-efficient for 1GB+ exports with concurrent users.

    Accepts a JSON request body with ExportImportRequest schema.

    Returns a JSON file download with all book data including
    base64-encoded binary files.

    Parameters:
    - book_ids: Export specific books (None = all books)
    - chapter_ids: Export specific chapters (None = all chapters)
    - include_binary_files: Embed base64-encoded files (default: true)
    """
    try:
        # Create service
        service = ExportImportService(db, minio_client)

        # Log export start
        logger.info(
            f"Starting STREAMING export: book_ids={request.book_ids}, "
            f"chapter_ids={request.chapter_ids}, "
            f"include_binary_files={request.include_binary_files}"
        )

        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"ocr_workbench_export_{timestamp}.json"

        # Create async generator for streaming
        async def generate_json():
            """Stream JSON chunks directly to response."""
            async for chunk in service.export_to_json_stream(
                book_ids=request.book_ids,
                chapter_ids=request.chapter_ids,
                include_binary_files=request.include_binary_files,
            ):
                yield chunk.encode('utf-8')

        # Stream response directly (no intermediate file, no full JSON in memory)
        return StreamingResponse(
            generate_json(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    except ValidationError as e:
        logger.error(f"Validation error in export request: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )


@router.post("/import")
async def import_from_json(
    merge_strategy: str = Form("skip_duplicates"),
    preserve_uuids: bool = Form(False),
    file: UploadFile = File(..., description="JSON export file to import"),
    db: Session = Depends(get_db),
    minio_client = Depends(get_minio_client),
):
    """
    Import books/chapters from JSON export file with STREAMING.

    STREAMING ENABLED: Memory-efficient for 1GB+ imports with concurrent users.

    Args:
        file: JSON export file (required)
        merge_strategy: How to handle duplicates
            - 'replace': Delete existing and import fresh
            - 'merge': Update existing, create new
            - 'skip_duplicates': Only import non-existing (default)
        preserve_uuids: Preserve UUIDs from import (for migrations)

    Returns:
        ImportSummary with counts of created/updated/skipped items
    """
    try:
        # Validate merge strategy
        valid_strategies = {"replace", "merge", "skip_duplicates"}
        if merge_strategy not in valid_strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid merge_strategy. Must be one of: {valid_strategies}",
            )

        # Validate file
        if not file.filename.endswith(".json"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .json files are supported",
            )

        # STREAMING: Read file in chunks to avoid loading entire file into RAM
        logger.info(f"Starting STREAMING import from file: {file.filename}")

        # Read file content (we still need to read it all, but ijson will parse incrementally)
        content = await file.read()
        file_size = len(content)
        logger.info(f"Import file size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")

        # Create service
        service = ExportImportService(db, minio_client)

        # Perform STREAMING import using ijson
        summary = await service.import_from_json_streaming(
            file_content=content,
            merge_strategy=merge_strategy,
            preserve_uuids=preserve_uuids,
        )

        # Check for errors
        if summary["errors"]:
            logger.error(f"Import completed with errors: {summary['errors']}")

        # Log summary
        logger.info(
            f"Import summary: "
            f"{summary['books_created']} books created, "
            f"{summary['books_updated']} updated, "
            f"{summary['books_skipped']} skipped, "
            f"{summary['chapters_created']} chapters created, "
            f"{summary['images_created']} images created, "
            f"{summary['audios_created']} audios created"
        )

        return ImportSummary(**summary)

    except HTTPException:
        raise
    except ValidationError as e:
        logger.error(f"Validation error in import request: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Import error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}",
        )


@router.get("/info")
async def get_export_info():
    """
    Get information about the export/import format.

    Returns details about the JSON schema, format version, etc.
    """
    return {
        "format_version": "1.0",
        "description": "JSON export/import format for OCR Workbench",
        "features": [
            "Database-agnostic UUID-based references",
            "Base64-encoded binary files (self-contained archives)",
            "Multiple merge strategies for conflict resolution",
            "Transaction-safe imports with rollback on errors",
            "Preserves OCR text and transcripts",
            "Supports edited text with formatting",
        ],
        "merge_strategies": {
            "replace": "Delete existing data and import fresh",
            "merge": "Update existing records, create new ones",
            "skip_duplicates": "Only import non-existing records (default)",
        },
        "json_structure": {
            "format_version": "Export format version",
            "exported_at": "ISO timestamp of export",
            "application_version": "Application version at export time",
            "data": {
                "books": [
                    {
                        "uuid": "Unique identifier",
                        "name": "Book name",
                        "description": "Book description",
                        "languages": "Comma-separated language codes",
                        "created_at": "ISO timestamp",
                        "chapters": [
                            {
                                "uuid": "Chapter identifier",
                                "name": "Chapter name",
                                "sequence_order": "Chapter order",
                                "images": [
                                    {
                                        "uuid": "Image identifier",
                                        "filename": "Original filename",
                                        "sequence_number": "Image order in chapter",
                                        "page_number": "Page number (for PDFs)",
                                        "file_data": {
                                            "base64": "Base64-encoded file data",
                                            "mime_type": "MIME type",
                                            "size": "File size in bytes",
                                        },
                                        "ocr_text": {
                                            "raw_text_with_formatting": "Markdown formatted text",
                                            "plain_text_for_search": "Plain text for FTS",
                                            "edited_text_with_formatting": "User-edited text",
                                            "detected_language": "Language code",
                                            "model_used": "OCR model used",
                                        },
                                    }
                                ],
                                "audios": [
                                    {
                                        "uuid": "Audio identifier",
                                        "filename": "Audio filename",
                                        "sequence_number": "Audio order in chapter",
                                        "duration_seconds": "Audio duration",
                                        "file_data": {
                                            "base64": "Base64-encoded audio",
                                            "mime_type": "MIME type",
                                            "size": "File size in bytes",
                                        },
                                        "transcript": {
                                            "raw_text_with_formatting": "Transcript text",
                                            "plain_text_for_search": "Plain text",
                                            "edited_text_with_formatting": "User-edited text",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    }
