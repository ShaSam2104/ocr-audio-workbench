"""OCR processing endpoints with background task support."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.database import get_db
from app.dependencies import get_current_user, get_minio_client
from app.models.user import User
from app.models.image import Image
from app.models.ocr import OCRText
from app.services.background_tasks import get_ocr_task_manager, ImageStatus, TaskStatus
from app.services.minio_service import MinIOService
from app.services.gemini_service import GeminiService
from app.config import get_settings
from app.logger import logger
import tempfile
from pathlib import Path
import time

router = APIRouter(prefix="/ocr", tags=["ocr"])

# Global ThreadPoolExecutor for background image processing
_executor = ThreadPoolExecutor(max_workers=5)


# ============================================================================
# SCHEMAS
# ============================================================================


class OCRProcessRequest(BaseModel):
    """OCR processing request."""
    image_ids: List[int] = Field(..., description="List of image IDs to process", min_length=1)
    model: str = Field(default="higher", description="Model tier to use: 'higher' or 'lower'")


class ImageProcessingStatus(BaseModel):
    """Status of a single image in a task."""
    image_id: int
    status: str = Field(..., description="queued|processing|completed|failed")
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    processed_at: Optional[str] = None
    error: Optional[str] = None


class OCRStatusResponse(BaseModel):
    """OCR task status response."""
    task_id: str
    status: str = Field(..., description="queued|processing|completed|failed")
    total_images: int
    completed_count: int
    progress_percent: int
    images: List[ImageProcessingStatus]


class OCRProcessResponse(BaseModel):
    """OCR processing initiated response (202 Accepted)."""
    task_id: str
    status: str = "queued"
    total_images: int
    message: str


# ============================================================================
# BACKGROUND PROCESSING LOGIC
# ============================================================================


def _process_images_in_background(
    task_id: str,
    image_ids: List[int],
    minio_service: MinIOService,
    gemini_service: GeminiService,
    task_manager,
    languages: Optional[List[str]] = None,
    model_tier: str = "higher",
):
    """
    Background job to process images for OCR.
    Runs in a thread pool.
    
    Args:
        task_id: Task ID for tracking
        image_ids: List of image IDs to process
        minio_service: MinIO service for file operations
        gemini_service: Gemini service for OCR
        task_manager: OCR task manager for status tracking
        languages: Optional list of language codes from the book
        model_tier: Model tier to use ("higher" or "lower")
    """
    # Create a new database session for this background thread
    from app.database import SessionLocal
    db = SessionLocal()
    
    try:
        logger.info(f"Background OCR job started for task {task_id} with {len(image_ids)} images using model_tier={model_tier}")
        task_manager.start_processing(task_id)

        for image_id in image_ids:
            try:
                # Mark image as processing
                task_manager.start_image_processing(task_id, image_id)

                # Verify image exists
                image: Optional[Image] = db.query(Image).filter(Image.id == image_id).first()
                if not image:
                    task_manager.fail_image(task_id, image_id, f"Image {image_id} not found")
                    continue

                logger.debug(f"Processing image {image_id} for task {task_id}")

                # Download image from MinIO to temp file
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    tmp_path = tmp_file.name

                try:
                    # Download from MinIO (run async in event loop since we're in a thread)
                    asyncio.run(minio_service.download_file(
                        bucket="images",
                        object_key=image.object_key,
                        local_path=tmp_path,
                    ))

                    # Extract text using Gemini with language context and model selection
                    raw_text, detected_language, processing_time_ms, model_used = gemini_service.extract_text_from_image(
                        tmp_path,
                        languages=languages,
                        model_tier=model_tier,
                    )

                    # Check if OCRText already exists for this image
                    existing_ocr = db.query(OCRText).filter(OCRText.image_id == image_id).first()
                    if existing_ocr:
                        # Update existing record
                        existing_ocr.raw_text_with_formatting = raw_text
                        existing_ocr.plain_text_for_search = raw_text  # In production, remove markdown tags
                        existing_ocr.detected_language = detected_language
                        existing_ocr.processing_time_ms = processing_time_ms
                        existing_ocr.model_used = model_used
                    else:
                        # Create new OCRText record
                        ocr_text = OCRText(
                            image_id=image_id,
                            raw_text_with_formatting=raw_text,
                            plain_text_for_search=raw_text,  # In production, remove markdown tags
                            detected_language=detected_language,
                            processing_time_ms=processing_time_ms,
                            model_used=model_used,
                        )
                        db.add(ocr_text)

                    # Update image status
                    image.ocr_status = "completed"
                    image.detected_language = detected_language
                    db.commit()

                    # Mark as completed in task manager
                    task_manager.complete_image(task_id, image_id)
                    logger.info(f"Image {image_id} OCR completed in {processing_time_ms}ms using {model_used}")

                finally:
                    # Clean up temp file
                    Path(tmp_path).unlink(missing_ok=True)

            except Exception as e:
                error_msg = f"Error processing image {image_id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                task_manager.fail_image(task_id, image_id, error_msg)
                
                # Try to update image status in DB
                try:
                    db.rollback()  # Rollback any failed transaction
                    image = db.query(Image).filter(Image.id == image_id).first()
                    if image:
                        image.ocr_status = "failed"
                        db.commit()
                except Exception as db_error:
                    logger.error(f"Failed to update image status in DB: {db_error}")

        logger.info(f"Background OCR job completed for task {task_id}")
    
    finally:
        # Always close the database session
        db.close()


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/process", response_model=OCRProcessResponse, status_code=202)
async def process_images_ocr(
    request: OCRProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
):
    """
    Start OCR processing for images.
    
    Returns 202 IMMEDIATELY - does not wait for processing.
    Background job submitted to ThreadPoolExecutor.
    Use GET /ocr/status/{task_id} to poll for progress.
    
    Args:
        request: OCR request with image IDs
        current_user: Authenticated user
        db: Database session
        minio_service: MinIO service
        
    Returns:
        202 ACCEPTED with task_id for polling
        400 if images not found
    """
    logger.info(f"OCR process request for {len(request.image_ids)} images from user {current_user.id}")

    # Validate all images exist and get book languages
    existing_images = db.query(Image).filter(Image.id.in_(request.image_ids)).all()
    if len(existing_images) != len(request.image_ids):
        missing_ids = set(request.image_ids) - {img.id for img in existing_images}
        logger.warning(f"Some images not found: {missing_ids}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Images not found: {missing_ids}",
        )

    # Get book languages from the first image's chapter's book
    languages = None
    if existing_images:
        from app.models.hierarchy import Book
        first_image = existing_images[0]
        chapter = first_image.chapter
        if chapter and chapter.book:
            if chapter.book.languages:
                languages = [lang.strip() for lang in chapter.book.languages.split(",")]
            logger.debug(f"Book languages: {languages}")

    # Create task in task manager
    task_manager = get_ocr_task_manager()
    task_id = task_manager.create_task(request.image_ids)

    # Update images to "processing" status in DB
    db.query(Image).filter(Image.id.in_(request.image_ids)).update(
        {"ocr_status": "processing"},
        synchronize_session=False,
    )
    db.commit()

    # Submit background job (don't wait for result)
    settings = get_settings()
    gemini_service = GeminiService(api_key=settings.gemini_api_key)

    # Validate model selection
    model_tier = request.model if request.model in ["higher", "lower"] else "higher"

    # Submit to thread pool - fire and forget
    _executor.submit(
        _process_images_in_background,
        task_id,
        request.image_ids,
        minio_service,
        gemini_service,
        task_manager,
        languages=languages,
        model_tier=model_tier,
    )

    logger.info(f"OCR task {task_id} submitted to background queue with model_tier={model_tier}")

    return OCRProcessResponse(
        task_id=task_id,
        status="queued",
        total_images=len(request.image_ids),
        message="Processing started",
    )


@router.get("/status/{task_id}", response_model=OCRStatusResponse)
async def get_ocr_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get real-time status of an OCR task.
    
    Polls for progress on background processing.
    Frontend can call this every 2 seconds to show progress.
    
    Args:
        task_id: Task ID from POST /ocr/process
        current_user: Authenticated user
        
    Returns:
        Task status with per-image progress
        404 if task not found
    """
    task_manager = get_ocr_task_manager()
    task = task_manager.get_task_status(task_id)

    if not task:
        logger.warning(f"Task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}",
        )

    # Convert task to response
    response_images = [
        ImageProcessingStatus(
            image_id=img.image_id,
            status=img.status.value,
            queued_at=img.queued_at.isoformat() if img.queued_at else None,
            started_at=img.started_at.isoformat() if img.started_at else None,
            processed_at=img.processed_at.isoformat() if img.processed_at else None,
            error=img.error,
        )
        for img in task.images
    ]

    return OCRStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        total_images=task.total_images,
        completed_count=task.completed_count,
        progress_percent=task.progress_percent,
        images=response_images,
    )
