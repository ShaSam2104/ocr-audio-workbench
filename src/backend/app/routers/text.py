"""Text retrieval and update endpoints - NO audit trail (fully shared data)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user, get_minio_client
from app.models.user import User
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.schemas.ocr import OCRUpdateRequest
from app.schemas.transcript import AudioTranscriptUpdateRequest
from app.services.minio_service import MinIOService
from app.logger import logger

router = APIRouter(prefix="", tags=["text"])


# ============================================================================
# SCHEMAS
# ============================================================================


class OCRTextResponse(BaseModel):
    """Response schema for OCR text retrieval - includes image metadata and OCR text.
    
    Matches the structure from /books/{book_id}/chapters/{chapter_id}/images endpoint
    by including image details along with OCR text.
    """

    model_config = ConfigDict(from_attributes=True)

    # Image metadata
    image_id: int
    sequence_number: int  # Image sequence within chapter
    page_number: Optional[int] = None  # Physical page number if known
    ocr_status: str  # pending|processing|completed|failed
    chapter_id: int  # Which chapter this image belongs to
    filename: str  # Original filename
    
    # OCR text data
    raw_text_with_formatting: str  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text: str  # Plain text without formatting tags
    detected_language: Optional[str] = None  # Detected language code
    processing_time_ms: Optional[int] = None  # Time to process (milliseconds)
    model_used: Optional[str] = None  # Which model was used for extraction
    created_at: datetime  # When OCR was extracted
    
    # Image access
    image_url: Optional[str] = None  # Signed/presigned URL for image access (30 mins)
    
    # Manual edit fields (user corrections)
    edited_text_with_formatting: Optional[str] = None  # User-edited text with formatting
    edited_plain_text: Optional[str] = None  # User-edited plain text
    edited_at: Optional[datetime] = None  # When user last edited


class AudioTranscriptResponse(BaseModel):
    """Response schema for audio transcript retrieval - includes audio metadata and transcript.
    
    Matches the structure from /books/{book_id}/chapters/{chapter_id}/audios endpoint
    by including audio details along with transcript.
    """

    model_config = ConfigDict(from_attributes=True)

    # Audio metadata
    audio_id: int
    sequence_number: int  # Audio sequence within chapter
    chapter_id: int  # Which chapter this audio belongs to
    filename: str  # Original filename
    audio_format: Optional[str] = None  # File format (mp3, wav, etc.)
    transcription_status: str  # pending|processing|completed|failed
    
    # Transcript data
    raw_text_with_formatting: str  # Text with markdown tags
    plain_text: str  # Plain text without formatting tags
    detected_language: Optional[str] = None  # Detected language code
    processing_time_ms: Optional[int] = None  # Time to process (milliseconds)
    model_used: Optional[str] = None  # Which model was used for transcription
    duration_seconds: Optional[int] = None  # Original audio duration
    created_at: datetime  # When transcription was extracted
    
    # Audio access
    audio_url: Optional[str] = None  # Signed/presigned URL for audio access (30 mins)
    
    # Manual edit fields (user corrections)
    edited_text_with_formatting: Optional[str] = None  # User-edited text with formatting
    edited_plain_text: Optional[str] = None  # User-edited plain text
    edited_at: Optional[datetime] = None  # When user last edited


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/images/{image_id}/text", response_model=OCRTextResponse)
async def get_image_text(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
):
    """
    Retrieve OCR text for an image with complete image metadata.

    NO user verification - all authenticated users can access all images.
    Returns complete image details along with OCR text, matching the structure
    from /books/{book_id}/chapters/{chapter_id}/images endpoint.

    Args:
        image_id: Image ID
        current_user: Authenticated user (any user can access any image)
        db: Database session
        minio_service: MinIO service for generating signed URLs

    Returns:
        Complete image details with OCR text (includes user edits if available) + signed image URL
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

    # Generate presigned URL for image (30 mins = 1800 seconds)
    image_url = None
    try:
        image_url = await minio_service.get_presigned_url(
            bucket="images",
            object_key=image.object_key,
            expiration=1800,  # 30 minutes
        )
        logger.debug(f"Generated presigned URL for image {image_id}")
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL for image {image_id}: {e}")
        # Don't fail the request, just skip the URL

    logger.debug(f"OCR text retrieved for image {image_id}")

    return OCRTextResponse(
        # Image metadata
        image_id=image_id,
        sequence_number=image.sequence_number,
        page_number=image.page_number,
        ocr_status=image.ocr_status,
        chapter_id=image.chapter_id,
        filename=image.filename,
        # OCR text data
        raw_text_with_formatting=ocr_text.raw_text_with_formatting,
        plain_text=ocr_text.plain_text_for_search,
        detected_language=ocr_text.detected_language,
        processing_time_ms=ocr_text.processing_time_ms,
        model_used=getattr(ocr_text, 'model_used', None),
        created_at=ocr_text.created_at,
        # Image access
        image_url=image_url,
        # Manual edit fields
        edited_text_with_formatting=ocr_text.edited_text_with_formatting,
        edited_plain_text=ocr_text.edited_plain_text,
        edited_at=ocr_text.edited_at,
    )


