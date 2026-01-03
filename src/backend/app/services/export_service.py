"""Export service for generating .docx and .txt files with OCR and transcript data."""
import re
import tempfile
from pathlib import Path
from typing import List, Tuple
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from sqlalchemy.orm import Session
from app.logger import logger
from app.models.image import Image
from app.models.ocr import OCRText
from app.models.audio import Audio
from app.models.transcript import AudioTranscript
from app.services.minio_service import MinIOService


class ExportService:
    """Service for exporting OCR and transcription data to .docx and .txt formats."""

    def __init__(self, minio_service: MinIOService):
        """
        Initialize export service.

        Args:
            minio_service: MinIO service for file downloads
        """
        self.minio_service = minio_service

    def _parse_markdown_to_docx_runs(self, text: str, paragraph) -> None:
        """
        Parse markdown formatting and add formatted runs to a docx paragraph.
        
        Supports:
        - **bold text** -> bold
        - *italic text* -> italic
        - `code text` -> monospaced
        - # Heading -> h1 (handled separately)
        - - bullet -> bullet (handled separately)

        Args:
            text: Text with markdown tags
            paragraph: python-docx paragraph object to add runs to
        """
        if not text:
            return

        # Pattern to find markdown formatting
        # This regex finds: **bold**, *italic*, `code`
        pattern = r'(\*\*.*?\*\*|\*.*?\*|`.*?`)'
        
        last_end = 0
        for match in re.finditer(pattern, text):
            # Add plain text before this match
            if match.start() > last_end:
                paragraph.add_run(text[last_end:match.start()])
            
            # Add formatted text
            matched_text = match.group(0)
            if matched_text.startswith('**') and matched_text.endswith('**'):
                # Bold
                run = paragraph.add_run(matched_text[2:-2])
                run.bold = True
            elif matched_text.startswith('*') and matched_text.endswith('*'):
                # Italic
                run = paragraph.add_run(matched_text[1:-1])
                run.italic = True
            elif matched_text.startswith('`') and matched_text.endswith('`'):
                # Code/monospaced
                run = paragraph.add_run(matched_text[1:-1])
                run.font.name = 'Courier New'
                run.font.size = Pt(10)
            
            last_end = match.end()
        
        # Add remaining plain text
        if last_end < len(text):
            paragraph.add_run(text[last_end:])

    def _add_markdown_text_to_docx(self, doc: Document, text: str) -> None:
        """
        Add markdown-formatted text to a docx document.
        
        Handles:
        - # Heading 1
        - ## Heading 2
        - ### Heading 3
        - **bold**, *italic*, `code`
        - Empty lines (paragraph breaks)
        - Regular paragraphs

        Args:
            doc: python-docx Document object
            text: Text with markdown formatting
        """
        lines = text.split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                # Empty line - add spacing
                doc.add_paragraph()
                continue
            
            # Check for headings
            if line_stripped.startswith('# '):
                doc.add_heading(line_stripped[2:].strip(), level=1)
            elif line_stripped.startswith('## '):
                doc.add_heading(line_stripped[3:].strip(), level=2)
            elif line_stripped.startswith('### '):
                doc.add_heading(line_stripped[4:].strip(), level=3)
            elif line_stripped.startswith('- '):
                # Bullet point
                paragraph = doc.add_paragraph(line_stripped[2:].strip(), style='List Bullet')
                self._parse_markdown_to_docx_runs(line_stripped[2:].strip(), paragraph)
            else:
                # Regular paragraph with potential markdown formatting
                paragraph = doc.add_paragraph()
                self._parse_markdown_to_docx_runs(line_stripped, paragraph)

    def generate_docx(
        self,
        images: List[Image],
        ocr_texts: List[OCRText],
        audios: List[Audio],
        transcripts: List[AudioTranscript],
        include_images: bool = True,
    ) -> str:
        """
        Generate .docx file with OCR text and transcripts with proper markdown formatting.

        Args:
            images: List of Image objects with sequence numbers (sorted by sequence)
            ocr_texts: List of OCRText objects (keyed by image_id)
            audios: List of Audio objects with sequence numbers (sorted by sequence)
            transcripts: List of AudioTranscript objects (keyed by audio_id)
            include_images: Include image information in output

        Returns:
            Path to generated .docx file
        """
        doc = Document()
        doc.add_heading("OCR Workbench Export", level=0)

        # Add images and their OCR text
        if include_images and images:
            doc.add_heading("Images", level=1)
            for img in images:
                # Add image heading with sequence number
                doc.add_heading(f"Image {img.sequence_number}", level=2)

                # Find OCR text for this image
                ocr_text = next((o for o in ocr_texts if o.image_id == img.id), None)
                if ocr_text:
                    # Add markdown-formatted text
                    self._add_markdown_text_to_docx(doc, ocr_text.raw_text_with_formatting)
                else:
                    doc.add_paragraph("[No OCR text available]")

        # Add audio transcripts
        if audios:
            doc.add_heading("Audio Transcripts", level=1)
            for audio in audios:
                # Add audio heading with sequence number
                doc.add_heading(f"Audio {audio.sequence_number}", level=2)

                # Add metadata
                metadata = f"Format: {audio.audio_format or 'unknown'}"
                if audio.duration_seconds:
                    minutes = audio.duration_seconds // 60
                    seconds = audio.duration_seconds % 60
                    metadata += f" | Duration: {minutes}m {seconds}s"
                doc.add_paragraph(metadata, style="Normal")

                # Find transcript for this audio
                transcript = next((t for t in transcripts if t.audio_id == audio.id), None)
                if transcript:
                    # Add markdown-formatted text
                    self._add_markdown_text_to_docx(doc, transcript.raw_text_with_formatting)
                else:
                    doc.add_paragraph("[No transcript available]")

        # Save document to temp file
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            doc.save(f.name)
            logger.info(f"Generated .docx export file: {f.name}")
            return f.name

    def generate_txt(
        self,
        images: List[Image],
        ocr_texts: List[OCRText],
        audios: List[Audio],
        transcripts: List[AudioTranscript],
        include_images: bool = True,
    ) -> str:
        """
        Generate .txt file with OCR text and transcripts (preserving markdown tags).

        Args:
            images: List of Image objects with sequence numbers (sorted by sequence)
            ocr_texts: List of OCRText objects (keyed by image_id)
            audios: List of Audio objects with sequence numbers (sorted by sequence)
            transcripts: List of AudioTranscript objects (keyed by audio_id)
            include_images: Include image information in output

        Returns:
            Path to generated .txt file
        """
        content = []
        content.append("=" * 80)
        content.append("OCR WORKBENCH EXPORT")
        content.append("=" * 80)
        content.append("")

        # Add images and their OCR text
        if include_images and images:
            content.append("IMAGES")
            content.append("-" * 80)
            for img in images:
                content.append(f"\nImage {img.sequence_number}")
                content.append("-" * 40)

                # Find OCR text for this image
                ocr_text = next((o for o in ocr_texts if o.image_id == img.id), None)
                if ocr_text:
                    # Add formatted text with markdown tags intact
                    content.append(ocr_text.raw_text_with_formatting)
                else:
                    content.append("[No OCR text available]")
            content.append("")

        # Add audio transcripts
        if audios:
            content.append("AUDIO TRANSCRIPTS")
            content.append("-" * 80)
            for audio in audios:
                content.append(f"\nAudio {audio.sequence_number}")
                content.append("-" * 40)

                # Add metadata
                metadata_parts = []
                if audio.audio_format:
                    metadata_parts.append(f"Format: {audio.audio_format}")
                if audio.duration_seconds:
                    minutes = audio.duration_seconds // 60
                    seconds = audio.duration_seconds % 60
                    metadata_parts.append(f"Duration: {minutes}m {seconds}s")
                if metadata_parts:
                    content.append(f"[{' | '.join(metadata_parts)}]")

                # Find transcript for this audio
                transcript = next((t for t in transcripts if t.audio_id == audio.id), None)
                if transcript:
                    # Add formatted text with markdown tags intact
                    content.append(transcript.raw_text_with_formatting)
                else:
                    content.append("[No transcript available]")
            content.append("")

        content.append("=" * 80)
        content.append("END OF EXPORT")
        content.append("=" * 80)

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(content))
            logger.info(f"Generated .txt export file: {f.name}")
            return f.name

    def export_folder(
        self,
        db: Session,
        book_id: int,
        chapter_id: int = None,
        format: str = "docx",
        include_images: bool = True,
        include_audio_transcripts: bool = True,
        include_page_breaks: bool = False,
    ) -> str:
        """
        Export a book or chapter to .docx or .txt file.

        Args:
            db: Database session
            book_id: Book ID to export
            chapter_id: Optional chapter ID (if None, export all chapters in book)
            format: Export format ('docx' or 'txt')
            include_images: Include images in export
            include_audio_transcripts: Include audio transcripts in export
            include_page_breaks: Include page breaks between chapters (docx only)

        Returns:
            Path to generated export file

        Raises:
            ValueError: If book/chapter not found or invalid format
        """
        logger.info(f"Exporting book_id={book_id}, chapter_id={chapter_id}, format={format}")

        # Query images and audios
        images_query = (
            db.query(Image)
            .filter(Image.chapter_id == chapter_id)
            .order_by(Image.sequence_number)
        ) if chapter_id else (
            db.query(Image)
            .join(Image.chapter)
            .filter(Image.chapter.has(book_id=book_id))
            .order_by(Image.sequence_number)
        )

        images = images_query.all() if include_images else []

        # Get OCR texts for images
        image_ids = [img.id for img in images]
        ocr_texts = db.query(OCRText).filter(OCRText.image_id.in_(image_ids)).all() if image_ids else []

        # Query audios
        audios_query = (
            db.query(Audio)
            .filter(Audio.chapter_id == chapter_id)
            .order_by(Audio.sequence_number)
        ) if chapter_id else (
            db.query(Audio)
            .join(Audio.chapter)
            .filter(Audio.chapter.has(book_id=book_id))
            .order_by(Audio.sequence_number)
        )

        audios = audios_query.all() if include_audio_transcripts else []

        # Get transcripts for audios
        audio_ids = [audio.id for audio in audios]
        transcripts = db.query(AudioTranscript).filter(AudioTranscript.audio_id.in_(audio_ids)).all() if audio_ids else []

        logger.info(f"Exporting: {len(images)} images, {len(audios)} audios")

        # Generate export file
        if format == "docx":
            return self.generate_docx(images, ocr_texts, audios, transcripts, include_images)
        elif format == "txt":
            return self.generate_txt(images, ocr_texts, audios, transcripts, include_images)
        else:
            raise ValueError(f"Invalid format: {format}")

    def export_selection(
        self,
        db: Session,
        image_ids: List[int] = None,
        audio_ids: List[int] = None,
        format: str = "docx",
        include_images: bool = True,
    ) -> str:
        """
        Export selected images and audios to .docx or .txt file.

        Args:
            db: Database session
            image_ids: List of image IDs to export (or None)
            audio_ids: List of audio IDs to export (or None)
            format: Export format ('docx' or 'txt')
            include_images: Include images in export

        Returns:
            Path to generated export file

        Raises:
            ValueError: If any image/audio not found or invalid format
        """
        logger.info(f"Exporting selection: {len(image_ids or [])} images, {len(audio_ids or [])} audios, format={format}")

        # Query selected images
        images = []
        ocr_texts = []
        if include_images and image_ids:
            images = db.query(Image).filter(Image.id.in_(image_ids)).order_by(Image.sequence_number).all()
            ocr_texts = db.query(OCRText).filter(OCRText.image_id.in_(image_ids)).all()

        # Query selected audios
        audios = []
        transcripts = []
        if audio_ids:
            audios = db.query(Audio).filter(Audio.id.in_(audio_ids)).order_by(Audio.sequence_number).all()
            transcripts = db.query(AudioTranscript).filter(AudioTranscript.audio_id.in_(audio_ids)).all()

        # Generate export file
        if format == "docx":
            return self.generate_docx(images, ocr_texts, audios, transcripts, include_images)
        elif format == "txt":
            return self.generate_txt(images, ocr_texts, audios, transcripts, include_images)
        else:
            raise ValueError(f"Invalid format: {format}")
