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
from app.schemas.image import ImageSchema, BatchImageReorderSchema
from app.schemas.response import MessageResponse
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
    
    # file_ext = Path(file.filename).suffix.lower()
    # if file_ext not in ALLOWED_IMAGE_FORMATS:
    #     return False, f"Invalid file extension. Allowed: {', '.join(ALLOWED_IMAGE_FORMATS)}"
    
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
    logger.debug(f"[UPLOAD] Received upload request for chapter {chapter_id} with {len(files) if files else 0} files")
    
    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        logger.warning(f"[UPLOAD] Chapter {chapter_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )

    if not files or len(files) == 0:
        logger.warning(f"[UPLOAD] No files provided in request")
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
                logger.warning(f"[UPLOAD] File validation failed for {file.filename}: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg,
                )

            logger.debug(f"[UPLOAD] Processing file: {file.filename} (content_type: {file.content_type})")

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


@router.delete("/images/{image_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> MessageResponse:
    """
    Delete an image from a chapter and its related OCR data.
    
    - Deletes the image record from database
    - Deletes the OCR text record (if exists) through cascade
    - Deletes the image file from MinIO
    - Automatically renumbers remaining images' sequence numbers
    
    Args:
        image_id: Image ID to delete
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        MessageResponse with success message
    
    Raises:
        HTTPException: 404 if image not found
    """
    # Find the image
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with id {image_id} not found",
        )
    
    # Store info for logging
    object_key = image.object_key
    chapter_id = image.chapter_id
    deleted_sequence = image.sequence_number
    
    try:
        # Delete from MinIO
        if object_key:
            await minio_service.delete_file(bucket="images", object_key=object_key)
            logger.info(f"Deleted image file from MinIO: {object_key}")
        
        # Delete from database (cascade will delete OCRText)
        db.delete(image)
        db.flush()
        
        # Renumber remaining images' sequence numbers
        remaining_images = db.query(Image).filter(Image.chapter_id == chapter_id).order_by(Image.sequence_number).all()
        for idx, img in enumerate(remaining_images, start=1):
            img.sequence_number = idx
        
        db.commit()
        
        logger.info(f"Deleted image {image_id} (was at position {deleted_sequence}) and renumbered {len(remaining_images)} remaining images")
        return MessageResponse(message=f"Image deleted successfully. Renumbered {len(remaining_images)} remaining image(s)")
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting image {image_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete image: {str(e)}",
        )


@router.delete("/chapters/{chapter_id}/images", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_all_images_in_chapter(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> MessageResponse:
    """
    Delete all images in a chapter along with their OCR data.
    
    - Finds all images in the chapter
    - Deletes each image file from MinIO
    - Deletes all image records from database
    - Cascades delete to OCR text records
    
    Args:
        chapter_id: Chapter ID
        current_user: Current authenticated user
        db: Database session
        minio_service: MinIO service
    
    Returns:
        MessageResponse with count of deleted images
    
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
        # Get all images in chapter
        images = db.query(Image).filter(Image.chapter_id == chapter_id).all()
        
        if not images:
            return MessageResponse(message=f"No images found in chapter {chapter_id}")
        
        # Delete each image from MinIO
        for image in images:
            if image.object_key:
                try:
                    await minio_service.delete_file(bucket="images", object_key=image.object_key)
                    logger.debug(f"Deleted image file from MinIO: {image.object_key}")
                except Exception as e:
                    logger.warning(f"Failed to delete MinIO file {image.object_key}: {e}")
        
        # Delete all images from database (cascade will delete OCRText)
        image_count = len(images)
        for image in images:
            db.delete(image)
        
        db.commit()
        logger.info(f"Deleted {image_count} images and their OCR data from chapter {chapter_id}")
        
        return MessageResponse(message=f"Deleted {image_count} image(s) and their OCR data from chapter {chapter_id}")
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting images from chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete images: {str(e)}",
        )


@router.put("/chapters/{chapter_id}/images/reorder", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def reorder_images(
    chapter_id: int,
    request: BatchImageReorderSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Reorder images in a chapter by sequence position.
    
    Move images from one sequence position to another. Example:
    - Move the image at position 10 to position 1
    - All images in between shift accordingly to fill the gap
    - Frontend just deals with positions (1-N), not image IDs
    
    Request:
    ```json
    {
      "images": [
        {"current_sequence_number": 10, "new_sequence_number": 1}
      ]
    }
    ```
    
    Args:
        chapter_id: Chapter ID
        request: Batch reorder request with current and new positions
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        MessageResponse with count of updated images
    
    Raises:
        HTTPException: 404 if chapter not found, 400 if validation fails
    """
    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )
    
    if not request.images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images provided for reordering",
        )
    
    try:
        # Get all images in chapter, sorted by sequence_number
        all_images = db.query(Image).filter(Image.chapter_id == chapter_id).order_by(Image.sequence_number).all()
        
        if not all_images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No images found in this chapter",
            )
        
        # Create map of sequence_number -> image for quick lookup
        sequence_to_image = {img.sequence_number: img for img in all_images}
        total_images = len(all_images)
        
        logger.info(f"[REORDER] Chapter {chapter_id} has {total_images} images")
        logger.info(f"[REORDER] Request to move: {[(img.current_sequence_number, img.new_sequence_number) for img in request.images]}")
        
        # Verify all current sequence numbers exist and validate new sequence numbers
        for item in request.images:
            if item.current_sequence_number not in sequence_to_image:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No image at position {item.current_sequence_number}",
                )
            if item.new_sequence_number < 1 or item.new_sequence_number > total_images:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid position {item.new_sequence_number}. Must be between 1 and {total_images}",
                )
        
        # Create mapping of current_position -> new_position
        reorder_map = {item.current_sequence_number: item.new_sequence_number for item in request.images}
        
        # Use a simpler approach: build the new order directly
        # Create list of (position, image_id) for images being moved
        moved_images = [(reorder_map[seq], sequence_to_image[seq].id) for seq in reorder_map.keys()]
        
        # Create list of remaining images (not being moved)
        remaining_positions = [seq for seq in range(1, total_images + 1) if seq not in reorder_map]
        remaining_images = [sequence_to_image[seq].id for seq in remaining_positions]
        
        # Build the final order by placing moved images at their target positions
        final_order = [None] * total_images
        
        # Place moved images first
        for target_pos, image_id in moved_images:
            if final_order[target_pos - 1] is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Multiple images trying to move to position {target_pos}",
                )
            final_order[target_pos - 1] = image_id
        
        # Fill remaining positions with non-moved images in order
        remaining_idx = 0
        for pos in range(total_images):
            if final_order[pos] is None:
                final_order[pos] = remaining_images[remaining_idx]
                remaining_idx += 1
        
        # Create new_sequences mapping from this final order
        new_sequences = {}
        for position, image_id in enumerate(final_order, start=1):
            new_sequences[image_id] = position
        
        # Verify no duplicate sequence numbers
        sequence_values = list(new_sequences.values())
        if len(set(sequence_values)) != len(sequence_values):
            logger.error(f"[REORDER] Duplicate sequence numbers detected: {sequence_values}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reordering: resulting in duplicate sequence numbers",
            )
        
        # Update all sequence numbers
        for image in all_images:
            image.sequence_number = new_sequences[image.id]
        
        # Renormalize sequences to be contiguous [1, N]
        all_images.sort(key=lambda img: img.sequence_number)
        for idx, image in enumerate(all_images, start=1):
            image.sequence_number = idx
        
        db.commit()
        logger.info(f"[REORDER] Updated sequence numbers for {len(request.images)} image(s) in chapter {chapter_id}")
        logger.info(f"[REORDER] Final result: {[(img.id, img.sequence_number) for img in all_images]}")
        
        return MessageResponse(message=f"Reordered {len(request.images)} image(s)")
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error reordering images in chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reorder images: {str(e)}",
        )

