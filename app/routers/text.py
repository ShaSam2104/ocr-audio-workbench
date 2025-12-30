"""Text retrieval endpoints - NO audit trail (fully shared data)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.logger import logger

router = APIRouter(prefix="", tags=["text"])


# ============================================================================
# SCHEMAS
# ============================================================================


class OCRTextResponse(BaseModel):
    """Response schema for OCR text retrieval - NO audit fields."""

    model_config = ConfigDict(from_attributes=True)

    image_id: int
    raw_text_with_formatting: str  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text: str  # Plain text without formatting tags
    detected_language: Optional[str] = None
    created_at: datetime  # When OCR was extracted


class AudioTranscriptResponse(BaseModel):
    """Response schema for audio transcript retrieval - NO audit fields."""

    model_config = ConfigDict(from_attributes=True)

    audio_id: int
    raw_text_with_formatting: str  # Text with markdown tags
    plain_text: str  # Plain text without formatting tags
    detected_language: Optional[str] = None
    duration_seconds: Optional[int] = None  # Original audio duration
    created_at: datetime  # When transcription was extracted


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/images/{image_id}/text", response_model=OCRTextResponse)
async def get_image_text(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve OCR text for an image.

    NO user verification - all authenticated users can access all images.
    NO audit trail - no extracted_by or extracted_at fields.

    Args:
        image_id: Image ID
        current_user: Authenticated user (any user can access any image)
        db: Database session

    Returns:
        OCR text with formatting
        404 if image not found or OCR not completed
    """
    logger.debug(f"Retrieving OCR text for image {image_id}")

    # Verify image exists (NO user scoping)
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        logger.warning(f"Image {image_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {image_id} not found",
        )

    # Get OCR text for this image
    ocr_text = db.query(OCRText).filter(OCRText.image_id == image_id).first()
    if not ocr_text:
        logger.warning(f"OCR text not found for image {image_id} (may not be processed yet)")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OCR text not found for image {image_id}",
        )

    logger.debug(f"OCR text retrieved for image {image_id}")

    return OCRTextResponse(
        image_id=image_id,
        raw_text_with_formatting=ocr_text.raw_text_with_formatting,
        plain_text=ocr_text.plain_text_for_search,
        detected_language=ocr_text.detected_language,
        created_at=ocr_text.created_at,
    )


@router.get("/audio/{audio_id}/transcript", response_model=AudioTranscriptResponse)
async def get_audio_transcript(
    audio_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve transcription text for an audio file.

    NO user verification - all authenticated users can access all audios.
    NO audit trail - no extracted_by or extracted_at fields.

    Args:
        audio_id: Audio ID
        current_user: Authenticated user (any user can access any audio)
        db: Database session

    Returns:
        Audio transcript with formatting
        404 if audio not found or transcription not completed
    """
    logger.debug(f"Retrieving transcript for audio {audio_id}")

    # Verify audio exists (NO user scoping)
    audio = db.query(Audio).filter(Audio.id == audio_id).first()
    if not audio:
        logger.warning(f"Audio {audio_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio {audio_id} not found",
        )

    # Get transcript for this audio
    transcript = db.query(AudioTranscript).filter(AudioTranscript.audio_id == audio_id).first()
    if not transcript:
        logger.warning(f"Transcript not found for audio {audio_id} (may not be processed yet)")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript not found for audio {audio_id}",
        )

    logger.debug(f"Transcript retrieved for audio {audio_id}")

    return AudioTranscriptResponse(
        audio_id=audio_id,
        raw_text_with_formatting=transcript.raw_text_with_formatting,
        plain_text=transcript.plain_text_for_search,
        detected_language=transcript.detected_language,
        duration_seconds=audio.duration_seconds,
        created_at=transcript.created_at,
    )
