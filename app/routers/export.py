"""Export endpoints for generating .docx and .txt files with OCR and transcript data."""
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from app.models.audio import Audio
from app.dependencies import get_current_user
from app.services.export_service import ExportService
from app.services.minio_service import MinIOService
from app.dependencies import get_minio_client
from app.schemas.export import ExportFolderRequest, ExportSelectionRequest
from app.logger import logger


router = APIRouter(prefix="/export", tags=["export"])


@router.post("/folder")
async def export_folder(
    request: ExportFolderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> FileResponse:
    """
    Export a book or chapter to .docx or .txt file.

    NO user verification - just verify book/chapter exist.
    All authenticated users can export any book/chapter.

    Args:
        request: Export request with book_id, optional chapter_id, format
        current_user: Authenticated user
        db: Database session
        minio_service: MinIO service for file downloads

    Returns:
        File download response

    Status:
        200: Export successful
        404: Book or chapter not found
        400: Invalid request parameters
    """
    logger.info(f"Export folder request from user {current_user.id}: book_id={request.book_id}, chapter_id={request.chapter_id}")

    # Verify book exists
    book = db.query(Book).filter(Book.id == request.book_id).first()
    if not book:
        logger.warning(f"Book not found: {request.book_id}")
        raise HTTPException(status_code=404, detail="Book not found")

    # Verify chapter exists if provided
    if request.chapter_id:
        chapter = (
            db.query(Chapter)
            .filter(Chapter.id == request.chapter_id, Chapter.book_id == request.book_id)
            .first()
        )
        if not chapter:
            logger.warning(f"Chapter not found: {request.chapter_id} in book {request.book_id}")
            raise HTTPException(status_code=404, detail="Chapter not found")

    # Validate format
    if request.format not in ["docx", "txt"]:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'docx' or 'txt'")

    # Generate export
    export_service = ExportService(minio_service)
    try:
        export_file_path = export_service.export_folder(
            db=db,
            book_id=request.book_id,
            chapter_id=request.chapter_id,
            format=request.format,
            include_images=request.include_images,
            include_audio_transcripts=request.include_audio_transcripts,
            include_page_breaks=request.include_page_breaks,
        )
    except Exception as e:
        logger.error(f"Failed to export: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate export: {str(e)}")

    # Determine file extension and media type
    ext = "docx" if request.format == "docx" else "txt"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if request.format == "docx"
        else "text/plain"
    )

    # Generate filename
    book_name = book.name.replace(" ", "_").replace("/", "_")
    if request.chapter_id:
        chapter = db.query(Chapter).filter(Chapter.id == request.chapter_id).first()
        chapter_name = chapter.name.replace(" ", "_").replace("/", "_")
        filename = f"{book_name}_{chapter_name}.{ext}"
    else:
        filename = f"{book_name}.{ext}"

    logger.info(f"Returning export file: {filename}")

    return FileResponse(
        path=export_file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/selection")
async def export_selection(
    request: ExportSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> FileResponse:
    """
    Export selected images and audios to .docx or .txt file.

    NO user verification - just verify images/audios exist.
    All authenticated users can export any images/audios.

    Args:
        request: Export request with image_ids, audio_ids, format
        current_user: Authenticated user
        db: Database session
        minio_service: MinIO service for file downloads

    Returns:
        File download response

    Status:
        200: Export successful
        404: Any image or audio not found
        400: Invalid request parameters
    """
    logger.info(
        f"Export selection request from user {current_user.id}: "
        f"images={len(request.image_ids or [])}, audios={len(request.audio_ids or [])}"
    )

    # Validate that at least one type is provided
    if not request.image_ids and not request.audio_ids:
        raise HTTPException(status_code=400, detail="Must provide either image_ids or audio_ids")

    # Verify all images exist
    if request.image_ids:
        images_count = db.query(Image).filter(Image.id.in_(request.image_ids)).count()
        if images_count != len(request.image_ids):
            logger.warning(f"Some images not found: expected {len(request.image_ids)}, got {images_count}")
            raise HTTPException(status_code=404, detail="One or more images not found")

    # Verify all audios exist
    if request.audio_ids:
        audios_count = db.query(Audio).filter(Audio.id.in_(request.audio_ids)).count()
        if audios_count != len(request.audio_ids):
            logger.warning(f"Some audios not found: expected {len(request.audio_ids)}, got {audios_count}")
            raise HTTPException(status_code=404, detail="One or more audios not found")

    # Validate format
    if request.format not in ["docx", "txt"]:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'docx' or 'txt'")

    # Generate export
    export_service = ExportService(minio_service)
    try:
        export_file_path = export_service.export_selection(
            db=db,
            image_ids=request.image_ids,
            audio_ids=request.audio_ids,
            format=request.format,
            include_images=request.include_images,
        )
    except Exception as e:
        logger.error(f"Failed to export selection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate export: {str(e)}")

    # Determine file extension and media type
    ext = "docx" if request.format == "docx" else "txt"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if request.format == "docx"
        else "text/plain"
    )
    filename = f"export_selection.{ext}"

    logger.info(f"Returning export file: {filename}")

    return FileResponse(
        path=export_file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
