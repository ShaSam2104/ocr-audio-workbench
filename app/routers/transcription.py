"""Audio transcription endpoints with background task support."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.database import get_db
from app.dependencies import get_current_user, get_minio_client
from app.models.user import User
from app.models.audio import Audio
from app.models.transcript import AudioTranscript
from app.services.audio_task_manager import get_audio_task_manager, AudioStatus, TaskStatus
from app.services.minio_service import MinIOService
from app.services.gemini_service import GeminiService
from app.config import get_settings
from app.logger import logger
import tempfile
from pathlib import Path
import time

router = APIRouter(prefix="/audio", tags=["audio"])

# Global ThreadPoolExecutor for background audio processing
_executor = ThreadPoolExecutor(max_workers=5)


# ============================================================================
# SCHEMAS
# ============================================================================


class AudioTranscriptionRequest(BaseModel):
    """Audio transcription request."""
    audio_ids: List[int] = Field(..., description="List of audio IDs to process", min_length=1)
    language_hint: Optional[str] = Field(None, description="Optional language hint (e.g., 'en', 'hi', 'gu')")


class AudioProcessingStatus(BaseModel):
    """Status of a single audio in a task."""
    audio_id: int
    status: str = Field(..., description="queued|processing|completed|failed")
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    processed_at: Optional[str] = None
    error: Optional[str] = None


class AudioTranscriptionStatusResponse(BaseModel):
    """Audio transcription task status response."""
    task_id: str
    status: str = Field(..., description="queued|processing|completed|failed")
    total_audios: int
    completed_count: int
    progress_percent: int
    audios: List[AudioProcessingStatus]


class AudioTranscriptionResponse(BaseModel):
    """Audio transcription initiated response (202 Accepted)."""
    task_id: str
    status: str = "queued"
    total_audios: int
    message: str


# ============================================================================
# BACKGROUND PROCESSING LOGIC
# ============================================================================


def _process_audios_in_background(
    task_id: str,
    audio_ids: List[int],
    language_hint: Optional[str],
    db: Session,
    minio_service: MinIOService,
    gemini_service: GeminiService,
    task_manager,
):
    """
    Background job to process audios for transcription.
    Runs in a thread pool.
    
    Args:
        task_id: Task ID for tracking
        audio_ids: List of audio IDs to process
        language_hint: Optional language hint for transcription
        db: Database session
        minio_service: MinIO service for file operations
        gemini_service: Gemini service for transcription
        task_manager: Audio task manager for status tracking
    """
    logger.info(f"Background audio transcription job started for task {task_id} with {len(audio_ids)} audios")
    task_manager.start_processing(task_id)

    for audio_id in audio_ids:
        try:
            # Mark audio as processing
            task_manager.start_audio_processing(task_id, audio_id)

            # Verify audio exists
            audio: Optional[Audio] = db.query(Audio).filter(Audio.id == audio_id).first()
            if not audio:
                task_manager.fail_audio(task_id, audio_id, f"Audio {audio_id} not found")
                continue

            logger.debug(f"Processing audio {audio_id} for task {task_id}")

            # Download audio from MinIO to temp file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            try:
                # Download from MinIO (run async in event loop since we're in a thread)
                asyncio.run(minio_service.download_file(
                    bucket="audio",
                    object_key=audio.object_key,
                    local_path=tmp_path,
                ))

                # Transcribe using Gemini audio mode
                raw_text, detected_language, processing_time_ms = gemini_service.transcribe_audio(
                    tmp_path,
                    language_hint=language_hint,
                )

                # Store transcript result in database
                transcript = AudioTranscript(
                    audio_id=audio_id,
                    raw_text_with_formatting=raw_text,
                    plain_text_for_search=raw_text,  # In production, remove markdown tags
                    detected_language=detected_language,
                    processing_time_ms=processing_time_ms,
                )
                db.add(transcript)

                # Update audio status
                audio.transcription_status = "completed"
                audio.detected_language = detected_language
                db.commit()

                # Mark as completed in task manager
                task_manager.complete_audio(task_id, audio_id)
                logger.info(f"Audio {audio_id} transcription completed in {processing_time_ms}ms")

            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            error_msg = f"Error processing audio {audio_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            task_manager.fail_audio(task_id, audio_id, error_msg)
            
            # Try to update audio status in DB
            try:
                audio = db.query(Audio).filter(Audio.id == audio_id).first()
                if audio:
                    audio.transcription_status = "failed"
                    db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update audio status in DB: {db_error}")

    logger.info(f"Background audio transcription job completed for task {task_id}")


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/transcribe", response_model=AudioTranscriptionResponse, status_code=202)
async def transcribe_audios(
    request: AudioTranscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start audio transcription for audios.
    
    Returns 202 IMMEDIATELY - does not wait for processing.
    Background job submitted to ThreadPoolExecutor.
    Use GET /audio/transcription/status/{task_id} to poll for progress.
    
    Args:
        request: Transcription request with audio IDs
        current_user: Authenticated user
        db: Database session
        
    Returns:
        202 ACCEPTED with task_id for polling
        400 if audios not found
    """
    logger.info(f"Audio transcription request for {len(request.audio_ids)} audios from user {current_user.id}")

    # Validate all audios exist
    existing_audios = db.query(Audio).filter(Audio.id.in_(request.audio_ids)).all()
    if len(existing_audios) != len(request.audio_ids):
        missing_ids = set(request.audio_ids) - {audio.id for audio in existing_audios}
        logger.warning(f"Some audios not found: {missing_ids}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audios not found: {missing_ids}",
        )

    # Create task in task manager
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task(request.audio_ids)

    # Update audios to "processing" status in DB
    db.query(Audio).filter(Audio.id.in_(request.audio_ids)).update(
        {"transcription_status": "processing"},
        synchronize_session=False,
    )
    db.commit()

    # Submit background job (don't wait for result)
    settings = get_settings()
    minio_service = get_minio_client()
    gemini_service = GeminiService(api_key=settings.gemini_api_key)

    # Submit to thread pool - fire and forget
    _executor.submit(
        _process_audios_in_background,
        task_id,
        request.audio_ids,
        request.language_hint,
        db,
        minio_service,
        gemini_service,
        task_manager,
    )

    logger.info(f"Audio transcription task {task_id} submitted to background queue")

    return AudioTranscriptionResponse(
        task_id=task_id,
        status="queued",
        total_audios=len(request.audio_ids),
        message="Transcription started",
    )


@router.get("/transcription/status/{task_id}", response_model=AudioTranscriptionStatusResponse)
async def get_transcription_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get real-time status of an audio transcription task.
    
    Polls for progress on background processing.
    Frontend can call this every 2 seconds to show progress.
    
    Args:
        task_id: Task ID from POST /audio/transcribe
        current_user: Authenticated user
        
    Returns:
        Task status with per-audio progress
        404 if task not found
    """
    task_manager = get_audio_task_manager()
    task = task_manager.get_task_status(task_id)

    if not task:
        logger.warning(f"Task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}",
        )

    # Convert task to response
    response_audios = [
        AudioProcessingStatus(
            audio_id=audio.audio_id,
            status=audio.status.value,
            queued_at=audio.queued_at.isoformat() if audio.queued_at else None,
            started_at=audio.started_at.isoformat() if audio.started_at else None,
            processed_at=audio.processed_at.isoformat() if audio.processed_at else None,
            error=audio.error,
        )
        for audio in task.audios
    ]

    return AudioTranscriptionStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        total_audios=task.total_audios,
        completed_count=task.completed_count,
        progress_percent=task.progress_percent,
        audios=response_audios,
    )