@router.put("/images/{image_id}/text", response_model=OCRTextResponse)
async def update_image_text(
    image_id: int,
    request: OCRUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually update OCR text for an image (user correction).

    Stores the user-edited text in separate columns (edited_text_with_formatting, edited_plain_text).
    Original auto-extracted text remains unchanged for comparison.

    Args:
        image_id: Image ID
        request: OCRUpdateRequest with corrected text
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated OCR text response with user edits
        404 if image or OCR not found
    """
    logger.debug(f"Updating OCR text for image {image_id}")

    # Verify image exists
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
        logger.warning(f"OCR text not found for image {image_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OCR text not found for image {image_id}",
        )

    # Update with user-corrected text
    ocr_text.edited_text_with_formatting = request.text_with_formatting
    # If plain_text not provided, strip markdown from formatted text
    ocr_text.edited_plain_text = request.plain_text or request.text_with_formatting.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    ocr_text.edited_at = datetime.utcnow()

    db.commit()
    db.refresh(ocr_text)

    logger.info(f"OCR text updated for image {image_id}")

    return OCRTextResponse(
        # Image metadata
        image_id=image_id,
        sequence_number=image.sequence_number,
        page_number=image.page_number,
        ocr_status=image.ocr_status,
        chapter_id=image.chapter_id,
        filename=image.filename,
        # OCR text data
        raw_text_with_formatting=ocr_text.raw_text_with_formatting,
        plain_text=ocr_text.plain_text_for_search,
        detected_language=ocr_text.detected_language,
        processing_time_ms=ocr_text.processing_time_ms,
        model_used=getattr(ocr_text, 'model_used', None),
        created_at=ocr_text.created_at,
        # Image access - not needed on update but can be added if needed
        image_url=None,
        # Manual edit fields
        edited_text_with_formatting=ocr_text.edited_text_with_formatting,
        edited_plain_text=ocr_text.edited_plain_text,
        edited_at=ocr_text.edited_at,
    )


@router.get("/audio/{audio_id}/transcript", response_model=AudioTranscriptResponse)
async def get_audio_transcript(
    audio_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
):
    """
    Retrieve transcription text for an audio file with complete audio metadata and signed URL.

    NO user verification - all authenticated users can access all audios.
    Returns complete audio details along with transcript, matching the structure
    from /books/{book_id}/chapters/{chapter_id}/audios endpoint.
    Includes presigned URL for audio access (valid for 30 minutes).

    Args:
        audio_id: Audio ID
        current_user: Authenticated user (any user can access any audio)
        db: Database session
        minio_service: MinIO service for generating signed URLs

    Returns:
        Complete audio details with transcript (includes user edits if available) and signed URL
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

    # Generate presigned URL for audio (30 mins = 1800 seconds)
    audio_url = None
    try:
        audio_url = await minio_service.get_presigned_url(
            bucket="audio",
            object_key=audio.object_key,
            expiration=1800,  # 30 minutes
        )
        logger.debug(f"Generated presigned URL for audio {audio_id}")
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL for audio {audio_id}: {e}")
        # Don't fail the request, just skip the URL

    logger.debug(f"Transcript retrieved for audio {audio_id}")

    return AudioTranscriptResponse(
        # Audio metadata
        audio_id=audio_id,
        sequence_number=audio.sequence_number,
        chapter_id=audio.chapter_id,
        filename=audio.filename,
        audio_format=audio.audio_format,
        transcription_status=audio.transcription_status,
        # Transcript data
        raw_text_with_formatting=transcript.raw_text_with_formatting,
        plain_text=transcript.plain_text_for_search,
        detected_language=transcript.detected_language,
        processing_time_ms=transcript.processing_time_ms,
        model_used=getattr(transcript, 'model_used', None),
        duration_seconds=audio.duration_seconds,
        created_at=transcript.created_at,
        # Audio access
        audio_url=audio_url,
        # Manual edit fields
        edited_text_with_formatting=transcript.edited_text_with_formatting,
        edited_plain_text=transcript.edited_plain_text,
        edited_at=transcript.edited_at,
    )


@router.put("/audio/{audio_id}/transcript", response_model=AudioTranscriptResponse)
async def update_audio_transcript(
    audio_id: int,
    request: AudioTranscriptUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually update audio transcript (user correction).

    Stores the user-edited text in separate columns (edited_text_with_formatting, edited_plain_text).
    Original auto-extracted text remains unchanged for comparison.

    Args:
        audio_id: Audio ID
        request: AudioTranscriptUpdateRequest with corrected transcript
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated transcript response with user edits
        404 if audio or transcript not found
    """
    logger.debug(f"Updating transcript for audio {audio_id}")

    # Verify audio exists
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
        logger.warning(f"Transcript not found for audio {audio_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript not found for audio {audio_id}",
        )

    # Update with user-corrected transcript
    transcript.edited_text_with_formatting = request.text_with_formatting
    # If plain_text not provided, strip markdown from formatted text
    transcript.edited_plain_text = request.plain_text or request.text_with_formatting.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    transcript.edited_at = datetime.utcnow()

    db.commit()
    db.refresh(transcript)

    logger.info(f"Transcript updated for audio {audio_id}")

    return AudioTranscriptResponse(
        # Audio metadata
        audio_id=audio_id,
        sequence_number=audio.sequence_number,
        chapter_id=audio.chapter_id,
        filename=audio.filename,
        audio_format=audio.audio_format,
        transcription_status=audio.transcription_status,
        # Transcript data
        raw_text_with_formatting=transcript.raw_text_with_formatting,
        plain_text=transcript.plain_text_for_search,
        detected_language=transcript.detected_language,
        processing_time_ms=transcript.processing_time_ms,
        model_used=getattr(transcript, 'model_used', None),
        duration_seconds=audio.duration_seconds,
        created_at=transcript.created_at,
        # Audio access - not needed on update but can be added if needed
        audio_url=None,
        # Manual edit fields
        edited_text_with_formatting=transcript.edited_text_with_formatting,
        edited_plain_text=transcript.edited_plain_text,
        edited_at=transcript.edited_at,
    )
