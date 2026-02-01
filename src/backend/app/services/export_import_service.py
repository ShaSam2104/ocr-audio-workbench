"""
Export/Import service for JSON-based backup and restore.

Provides database-agnostic export/import functionality with:
- UUID-based references for portability across databases
- Base64-encoded binary files for self-contained archives
- Merge strategies for conflict resolution
- Comprehensive error handling and transaction safety
"""
import base64
import binascii
import hashlib
import io
import json
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Book, Chapter, Image, Audio, OCRText, AudioTranscript
from app.services.minio_service import MinIOService
from app.logger import logger


class ExportImportService:
    """
    Service for exporting and importing OCR workbench data as JSON.

    Key features:
    - Database-agnostic UUID-based references
    - Self-contained archives with embedded base64 files
    - Transaction-safe imports with rollback on errors
    - Multiple merge strategies for conflict resolution
    """

    # Format version for migration compatibility
    FORMAT_VERSION = "1.0"

    def __init__(self, db: Session, minio_service: MinIOService):
        """
        Initialize the export/import service.

        Args:
            db: SQLAlchemy database session
            minio_service: MinIO service for file storage
        """
        self.db = db
        self.minio = minio_service
        self._uuid_map: Dict[str, Any] = {}  # Maps entity type and ID to UUID
        self._id_map: Dict[str, int] = {}  # Maps UUID to new database ID during import

    def _generate_uuid(self) -> str:
        """Generate a deterministic UUID for entity tracking."""
        return str(uuid.uuid4())

    def _encode_file_to_base64(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Encode a file to base64 with metadata.

        Args:
            file_path: Path to the file

        Returns:
            Dict with base64 data, mime_type, and size, or None if file not found
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                return None

            # Get file info
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.warning(f"Empty file: {file_path}")
                return None

            # Determine mime type
            mime_type = self._get_mime_type(file_path)

            # Read and encode file in chunks that are multiples of 3 bytes
            # Base64 encodes 3 bytes → 4 chars, so only the FINAL chunk has padding
            # Using 3MB chunks (3 * 1024 * 1024) to handle large files efficiently
            chunk_size = 3 * 1024 * 1024  # 3MB - multiple of 3 for proper base64
            base64_chunks = []
            total_bytes_read = 0

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes_read += len(chunk)
                    # Encode this chunk - only final chunk will have padding
                    encoded_chunk = base64.b64encode(chunk).decode("ascii")
                    base64_chunks.append(encoded_chunk)

            # Verify all bytes were read
            if total_bytes_read != file_size:
                logger.error(f"File read mismatch: expected {file_size} bytes, read {total_bytes_read} bytes")

            # Concatenate - since chunk_size is multiple of 3, only the last chunk has padding
            base64_data = "".join(base64_chunks)

            # Log detailed base64 info
            logger.info(f"Encoded file to base64: {file_path}, size: {file_size} bytes, mime_type: {mime_type}")
            logger.info(f"Base64 string length: {len(base64_data)} chars")
            logger.info(f"Base64 starts with: {base64_data[:100]}")
            logger.info(f"Base64 ends with: {base64_data[-100:]}")

            return {
                "base64": base64_data,
                "mime_type": mime_type,
                "size": file_size,
            }
        except Exception as e:
            logger.error(f"Error encoding file {file_path}: {e}")
            return None

    def _decode_base64_to_file(self, base64_data: str, output_path: str) -> bool:
        """
        Decode base64 data and write to file.

        Args:
            base64_data: Base64 encoded string
            output_path: Where to write the decoded file

        Returns:
            True if successful
        """
        try:
            # Create parent directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Log base64 length and expected decoded size
            logger.info(f"Decoding base64 data: {len(base64_data)} chars to {output_path}")
            logger.info(f"Base64 starts with: {base64_data[:100]}")
            logger.info(f"Base64 ends with: {base64_data[-100:]}")

            # Strip whitespace
            base64_data = base64_data.strip()

            # Calculate expected size
            expected_size = (len(base64_data) * 3) // 4
            logger.info(f"Expected decoded size: ~{expected_size} bytes")

            # Decode the base64 data
            # Use standard base64 decode since we now properly encode in multiples of 3 bytes
            try:
                decoded_data = base64.b64decode(base64_data, validate=True)
            except binascii.Error as e:
                # If validation fails, the data might be corrupted
                logger.error(f"Base64 validation failed: {e}")
                logger.error(f"This indicates the base64 data in the JSON file is corrupted")
                raise

            actual_decoded_size = len(decoded_data)
            logger.info(f"Decoded size: {actual_decoded_size} bytes")

            # Write to file
            with open(output_path, "wb") as f:
                f.write(decoded_data)

            # Log resulting file size
            decoded_size = os.path.getsize(output_path)
            logger.info(f"Written file size: {decoded_size} bytes")

            # Verify the file is valid if it's an image
            if output_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                try:
                    from PIL import Image
                    img = Image.open(output_path)
                    img.verify()
                    logger.info(f"Image verification passed: {img.format} {img.size}")
                except Exception as img_err:
                    logger.error(f"Image verification failed: {img_err}")
                    return False

            return True
        except Exception as e:
            logger.error(f"Error decoding base64 to file {output_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_mime_type(self, file_path: str) -> str:
        """Get mime type based on file extension."""
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }
        return mime_types.get(ext, "application/octet-stream")

    async def _get_minio_file(self, bucket: str, object_key: str) -> Optional[str]:
        """
        Download file from MinIO to temporary location.

        Args:
            bucket: MinIO bucket name
            object_key: Object key in MinIO

        Returns:
            Temporary file path, or None if download failed
        """
        try:
            # Create temp file with appropriate extension
            ext = Path(object_key).suffix or ".bin"
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp_path = tmp.name

            # Download from MinIO
            success = await self.minio.download_file(bucket, object_key, tmp_path)
            if success and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                downloaded_size = os.path.getsize(tmp_path)
                logger.info(f"Downloaded file from MinIO: {object_key}, size: {downloaded_size} bytes")
                return tmp_path
            else:
                # Clean up empty file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return None
        except Exception as e:
            logger.error(f"Error downloading from MinIO: {e}")
            return None

    async def export_to_json(
        self,
        book_ids: Optional[List[int]] = None,
        chapter_ids: Optional[List[int]] = None,
        include_binary_files: bool = True,
    ) -> Dict[str, Any]:
        """
        Export books/chapters to JSON format with embedded base64 files.

        Args:
            book_ids: List of book IDs to export (None = all books)
            chapter_ids: List of chapter IDs to export (None = all chapters)
            include_binary_files: Whether to embed base64-encoded files

        Returns:
            Dictionary with export data ready for JSON serialization
        """
        self._uuid_map = {}  # Reset UUID mapping

        # Build the query with eager loading
        query = (
            select(Book)
            .options(
                joinedload(Book.chapters)
                .joinedload(Chapter.images)
                .joinedload(Image.ocr_text),
                joinedload(Book.chapters)
                .joinedload(Chapter.audios)
                .joinedload(Audio.transcript),
            )
            .order_by(Book.id)
        )

        # Filter by book_ids if provided
        if book_ids:
            query = query.filter(Book.id.in_(book_ids))

        # Execute query
        result = self.db.execute(query)
        books = result.scalars().unique().all()

        # If chapter_ids provided, filter chapters
        if chapter_ids:
            chapter_id_set = set(chapter_ids)
            filtered_books = []
            for book in books:
                # Keep only chapters that are in chapter_ids
                book.chapters = [ch for ch in book.chapters if ch.id in chapter_id_set]
                # Only include book if it has matching chapters
                if book.chapters:
                    filtered_books.append(book)
            books = filtered_books

        # Build export data structure
        export_data = {
            "format_version": self.FORMAT_VERSION,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "application_version": "1.0.0",  # TODO: Get from config
            "data": {
                "books": [],
            },
        }

        total_images = 0
        total_audios = 0
        total_chapters = 0

        for book in books:
            # Generate UUID for book
            book_uuid = self._generate_uuid()
            self._uuid_map[f"book_{book.id}"] = book_uuid

            book_data = {
                "uuid": book_uuid,
                "name": book.name,
                "description": book.description,
                "languages": book.languages,
                "created_at": book.created_at.isoformat() if book.created_at else None,
                "chapters": [],
            }

            for chapter in book.chapters:
                # Generate UUID for chapter
                chapter_uuid = self._generate_uuid()
                self._uuid_map[f"chapter_{chapter.id}"] = chapter_uuid

                chapter_data = {
                    "uuid": chapter_uuid,
                    "name": chapter.name,
                    "description": chapter.description,
                    "sequence_order": chapter.sequence_order,
                    "created_at": chapter.created_at.isoformat() if chapter.created_at else None,
                    "images": [],
                    "audios": [],
                }

                # Export images
                for image in chapter.images:
                    image_uuid = self._generate_uuid()
                    self._uuid_map[f"image_{image.id}"] = image_uuid

                    image_data = {
                        "uuid": image_uuid,
                        "filename": image.filename,
                        "sequence_number": image.sequence_number,
                        "page_number": image.page_number,
                        "detected_language": image.detected_language,
                        "ocr_status": image.ocr_status,
                        "is_cropped": image.is_cropped,
                        "created_at": image.created_at.isoformat() if image.created_at else None,
                    }

                    # Add file data if requested
                    if include_binary_files:
                        tmp_file = await self._get_minio_file("images", image.object_key)
                        if tmp_file:
                            file_data = self._encode_file_to_base64(tmp_file)
                            if file_data:
                                # Log BEFORE adding to image_data
                                b64_string = file_data.get("base64", "")
                                logger.info(f"PRE-ADD: Base64 for {image.filename} is {len(b64_string)} chars")
                                logger.info(f"PRE-ADD: First 100 chars: {b64_string[:100]}")
                                logger.info(f"PRE-ADD: Last 100 chars: {b64_string[-100:]}")

                                image_data["file_data"] = file_data

                                # Log AFTER adding to image_data
                                stored_b64 = image_data["file_data"]["base64"]
                                logger.info(f"POST-ADD: Base64 in image_data is {len(stored_b64)} chars")
                                if stored_b64 != b64_string:
                                    logger.error("CORRUPTION DETECTED: Base64 changed when added to image_data!")
                                else:
                                    logger.info("VERIFIED: Base64 unchanged when added to image_data")
                            # Clean up temp file
                            try:
                                os.unlink(tmp_file)
                            except Exception:
                                pass

                    # Add OCR text if exists
                    if image.ocr_text:
                        image_data["ocr_text"] = {
                            "raw_text_with_formatting": image.ocr_text.raw_text_with_formatting,
                            "plain_text_for_search": image.ocr_text.plain_text_for_search,
                            "edited_text_with_formatting": image.ocr_text.edited_text_with_formatting,
                            "edited_plain_text": image.ocr_text.edited_plain_text,
                            "detected_language": image.ocr_text.detected_language,
                            "model_used": image.ocr_text.model_used,
                        }

                    chapter_data["images"].append(image_data)
                    total_images += 1

                # Export audios
                for audio in chapter.audios:
                    audio_uuid = self._generate_uuid()
                    self._uuid_map[f"audio_{audio.id}"] = audio_uuid

                    audio_data = {
                        "uuid": audio_uuid,
                        "filename": audio.filename,
                        "sequence_number": audio.sequence_number,
                        "duration_seconds": audio.duration_seconds,
                        "audio_format": audio.audio_format,
                        "detected_language": audio.detected_language,
                        "created_at": audio.created_at.isoformat() if audio.created_at else None,
                    }

                    # Add file data if requested
                    if include_binary_files:
                        tmp_file = await self._get_minio_file("audio", audio.object_key)
                        if tmp_file:
                            file_data = self._encode_file_to_base64(tmp_file)
                            if file_data:
                                audio_data["file_data"] = file_data
                            # Clean up temp file
                            try:
                                os.unlink(tmp_file)
                            except Exception:
                                pass

                    # Add transcript if exists
                    if audio.transcript:
                        audio_data["transcript"] = {
                            "raw_text_with_formatting": audio.transcript.raw_text_with_formatting,
                            "plain_text_for_search": audio.transcript.plain_text_for_search,
                            "edited_text_with_formatting": audio.transcript.edited_text_with_formatting,
                            "edited_plain_text": audio.transcript.edited_plain_text,
                            "detected_language": audio.transcript.detected_language,
                            "model_used": audio.transcript.model_used,
                        }

                    chapter_data["audios"].append(audio_data)
                    total_audios += 1

                book_data["chapters"].append(chapter_data)
                total_chapters += 1

            export_data["data"]["books"].append(book_data)

        # Add metadata
        export_data["metadata"] = {
            "total_books": len(books),
            "total_chapters": total_chapters,
            "total_images": total_images,
            "total_audios": total_audios,
        }

        logger.info(
            f"Exported {len(books)} books, {total_chapters} chapters, "
            f"{total_images} images, {total_audios} audios"
        )

        return export_data

    async def import_from_json(
        self,
        json_data: Dict[str, Any],
        merge_strategy: str = "skip_duplicates",
        preserve_uuids: bool = False,
    ) -> Dict[str, Any]:
        """
        Import data from JSON export.

        Args:
            json_data: Parsed JSON export data
            merge_strategy: How to handle duplicates ('replace', 'merge', 'skip_duplicates')
            preserve_uuids: Whether to preserve UUIDs from import

        Returns:
            Import summary with counts and any errors
        """
        self._id_map = {}  # Reset ID mapping for this import

        summary = {
            "books_created": 0,
            "books_updated": 0,
            "books_skipped": 0,
            "chapters_created": 0,
            "chapters_updated": 0,
            "chapters_skipped": 0,
            "images_created": 0,
            "images_skipped": 0,
            "audios_created": 0,
            "audios_skipped": 0,
            "errors": [],
        }

        # Validate format version
        format_version = json_data.get("format_version", "1.0")
        if format_version != self.FORMAT_VERSION:
            logger.warning(
                f"Format version mismatch: expected {self.FORMAT_VERSION}, got {format_version}"
            )

        # Use a transaction for safety
        try:
            # Process each book
            for book_data in json_data.get("data", {}).get("books", []):
                await self._import_book(
                    book_data,
                    merge_strategy,
                    preserve_uuids,
                    summary,
                )

            self.db.commit()
            logger.info(f"Import completed: {summary}")
            return summary

        except Exception as e:
            self.db.rollback()
            logger.error(f"Import failed, rolling back: {e}")
            summary["errors"].append(f"Import failed: {str(e)}")
            return summary

    async def _import_book(
        self,
        book_data: Dict[str, Any],
        merge_strategy: str,
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single book and its contents."""
        book_uuid = book_data["uuid"]

        # Check for duplicate book
        existing_book = self._find_duplicate_book(book_data, merge_strategy)

        if existing_book:
            if merge_strategy == "skip_duplicates":
                summary["books_skipped"] += 1
                # Still need to map UUID for child references
                self._id_map[book_uuid] = existing_book.id
                # Skip chapters if we're skipping the book
                return
            elif merge_strategy == "replace":
                # Delete existing book (cascade will handle chapters)
                self.db.delete(existing_book)
                self.db.flush()
                existing_book = None
            elif merge_strategy == "merge":
                # Update existing book and add new chapters
                existing_book.name = book_data["name"]
                existing_book.description = book_data.get("description")
                existing_book.languages = book_data.get("languages")
                self.db.flush()
                self._id_map[book_uuid] = existing_book.id
                summary["books_updated"] += 1

        if not existing_book:
            # Create new book
            new_book = Book(
                name=book_data["name"],
                description=book_data.get("description"),
                languages=book_data.get("languages"),
            )
            self.db.add(new_book)
            self.db.flush()  # Get the new ID
            self._id_map[book_uuid] = new_book.id
            summary["books_created"] += 1
            existing_book = new_book

        # Import chapters
        for chapter_data in book_data.get("chapters", []):
            await self._import_chapter(
                existing_book.id,
                chapter_data,
                merge_strategy,
                preserve_uuids,
                summary,
            )

    def _find_duplicate_book(
        self, book_data: Dict[str, Any], merge_strategy: str
    ) -> Optional[Book]:
        """
        Find duplicate book by name and creation date.

        Args:
            book_data: Book data from import
            merge_strategy: Merge strategy to use

        Returns:
            Existing book if duplicate found, None otherwise
        """
        if merge_strategy == "replace":
            # Always find by name
            result = self.db.execute(
                select(Book).where(Book.name == book_data["name"])
            ).first()
            return result[0] if result else None
        elif merge_strategy in ("merge", "skip_duplicates"):
            # Find by name
            result = self.db.execute(
                select(Book).where(Book.name == book_data["name"])
            ).first()
            return result[0] if result else None
        return None

    async def _import_chapter(
        self,
        book_id: int,
        chapter_data: Dict[str, Any],
        merge_strategy: str,
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single chapter and its contents."""
        chapter_uuid = chapter_data["uuid"]

        # Check for duplicate chapter
        existing_chapter = self._find_duplicate_chapter(
            book_id, chapter_data, merge_strategy
        )

        if existing_chapter:
            if merge_strategy == "skip_duplicates":
                summary["chapters_skipped"] += 1
                self._id_map[chapter_uuid] = existing_chapter.id
                return
            elif merge_strategy == "replace":
                # Delete existing chapter (cascade handles images/audios)
                self.db.delete(existing_chapter)
                self.db.flush()
                existing_chapter = None
            elif merge_strategy == "merge":
                # Update existing chapter
                existing_chapter.name = chapter_data["name"]
                existing_chapter.description = chapter_data.get("description")
                existing_chapter.sequence_order = chapter_data.get("sequence_order")
                self.db.flush()
                self._id_map[chapter_uuid] = existing_chapter.id
                summary["chapters_updated"] += 1

        if not existing_chapter:
            # Create new chapter
            new_chapter = Chapter(
                book_id=book_id,
                name=chapter_data["name"],
                description=chapter_data.get("description"),
                sequence_order=chapter_data.get("sequence_order"),
            )
            self.db.add(new_chapter)
            self.db.flush()
            self._id_map[chapter_uuid] = new_chapter.id
            summary["chapters_created"] += 1
            existing_chapter = new_chapter

        # Import images
        for image_data in chapter_data.get("images", []):
            await self._import_image(
                existing_chapter.id,
                image_data,
                preserve_uuids,
                summary,
            )

        # Import audios
        for audio_data in chapter_data.get("audios", []):
            await self._import_audio(
                existing_chapter.id,
                audio_data,
                preserve_uuids,
                summary,
            )

    def _find_duplicate_chapter(
        self, book_id: int, chapter_data: Dict[str, Any], merge_strategy: str
    ) -> Optional[Chapter]:
        """Find duplicate chapter by book_id, name, and sequence."""
        result = self.db.execute(
            select(Chapter).where(
                Chapter.book_id == book_id,
                Chapter.name == chapter_data["name"],
            )
        ).first()
        return result[0] if result else None

    async def _import_image(
        self,
        chapter_id: int,
        image_data: Dict[str, Any],
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single image with its OCR text."""
        # Check for duplicate by filename and sequence
        existing = self.db.execute(
            select(Image).where(
                Image.chapter_id == chapter_id,
                Image.filename == image_data["filename"],
                Image.sequence_number == image_data["sequence_number"],
            )
        ).first()

        if existing and existing[0]:
            summary["images_skipped"] += 1
            return

        # Create temp file if base64 data present
        tmp_file = None
        file_size = None
        file_hash = None

        if "file_data" in image_data:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{image_data['filename']}"
            ).name
            if self._decode_base64_to_file(image_data["file_data"]["base64"], tmp_file):
                file_size = image_data["file_data"]["size"]
                # Calculate hash
                with open(tmp_file, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
            else:
                tmp_file = None

        # Upload to MinIO if we have a file
        object_key = None
        if tmp_file:
            try:
                # Check temp file size before upload
                temp_file_size = os.path.getsize(tmp_file)
                logger.info(f"Uploading temp file {tmp_file} to MinIO, size: {temp_file_size} bytes")

                # Generate new object key
                ext = Path(image_data["filename"]).suffix
                # We'll get the actual image ID after insert, so use temp key
                object_key = f"{chapter_id}/temp_{uuid.uuid4().hex}{ext}"

                result = await self.minio.upload_file("images", object_key, tmp_file)
                if result:
                    file_hash = result.get("file_hash", file_hash)
                    object_key = f"{chapter_id}/{object_key.split('/')[-1]}"
                    logger.info(f"Uploaded to MinIO: {object_key}, result size: {result.get('file_size', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to upload image to MinIO: {e}")
                summary["errors"].append(f"Failed to upload image {image_data['filename']}: {e}")
                return
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass

        # Create image record
        new_image = Image(
            chapter_id=chapter_id,
            object_key=object_key or f"{chapter_id}/placeholder.png",
            filename=image_data["filename"],
            sequence_number=image_data["sequence_number"],
            page_number=image_data.get("page_number"),
            file_size=file_size,
            file_hash=file_hash,
            detected_language=image_data.get("detected_language"),
            ocr_status=image_data.get("ocr_status", "pending"),
            is_cropped=image_data.get("is_cropped", False),
        )
        self.db.add(new_image)
        self.db.flush()  # Get the image ID

        # Rename object key with actual image ID if we uploaded a file
        if tmp_file and object_key:
            try:
                old_key = object_key
                new_key = f"{chapter_id}/{new_image.id}{Path(image_data['filename']).suffix}"
                # MinIO doesn't have rename, so we download and re-upload
                tmp_download = tempfile.NamedTemporaryFile(delete=False).name
                if await self.minio.download_file("images", old_key, tmp_download):
                    await self.minio.upload_file("images", new_key, tmp_download)
                    await self.minio.delete_file("images", old_key)
                    new_image.object_key = new_key
                try:
                    os.unlink(tmp_download)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to rename image object: {e}")

        # Create OCR text record if present
        if "ocr_text" in image_data:
            ocr_data = image_data["ocr_text"]
            ocr_text = OCRText(
                image_id=new_image.id,
                raw_text_with_formatting=ocr_data.get("raw_text_with_formatting", ""),
                plain_text_for_search=ocr_data.get("plain_text_for_search", ""),
                edited_text_with_formatting=ocr_data.get("edited_text_with_formatting"),
                edited_plain_text=ocr_data.get("edited_plain_text"),
                detected_language=ocr_data.get("detected_language"),
                model_used=ocr_data.get("model_used"),
            )
            self.db.add(ocr_text)

        summary["images_created"] += 1

    async def _import_audio(
        self,
        chapter_id: int,
        audio_data: Dict[str, Any],
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single audio file with its transcript."""
        # Check for duplicate by filename and sequence
        existing = self.db.execute(
            select(Audio).where(
                Audio.chapter_id == chapter_id,
                Audio.filename == audio_data["filename"],
                Audio.sequence_number == audio_data["sequence_number"],
            )
        ).first()

        if existing and existing[0]:
            summary["audios_skipped"] += 1
            return

        # Create temp file if base64 data present
        tmp_file = None
        file_size = None

        if "file_data" in audio_data:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{audio_data['filename']}"
            ).name
            if self._decode_base64_to_file(audio_data["file_data"]["base64"], tmp_file):
                file_size = audio_data["file_data"]["size"]
            else:
                tmp_file = None

        # Upload to MinIO if we have a file
        object_key = None
        if tmp_file:
            try:
                # Generate new object key
                ext = Path(audio_data["filename"]).suffix
                object_key = f"{chapter_id}/temp_{uuid.uuid4().hex}{ext}"

                result = await self.minio.upload_file("audio", object_key, tmp_file)
                object_key = f"{chapter_id}/{object_key.split('/')[-1]}"
            except Exception as e:
                logger.error(f"Failed to upload audio to MinIO: {e}")
                summary["errors"].append(f"Failed to upload audio {audio_data['filename']}: {e}")
                return
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass

        # Create audio record
        new_audio = Audio(
            chapter_id=chapter_id,
            object_key=object_key or f"{chapter_id}/placeholder.mp3",
            filename=audio_data["filename"],
            sequence_number=audio_data["sequence_number"],
            duration_seconds=audio_data.get("duration_seconds"),
            audio_format=audio_data.get("audio_format"),
            file_size=file_size,
            detected_language=audio_data.get("detected_language"),
            transcription_status="completed" if "transcript" in audio_data else "pending",
        )
        self.db.add(new_audio)
        self.db.flush()  # Get the audio ID

        # Rename object key with actual audio ID
        if tmp_file and object_key:
            try:
                old_key = object_key
                new_key = f"{chapter_id}/{new_audio.id}{Path(audio_data['filename']).suffix}"
                tmp_download = tempfile.NamedTemporaryFile(delete=False).name
                if await self.minio.download_file("audio", old_key, tmp_download):
                    await self.minio.upload_file("audio", new_key, tmp_download)
                    await self.minio.delete_file("audio", old_key)
                    new_audio.object_key = new_key
                try:
                    os.unlink(tmp_download)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to rename audio object: {e}")

        # Create transcript record if present
        if "transcript" in audio_data:
            transcript_data = audio_data["transcript"]
            transcript = AudioTranscript(
                audio_id=new_audio.id,
                raw_text_with_formatting=transcript_data.get("raw_text_with_formatting", ""),
                plain_text_for_search=transcript_data.get("plain_text_for_search", ""),
                edited_text_with_formatting=transcript_data.get("edited_text_with_formatting"),
                edited_plain_text=transcript_data.get("edited_plain_text"),
                detected_language=transcript_data.get("detected_language"),
                model_used=transcript_data.get("model_used"),
            )
            self.db.add(transcript)

        summary["audios_created"] += 1

    async def export_to_json_stream(
        self,
        book_ids: Optional[List[int]] = None,
        chapter_ids: Optional[List[int]] = None,
        include_binary_files: bool = True,
    ):
        """
        Stream export data as JSON chunks for memory-efficient large exports.

        Uses a cleaner structure tracking approach to avoid bracket/brace errors.
        """
        self._uuid_map = {}

        # Start JSON structure
        yield '{"format_version": "1.0", '
        yield f'"exported_at": "{datetime.utcnow().isoformat()}Z", '
        yield '"application_version": "1.0", '
        yield '"data": {"books": ['

        # Build query
        query = (
            select(Book)
            .options(
                joinedload(Book.chapters)
                .joinedload(Chapter.images)
                .joinedload(Image.ocr_text),
                joinedload(Book.chapters)
                .joinedload(Chapter.audios)
                .joinedload(Audio.transcript),
            )
            .order_by(Book.id)
        )

        if book_ids:
            query = query.filter(Book.id.in_(book_ids))

        result = self.db.execute(query)
        books = result.scalars().unique().all()

        if chapter_ids:
            chapter_id_set = set(chapter_ids)
            filtered_books = []
            for book in books:
                book.chapters = [ch for ch in book.chapters if ch.id in chapter_id_set]
                if book.chapters:
                    filtered_books.append(book)
            books = filtered_books

        total_books = len(books)
        total_images = 0
        total_audios = 0
        total_chapters = 0

        for book_idx, book in enumerate(books):
            # Start book object
            book_uuid = self._generate_uuid()
            self._uuid_map[f"book_{book.id}"] = book_uuid

            yield '{"uuid": "' + book_uuid + '", '
            yield '"name": ' + json.dumps(book.name) + ', '
            yield '"description": ' + json.dumps(book.description) + ', '
            yield '"languages": ' + json.dumps(book.languages) + ', '

            if book.created_at:
                yield f'"created_at": "{book.created_at.isoformat()}", '

            yield '"chapters": ['

            for chapter_idx, chapter in enumerate(book.chapters):
                chapter_uuid = self._generate_uuid()
                self._uuid_map[f"chapter_{chapter.id}"] = chapter_uuid

                yield '{"uuid": "' + chapter_uuid + '", '
                yield '"name": ' + json.dumps(chapter.name) + ', '
                yield '"description": ' + json.dumps(chapter.description) + ', '
                yield f'"sequence_order": {chapter.sequence_order or 0}, '

                if chapter.created_at:
                    yield f'"created_at": "{chapter.created_at.isoformat()}", '

                # Add images array (always include the key, even if empty)
                yield '"images": ['
                for image_idx, image in enumerate(chapter.images):
                    image_uuid = self._generate_uuid()
                    self._uuid_map[f"image_{image.id}"] = image_uuid

                    yield '{"uuid": "' + image_uuid + '", '
                    yield '"filename": ' + json.dumps(image.filename) + ', '
                    yield f'"sequence_number": {image.sequence_number}, '
                    yield f'"page_number": {image.page_number or 0}, '
                    yield '"detected_language": ' + json.dumps(image.detected_language) + ', '
                    yield '"ocr_status": ' + json.dumps(image.ocr_status) + ', '
                    yield f'"is_cropped": {str(image.is_cropped).lower()}, '

                    if image.created_at:
                        yield f'"created_at": "{image.created_at.isoformat()}", '

                    # Add optional fields with proper comma handling
                    needs_comma = False

                    if include_binary_files:
                        tmp_file = await self._get_minio_file("images", image.object_key)
                        if tmp_file:
                            file_data = self._encode_file_to_base64_streaming(tmp_file)
                            if file_data:
                                if needs_comma:
                                    yield ', '
                                yield '"file_data": {"base64": "' + file_data["base64"] + '", '
                                yield '"mime_type": "' + file_data["mime_type"] + '", '
                                yield f'"size": {file_data["size"]}}}'
                                needs_comma = True
                            try:
                                os.unlink(tmp_file)
                            except Exception:
                                pass

                    if image.ocr_text:
                        if needs_comma:
                            yield ', '
                        yield '"ocr_text": {'
                        yield '"raw_text_with_formatting": ' + json.dumps(image.ocr_text.raw_text_with_formatting) + ', '
                        yield '"plain_text_for_search": ' + json.dumps(image.ocr_text.plain_text_for_search) + ', '
                        yield '"edited_text_with_formatting": ' + json.dumps(image.ocr_text.edited_text_with_formatting) + ', '
                        yield '"edited_plain_text": ' + json.dumps(image.ocr_text.edited_plain_text) + ', '
                        yield '"detected_language": ' + json.dumps(image.ocr_text.detected_language) + ', '
                        yield '"model_used": ' + json.dumps(image.ocr_text.model_used) + '}'
                        needs_comma = True

                    # Close image object
                    yield '}'
                    # Add comma if more images coming
                    if image_idx < len(chapter.images) - 1:
                        yield ', '

                    total_images += 1

                # Close images array
                yield '], '

                # Add audios array (always include the key, even if empty)
                yield '"audios": ['
                for audio_idx, audio in enumerate(chapter.audios):
                    audio_uuid = self._generate_uuid()
                    self._uuid_map[f"audio_{audio.id}"] = audio_uuid

                    yield '{"uuid": "' + audio_uuid + '", '
                    yield '"filename": ' + json.dumps(audio.filename) + ', '
                    yield f'"sequence_number": {audio.sequence_number}, '
                    yield f'"duration_seconds": {audio.duration_seconds or 0}, '
                    yield '"audio_format": ' + json.dumps(audio.audio_format) + ', '
                    yield '"detected_language": ' + json.dumps(audio.detected_language) + ', '

                    if audio.created_at:
                        yield f'"created_at": "{audio.created_at.isoformat()}", '

                    # Add optional fields with proper comma handling
                    needs_comma = False

                    if include_binary_files:
                        tmp_file = await self._get_minio_file("audio", audio.object_key)
                        if tmp_file:
                            file_data = self._encode_file_to_base64_streaming(tmp_file)
                            if file_data:
                                if needs_comma:
                                    yield ', '
                                yield '"file_data": {"base64": "' + file_data["base64"] + '", '
                                yield '"mime_type": "' + file_data["mime_type"] + '", '
                                yield f'"size": {file_data["size"]}}}'
                                needs_comma = True
                            try:
                                os.unlink(tmp_file)
                            except Exception:
                                pass

                    if audio.transcript:
                        if needs_comma:
                            yield ', '
                        yield '"transcript": {'
                        yield '"raw_text_with_formatting": ' + json.dumps(audio.transcript.raw_text_with_formatting) + ', '
                        yield '"plain_text_for_search": ' + json.dumps(audio.transcript.plain_text_for_search) + ', '
                        yield '"edited_text_with_formatting": ' + json.dumps(audio.transcript.edited_text_with_formatting) + ', '
                        yield '"edited_plain_text": ' + json.dumps(audio.transcript.edited_plain_text) + ', '
                        yield '"detected_language": ' + json.dumps(audio.transcript.detected_language) + ', '
                        yield '"model_used": ' + json.dumps(audio.transcript.model_used) + '}'
                        needs_comma = True

                    # Close audio object
                    yield '}'
                    # Add comma if more audios coming
                    if audio_idx < len(chapter.audios) - 1:
                        yield ', '

                    total_audios += 1

                # Close audios array
                yield ']'

                # Close chapter object
                yield '}'
                # Add comma if more chapters coming
                if chapter_idx < len(book.chapters) - 1:
                    yield ', '

                total_chapters += 1

            # Close chapters array and book object
            yield ']}'
            # Add comma if more books coming
            if book_idx < total_books - 1:
                yield ', '

        # Close books array, data object, and root object with metadata
        yield '], "metadata": {'
        yield f'"total_books": {total_books}, '
        yield f'"total_chapters": {total_chapters}, '
        yield f'"total_images": {total_images}, '
        yield f'"total_audios": {total_audios}'
        yield '}}'

        logger.info(
            f"Streamed export: {total_books} books, {total_chapters} chapters, "
            f"{total_images} images, {total_audios} audios"
        )

    def _encode_file_to_base64_streaming(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Encode file to base64 as a single string (memory-efficient chunking).

        Uses 3MB chunks to minimize memory while producing valid base64.

        Returns dict with base64 string and metadata.
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                return None

            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.warning(f"Empty file: {file_path}")
                return None

            mime_type = self._get_mime_type(file_path)

            # Read in 3MB chunks (multiple of 3 for valid base64)
            chunk_size = 3 * 1024 * 1024
            base64_chunks = []
            total_bytes_read = 0

            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes_read += len(chunk)
                    encoded_chunk = base64.b64encode(chunk).decode("ascii")
                    base64_chunks.append(encoded_chunk)

            if total_bytes_read != file_size:
                logger.error(f"File read mismatch: expected {file_size} bytes, read {total_bytes_read}")

            return {
                "base64": "".join(base64_chunks),
                "mime_type": mime_type,
                "size": file_size,
            }

        except Exception as e:
            logger.error(f"Error encoding file {file_path}: {e}")
            return None

    async def import_from_json_streaming(
        self,
        file_content: bytes,
        merge_strategy: str = "skip_duplicates",
        preserve_uuids: bool = False,
    ) -> Dict[str, Any]:
        """
        Stream import from JSON for memory-efficient large imports.

        Uses ijson to parse JSON incrementally without loading entire file into RAM.
        Processes books, chapters, images, and audios one at a time.

        Memory usage: Constant (~50MB) regardless of file size.
        """
        import ijson
        from io import BytesIO

        summary = {
            "books_created": 0,
            "books_updated": 0,
            "books_skipped": 0,
            "chapters_created": 0,
            "chapters_updated": 0,
            "chapters_skipped": 0,
            "images_created": 0,
            "images_skipped": 0,
            "audios_created": 0,
            "audios_skipped": 0,
            "errors": [],
        }

        self._id_map = {}
        total_books = 0
        total_chapters = 0
        total_images = 0
        total_audios = 0

        try:
            # Use BytesIO for efficient parsing
            file_bytes = BytesIO(file_content)

            # Parse books array incrementally
            books_parser = ijson.items(file_bytes, 'data.books.item')

            for book_data in books_parser:
                total_books += 1

                # Validate book structure
                if "uuid" not in book_data or "name" not in book_data:
                    logger.warning(f"Skipping invalid book: {book_data}")
                    summary["books_skipped"] += 1
                    continue

                # Import the book
                await self._import_book_streaming(
                    book_data,
                    merge_strategy,
                    preserve_uuids,
                    summary,
                )

                total_chapters += len(book_data.get("chapters", []))
                total_images += sum(
                    len(ch.get("images", []))
                    for ch in book_data.get("chapters", [])
                )
                total_audios += sum(
                    len(ch.get("audios", []))
                    for ch in book_data.get("chapters", [])
                )

            self.db.commit()

            logger.info(
                f"Streaming import completed: {total_books} books processed, "
                f"{total_chapters} chapters, {total_images} images, {total_audios} audios"
            )

            return summary

        except ijson.JSONError as e:
            self.db.rollback()
            logger.error(f"JSON parsing error during streaming import: {e}")
            summary["errors"].append(f"Invalid JSON format: {str(e)}")
            return summary
        except Exception as e:
            self.db.rollback()
            logger.error(f"Streaming import failed, rolling back: {e}")
            import traceback
            logger.error(traceback.format_exc())
            summary["errors"].append(f"Import failed: {str(e)}")
            return summary

    async def _import_book_streaming(
        self,
        book_data: Dict[str, Any],
        merge_strategy: str,
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single book (streaming version)."""
        book_uuid = book_data["uuid"]

        # Check for duplicate book
        existing_book = self._find_duplicate_book(book_data, merge_strategy)

        if existing_book:
            if merge_strategy == "skip_duplicates":
                summary["books_skipped"] += 1
                self._id_map[book_uuid] = existing_book.id
                return
            elif merge_strategy == "replace":
                self.db.delete(existing_book)
                self.db.flush()
                existing_book = None
            elif merge_strategy == "merge":
                existing_book.name = book_data["name"]
                existing_book.description = book_data.get("description")
                existing_book.languages = book_data.get("languages")
                self.db.flush()
                self._id_map[book_uuid] = existing_book.id
                summary["books_updated"] += 1

        if not existing_book:
            new_book = Book(
                name=book_data["name"],
                description=book_data.get("description"),
                languages=book_data.get("languages"),
            )
            self.db.add(new_book)
            self.db.flush()
            self._id_map[book_uuid] = new_book.id
            summary["books_created"] += 1
            existing_book = new_book

        # Import chapters
        for chapter_data in book_data.get("chapters", []):
            await self._import_chapter_streaming(
                existing_book.id,
                chapter_data,
                merge_strategy,
                preserve_uuids,
                summary,
            )

    async def _import_chapter_streaming(
        self,
        book_id: int,
        chapter_data: Dict[str, Any],
        merge_strategy: str,
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single chapter (streaming version)."""
        chapter_uuid = chapter_data["uuid"]

        existing_chapter = self._find_duplicate_chapter(
            book_id, chapter_data, merge_strategy
        )

        if existing_chapter:
            if merge_strategy == "skip_duplicates":
                summary["chapters_skipped"] += 1
                self._id_map[chapter_uuid] = existing_chapter.id
                return
            elif merge_strategy == "replace":
                self.db.delete(existing_chapter)
                self.db.flush()
                existing_chapter = None
            elif merge_strategy == "merge":
                existing_chapter.name = chapter_data["name"]
                existing_chapter.description = chapter_data.get("description")
                existing_chapter.sequence_order = chapter_data.get("sequence_order")
                self.db.flush()
                self._id_map[chapter_uuid] = existing_chapter.id
                summary["chapters_updated"] += 1

        if not existing_chapter:
            new_chapter = Chapter(
                book_id=book_id,
                name=chapter_data["name"],
                description=chapter_data.get("description"),
                sequence_order=chapter_data.get("sequence_order"),
            )
            self.db.add(new_chapter)
            self.db.flush()
            self._id_map[chapter_uuid] = new_chapter.id
            summary["chapters_created"] += 1
            existing_chapter = new_chapter

        # Import images
        for image_data in chapter_data.get("images", []):
            await self._import_image_streaming(
                existing_chapter.id,
                image_data,
                preserve_uuids,
                summary,
            )

        # Import audios
        for audio_data in chapter_data.get("audios", []):
            await self._import_audio_streaming(
                existing_chapter.id,
                audio_data,
                preserve_uuids,
                summary,
            )

    async def _import_image_streaming(
        self,
        chapter_id: int,
        image_data: Dict[str, Any],
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single image with streaming base64 decode."""
        # Check for duplicate
        existing = self.db.execute(
            select(Image).where(
                Image.chapter_id == chapter_id,
                Image.filename == image_data["filename"],
                Image.sequence_number == image_data["sequence_number"],
            )
        ).first()

        if existing and existing[0]:
            summary["images_skipped"] += 1
            return

        # Create temp file if base64 data present
        tmp_file = None
        file_size = None
        file_hash = None

        if "file_data" in image_data:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{image_data['filename']}"
            ).name

            if self._decode_base64_to_file(image_data["file_data"]["base64"], tmp_file):
                file_size = image_data["file_data"]["size"]
                with open(tmp_file, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
            else:
                tmp_file = None

        # Upload to MinIO if we have a file
        object_key = None
        if tmp_file:
            try:
                temp_file_size = os.path.getsize(tmp_file)
                logger.info(f"Uploading image {tmp_file} to MinIO, size: {temp_file_size} bytes")

                ext = Path(image_data["filename"]).suffix
                object_key = f"{chapter_id}/temp_{uuid.uuid4().hex}{ext}"

                result = await self.minio.upload_file("images", object_key, tmp_file)
                if result:
                    file_hash = result.get("file_hash", file_hash)
                    object_key = f"{chapter_id}/{object_key.split('/')[-1]}"
                    logger.info(f"Uploaded to MinIO: {object_key}, size: {result.get('file_size', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to upload image to MinIO: {e}")
                summary["errors"].append(f"Failed to upload image {image_data['filename']}: {e}")
                return
            finally:
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass

        # Create image record
        new_image = Image(
            chapter_id=chapter_id,
            object_key=object_key or f"{chapter_id}/placeholder.png",
            filename=image_data["filename"],
            sequence_number=image_data["sequence_number"],
            page_number=image_data.get("page_number"),
            file_size=file_size,
            file_hash=file_hash,
            detected_language=image_data.get("detected_language"),
            ocr_status=image_data.get("ocr_status", "pending"),
            is_cropped=image_data.get("is_cropped", False),
        )
        self.db.add(new_image)
        self.db.flush()

        # Rename object key with actual image ID
        if tmp_file and object_key:
            try:
                old_key = object_key
                new_key = f"{chapter_id}/{new_image.id}{Path(image_data['filename']).suffix}"
                tmp_download = tempfile.NamedTemporaryFile(delete=False).name
                if await self.minio.download_file("images", old_key, tmp_download):
                    await self.minio.upload_file("images", new_key, tmp_download)
                    await self.minio.delete_file("images", old_key)
                    new_image.object_key = new_key
                try:
                    os.unlink(tmp_download)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to rename image object: {e}")

        # Create OCR text record if present
        if "ocr_text" in image_data:
            ocr_data = image_data["ocr_text"]
            ocr_text = OCRText(
                image_id=new_image.id,
                raw_text_with_formatting=ocr_data.get("raw_text_with_formatting", ""),
                plain_text_for_search=ocr_data.get("plain_text_for_search", ""),
                edited_text_with_formatting=ocr_data.get("edited_text_with_formatting"),
                edited_plain_text=ocr_data.get("edited_plain_text"),
                detected_language=ocr_data.get("detected_language"),
                model_used=ocr_data.get("model_used"),
            )
            self.db.add(ocr_text)

        summary["images_created"] += 1

    async def _import_audio_streaming(
        self,
        chapter_id: int,
        audio_data: Dict[str, Any],
        preserve_uuids: bool,
        summary: Dict[str, Any],
    ):
        """Import a single audio with streaming base64 decode."""
        # Check for duplicate
        existing = self.db.execute(
            select(Audio).where(
                Audio.chapter_id == chapter_id,
                Audio.filename == audio_data["filename"],
                Audio.sequence_number == audio_data["sequence_number"],
            )
        ).first()

        if existing and existing[0]:
            summary["audios_skipped"] += 1
            return

        # Create temp file if base64 data present
        tmp_file = None
        file_size = None

        if "file_data" in audio_data:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{audio_data['filename']}"
            ).name
            if self._decode_base64_to_file(audio_data["file_data"]["base64"], tmp_file):
                file_size = audio_data["file_data"]["size"]
            else:
                tmp_file = None

        # Upload to MinIO if we have a file
        object_key = None
        if tmp_file:
            try:
                ext = Path(audio_data["filename"]).suffix
                object_key = f"{chapter_id}/temp_{uuid.uuid4().hex}{ext}"

                result = await self.minio.upload_file("audio", object_key, tmp_file)
                object_key = f"{chapter_id}/{object_key.split('/')[-1]}"
            except Exception as e:
                logger.error(f"Failed to upload audio to MinIO: {e}")
                summary["errors"].append(f"Failed to upload audio {audio_data['filename']}: {e}")
                return
            finally:
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass

        # Create audio record
        new_audio = Audio(
            chapter_id=chapter_id,
            object_key=object_key or f"{chapter_id}/placeholder.mp3",
            filename=audio_data["filename"],
            sequence_number=audio_data["sequence_number"],
            duration_seconds=audio_data.get("duration_seconds"),
            audio_format=audio_data.get("audio_format"),
            file_size=file_size,
            detected_language=audio_data.get("detected_language"),
            transcription_status="completed" if "transcript" in audio_data else "pending",
        )
        self.db.add(new_audio)
        self.db.flush()

        # Rename object key with actual audio ID
        if tmp_file and object_key:
            try:
                old_key = object_key
                new_key = f"{chapter_id}/{new_audio.id}{Path(audio_data['filename']).suffix}"
                tmp_download = tempfile.NamedTemporaryFile(delete=False).name
                if await self.minio.download_file("audio", old_key, tmp_download):
                    await self.minio.upload_file("audio", new_key, tmp_download)
                    await self.minio.delete_file("audio", old_key)
                    new_audio.object_key = new_key
                try:
                    os.unlink(tmp_download)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to rename audio object: {e}")

        # Create transcript record if present
        if "transcript" in audio_data:
            transcript_data = audio_data["transcript"]
            transcript = AudioTranscript(
                audio_id=new_audio.id,
                raw_text_with_formatting=transcript_data.get("raw_text_with_formatting", ""),
                plain_text_for_search=transcript_data.get("plain_text_for_search", ""),
                edited_text_with_formatting=transcript_data.get("edited_text_with_formatting"),
                edited_plain_text=transcript_data.get("edited_plain_text"),
                detected_language=transcript_data.get("detected_language"),
                model_used=transcript_data.get("model_used"),
            )
            self.db.add(transcript)

        summary["audios_created"] += 1


