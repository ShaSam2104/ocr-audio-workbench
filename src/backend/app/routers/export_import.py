"""
Export/Import API router.

Provides endpoints for:
- Exporting books/chapters to JSON archives
- Importing JSON archives back into the application
"""
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
    Export books/chapters to JSON format.

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

        # Perform export
        logger.info(
            f"Starting export: book_ids={request.book_ids}, "
            f"chapter_ids={request.chapter_ids}, "
            f"include_binary_files={request.include_binary_files}"
        )

        export_data = await service.export_to_json(
            book_ids=request.book_ids,
            chapter_ids=request.chapter_ids,
            include_binary_files=request.include_binary_files,
        )

        # VALIDATION BEFORE JSON SERIALIZATION
        logger.info(f"=== VALIDATION BEFORE json.dumps() ===")
        books_before = export_data.get("data", {}).get("books", [])
        if books_before:
            first_book = books_before[0]
            chapters = first_book.get("chapters", [])
            if chapters:
                first_chapter = chapters[0]
                images = first_chapter.get("images", [])
                if images:
                    first_image = images[0]
                    if "file_data" in first_image:
                        b64_before = first_image["file_data"].get("base64", "")
                        logger.info(f"BEFORE json.dumps(): Base64 length = {len(b64_before)} chars")
                        logger.info(f"BEFORE json.dumps(): Last 100 chars = {b64_before[-100:]}")

        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        book_count = export_data.get("metadata", {}).get("total_books", 0)
        filename = f"ocr_workbench_export_{timestamp}_books{book_count}.json"

        # Convert to JSON string
        json_str = json.dumps(export_data, indent=2, ensure_ascii=False)

        # Log JSON size BEFORE writing
        logger.info(f"JSON export size: {len(json_str)} characters")

        # CRITICAL: Validate the JSON structure AFTER serialization
        # Check if JSON is valid and complete
        logger.info(f"=== VALIDATION AFTER json.dumps() ===")
        try:
            reparsed = json.loads(json_str)
            books = reparsed.get("data", {}).get("books", [])
            if books:
                first_book = books[0]
                chapters = first_book.get("chapters", [])
                if chapters:
                    first_chapter = chapters[0]
                    images = first_chapter.get("images", [])
                    if images:
                        first_image = images[0]
                        if "file_data" in first_image:
                            b64 = first_image["file_data"].get("base64", "")
                            logger.info(f"AFTER json.dumps(): Base64 length = {len(b64)} chars")
                            logger.info(f"AFTER json.dumps(): Last 100 chars = {b64[-100:]}")

                            # Compare with before
                            if 'b64_before' in locals():
                                if len(b64) != len(b64_before):
                                    logger.error(f"BASE64 LENGTH CHANGED during json.dumps()!")
                                    logger.error(f"Before: {len(b64_before)} chars, After: {len(b64)} chars")
                                elif b64 != b64_before:
                                    logger.error(f"BASE64 CONTENT CHANGED during json.dumps()!")
                                else:
                                    logger.info(f"VERIFIED: Base64 unchanged during json.dumps()")

                            # Check if base64 appears valid (ends with padding)
                            if b64.endswith('=') or len(b64) % 4 == 0:
                                logger.info("VALIDATION: Base64 looks valid (proper padding)")
                            else:
                                logger.error(f"VALIDATION ERROR: Base64 appears malformed! Last 100 chars: {b64[-100:]}")
        except Exception as e:
            logger.error(f"JSON validation failed: {e}")

        # Write to temp file for streaming (avoids loading large JSON into memory)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as tmp_file:
            tmp_file.write(json_str.encode("utf-8"))
            tmp_path = tmp_file.name

        file_size = os.path.getsize(tmp_path)
        logger.info(
            f"Export complete: {filename}, size={file_size} bytes"
        )

        # Stream the file in chunks (8KB chunks for efficient memory usage)
        def iterfile():
            with open(tmp_path, mode='rb') as f:
                while chunk := f.read(8192):  # 8KB chunks
                    yield chunk
            # Clean up temp file after streaming
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        return StreamingResponse(
            iterfile(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(file_size),
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
    Import books/chapters from JSON export file.

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

        # Read and parse JSON
        logger.info(f"Starting import from file: {file.filename}")
        content = await file.read()

        # Check file size (warn if very large)
        file_size = len(content)
        logger.info(f"Import file size: {file_size} bytes ({file_size / 1024:.1f} KB)")
        if file_size > 100 * 1024 * 1024:  # 100 MB
            logger.warning(f"Large import file: {file_size / 1024 / 1024:.1f} MB")

        try:
            json_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON file: {str(e)}",
            )

        # Validate JSON structure
        if "data" not in json_data or "books" not in json_data.get("data", {}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid export format: missing 'data.books' structure",
            )

        # Create service
        service = ExportImportService(db, minio_client)

        # Perform import
        summary = await service.import_from_json(
            json_data=json_data,
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
