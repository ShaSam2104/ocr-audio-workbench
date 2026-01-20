"""Audio upload and management routes - NO user_id filtering (fully shared)."""
import os
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile
import librosa
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.hierarchy import Chapter
from app.models.audio import Audio
from app.models.user import User
from app.schemas.audio import AudioSchema
from app.schemas.response import MessageResponse
from app.dependencies import get_current_user, get_minio_client
from app.services.minio_service import MinIOService
from app.logger import logger

router = APIRouter(tags=["audios"])

# Allowed audio formats
ALLOWED_AUDIO_FORMATS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
ALLOWED_MIMETYPES = {
    "audio/mpeg",  # MP3
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",  # M4A
    "audio/ogg",
    "audio/flac",
}

# File size limit (500 MB for audio)
MAX_FILE_SIZE = 500 * 1024 * 1024


def get_next_sequence_number(chapter_id: int, db: Session) -> int:
    """Get next sequence number for audio files in a chapter."""
    max_sequence = db.query(Audio).filter(Audio.chapter_id == chapter_id).order_by(Audio.sequence_number.desc()).first()
    return (max_sequence.sequence_number + 1) if max_sequence else 1


def validate_audio_file(file: UploadFile) -> tuple[bool, str]:
    """
    Validate uploaded audio file.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check MIME type
    if file.content_type not in ALLOWED_MIMETYPES:
        return False, f"Invalid audio format. Allowed: MP3, WAV, M4A, OGG, FLAC. Got: {file.content_type}"
    
    # Check file extension
    if not file.filename:
        return False, "Filename is missing"
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_AUDIO_FORMATS:
        return False, f"Invalid file extension. Allowed: {', '.join(ALLOWED_AUDIO_FORMATS)}"
    
    return True, ""


def get_audio_format(filename: str) -> str:
    """Extract audio format from filename."""
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext if ext in {"mp3", "wav", "m4a", "ogg", "flac"} else "unknown"


def extract_audio_duration(file_path: str) -> int:
    """
    Extract audio duration in seconds using librosa.
    
    Returns:
        Duration in seconds (rounded to nearest integer)
    
    Raises:
        Exception: If audio cannot be loaded
    """
    try:
        # Load audio file (without loading the entire file into memory for sr parameter)
        y, sr = librosa.load(file_path, sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        return int(round(duration))
    except Exception as e:
        logger.warning(f"Failed to extract duration from {file_path}: {e}")
        # Return None if duration extraction fails
        return None


@router.post("/chapters/{chapter_id}/audios/upload", response_model=list[AudioSchema], status_code=status.HTTP_201_CREATED)
async def upload_audios(
    chapter_id: int,
    files: list[UploadFile] = File(..., description="Audio files to upload (MP3, WAV, M4A, OGG, FLAC)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> list[AudioSchema]:
    """
    Upload audio files to a chapter and store in MinIO.
    
    - Validates chapter exists
    - Validates each file format (MP3, WAV, M4A, OGG, FLAC only)
    - Extracts audio metadata (duration)
    - Uploads to MinIO immediately
    - Creates Audio records with object_key pointing to MinIO
    - Returns [AudioSchema] with transcription_status="pending"
    
    Args:
        chapter_id: Chapter ID
        files: List of audio files
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        List of created AudioSchema objects
    
    Raises:
        HTTPException: 404 if chapter not found, 400 if file validation fails
    """
    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )

    if not files or len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    created_audios = []
    uploaded_files = []  # Track files to delete later

    try:
        for file in files:
            # Validate file format
            is_valid, error_msg = validate_audio_file(file)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg,
                )

            # Save to temporary location
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, file.filename or f"temp_{chapter_id}.mp3")
            
            try:
                # Write uploaded file to temp location
                file_content = await file.read()
                
                # Check file size
                if len(file_content) > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File size exceeds {MAX_FILE_SIZE / (1024 * 1024):.0f} MB limit",
                    )

                with open(temp_path, "wb") as f:
                    f.write(file_content)
                
                uploaded_files.append(temp_path)

                # Extract audio metadata
                duration_seconds = extract_audio_duration(temp_path)
                audio_format = get_audio_format(file.filename)

                # Get next sequence number
                sequence_number = get_next_sequence_number(chapter_id, db)
                
                # Prepare object key: audio/{chapter_id}/{audio_id}.{ext}
                file_ext = Path(file.filename).suffix.lower()
                
                # Create audio record with temporary object_key
                audio = Audio(
                    chapter_id=chapter_id,
                    filename=file.filename,
                    sequence_number=sequence_number,
                    object_key="",  # Will update after upload
                    audio_format=audio_format,
                    duration_seconds=duration_seconds,
                    transcription_status="pending",
                )
                db.add(audio)
                db.flush()  # Get the audio ID without committing
                
                audio_id = audio.id
                object_key = f"audio/{chapter_id}/{audio_id}{file_ext}"

                # Upload to MinIO
                upload_result = await minio_service.upload_file(
                    bucket="audio",
                    object_key=object_key,
                    file_path=temp_path,
                )

                # Update audio record with MinIO metadata
                audio.object_key = upload_result["object_key"]
                audio.file_size = upload_result["file_size"]

                db.commit()
                db.refresh(audio)

                created_audios.append(AudioSchema.model_validate(audio))
                logger.info(
                    f"Audio {audio_id} uploaded: {object_key} ({upload_result['file_size']} bytes, {duration_seconds}s)"
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error uploading file {file.filename}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to upload {file.filename}: {str(e)}",
                )

    finally:
        # Delete temporary files
        for temp_path in uploaded_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.debug(f"Deleted temp file: {temp_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")

    return created_audios


@router.delete("/audios/{audio_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_audio(
    audio_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> MessageResponse:
    """
    Delete an audio file from a chapter and its related transcript data.
    
    - Deletes the audio record from database
    - Deletes the transcript record (if exists) through cascade
    - Deletes the audio file from MinIO
    
    Args:
        audio_id: Audio ID to delete
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        MessageResponse with success message
    
    Raises:
        HTTPException: 404 if audio not found
    """
    # Find the audio
    audio = db.query(Audio).filter(Audio.id == audio_id).first()
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio with id {audio_id} not found",
        )
    
    # Store info for logging
    object_key = audio.object_key
    chapter_id = audio.chapter_id
    
    try:
        # Delete from MinIO
        if object_key:
            await minio_service.delete_file(bucket="audio", object_key=object_key)
            logger.info(f"Deleted audio file from MinIO: {object_key}")
        
        # Delete from database (cascade will delete AudioTranscript)
        db.delete(audio)
        db.commit()
        
        logger.info(f"Deleted audio {audio_id} and its transcript data from chapter {chapter_id}")
        return MessageResponse(message=f"Audio {audio_id} and related transcript data deleted successfully")
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting audio {audio_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete audio: {str(e)}",
        )


@router.delete("/chapters/{chapter_id}/audios", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_all_audios_in_chapter(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> MessageResponse:
    """
    Delete all audio files in a chapter along with their transcript data.
    
    - Finds all audios in the chapter
    - Deletes each audio file from MinIO
    - Deletes all audio records from database
    - Cascades delete to transcript records
    
    Args:
        chapter_id: Chapter ID
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        MessageResponse with count of deleted audios
    
    Raises:
        HTTPException: 404 if chapter not found
    """
    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )
    
    try:
        # Get all audios in chapter
        audios = db.query(Audio).filter(Audio.chapter_id == chapter_id).all()
        
        if not audios:
            return MessageResponse(message=f"No audio files found in chapter {chapter_id}")
        
        # Delete each audio from MinIO
        for audio in audios:
            if audio.object_key:
                try:
                    await minio_service.delete_file(bucket="audio", object_key=audio.object_key)
                    logger.debug(f"Deleted audio file from MinIO: {audio.object_key}")
                except Exception as e:
                    logger.warning(f"Failed to delete MinIO file {audio.object_key}: {e}")
        
        # Delete all audios from database (cascade will delete AudioTranscript)
        audio_count = len(audios)
        for audio in audios:
            db.delete(audio)
        
        db.commit()
        logger.info(f"Deleted {audio_count} audio files and their transcript data from chapter {chapter_id}")
        
        return MessageResponse(message=f"Deleted {audio_count} audio file(s) and their transcript data from chapter {chapter_id}")
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting audios from chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete audio files: {str(e)}",
        )

