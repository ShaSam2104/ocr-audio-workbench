"""Image upload and management routes - NO user_id filtering (fully shared)."""
import os
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.hierarchy import Chapter
from app.models.image import Image
from app.models.user import User
from app.schemas.image import ImageSchema
from app.dependencies import get_current_user, get_minio_client
from app.services.minio_service import MinIOService
from app.logger import logger

router = APIRouter(tags=["images"])

# Allowed image formats
ALLOWED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIMETYPES = {"image/jpeg", "image/png"}

# File size limit (100 MB)
MAX_FILE_SIZE = 100 * 1024 * 1024


def get_next_sequence_number(chapter_id: int, db: Session) -> int:
    """Get next sequence number for images in a chapter."""
    max_sequence = db.query(Image).filter(Image.chapter_id == chapter_id).order_by(Image.sequence_number.desc()).first()
    return (max_sequence.sequence_number + 1) if max_sequence else 1


def validate_image_file(file: UploadFile) -> tuple[bool, str]:
    """
    Validate uploaded image file.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check MIME type
    if file.content_type not in ALLOWED_MIMETYPES:
        return False, f"Invalid file format. Allowed: JPG, PNG. Got: {file.content_type}"
    
    # Check file extension
    if not file.filename:
        return False, "Filename is missing"
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_IMAGE_FORMATS:
        return False, f"Invalid file extension. Allowed: {', '.join(ALLOWED_IMAGE_FORMATS)}"
    
    return True, ""


@router.post("/chapters/{chapter_id}/images/upload", response_model=list[ImageSchema], status_code=status.HTTP_201_CREATED)
async def upload_images(
    chapter_id: int,
    files: list[UploadFile] = File(..., description="Image files to upload (JPG, PNG)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> list[ImageSchema]:
    """
    Upload images to a chapter and store in MinIO.
    
    - Validates chapter exists
    - Validates each file format (JPG, PNG only)
    - Uploads to MinIO immediately
    - Creates Image records with object_key pointing to MinIO
    - Returns [ImageSchema] with ocr_status="pending"
    
    Args:
        chapter_id: Chapter ID
        files: List of image files
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        List of created ImageSchema objects
    
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

    created_images = []
    uploaded_files = []  # Track files to delete later

    try:
        for file in files:
            # Validate file format
            is_valid, error_msg = validate_image_file(file)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg,
                )

            # Save to temporary location
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, file.filename or f"temp_{chapter_id}.png")
            
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

                # Create Image record (without uploading yet)
                # Get next sequence number
                sequence_number = get_next_sequence_number(chapter_id, db)
                
                # Prepare object key: images/{chapter_id}/{image_id}.{ext}
                # We need to save the record first to get the ID, then update object_key
                file_ext = Path(file.filename).suffix.lower()
                
                # Create image record with temporary object_key
                image = Image(
                    chapter_id=chapter_id,
                    filename=file.filename,
                    sequence_number=sequence_number,
                    object_key="",  # Will update after upload
                    ocr_status="pending",
                    is_cropped=False,
                )
                db.add(image)
                db.flush()  # Get the image ID without committing
                
                image_id = image.id
                object_key = f"images/{chapter_id}/{image_id}{file_ext}"

                # Upload to MinIO
                upload_result = await minio_service.upload_file(
                    bucket="images",
                    object_key=object_key,
                    file_path=temp_path,
                )

                # Update image record with MinIO metadata
                image.object_key = upload_result["object_key"]
                image.file_size = upload_result["file_size"]
                image.file_hash = upload_result["file_hash"]

                db.commit()
                db.refresh(image)

                created_images.append(ImageSchema.model_validate(image))
                logger.info(f"Image {image_id} uploaded: {object_key} ({upload_result['file_size']} bytes)")

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

    return created_images
