"""Google Gemini 3 Flash API wrapper for OCR and text extraction."""
import time
from pathlib import Path
from typing import Tuple, Optional
import google.generativeai as genai
from PIL import Image
from app.logger import logger


class GeminiService:
    """Wrapper around Google Gemini 3 Flash API for image OCR and audio transcription."""

    EXTRACTION_PROMPT = """Analyze the provided image. Extract all text exactly as it appears in the image.
Maintain the original line breaks, paragraph structure, spacing, and tabular layouts.
Do not add any extra commentary, headers, or explanations.
Return only the extracted, formatted text."""

    TRANSCRIPTION_PROMPT = """Transcribe the provided audio file. Return only the transcribed text.
Maintain the original structure, paragraphs, and punctuation.
Do not add any extra commentary or headers."""

    def __init__(self, api_key: str):
        """
        Initialize Gemini service.
        
        Args:
            api_key: Google API key for Gemini
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        logger.info("GeminiService initialized with gemini-2.0-flash model")

    def extract_text_from_image(self, image_path: str) -> Tuple[str, str, int]:
        """
        Extract text from a single image using Gemini Vision.
        Uses the same approach as the notebook - load PIL image and pass to generate_content.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Text with formatting
            - detected_language: Detected language code (e.g., 'en', 'es')
            - processing_time_ms: Processing time in milliseconds
            
        Raises:
            FileNotFoundError: If image doesn't exist
            ValueError: If Gemini API fails
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        logger.debug(f"Extracting text from image: {image_path}")

        # Load image using PIL (same as your notebook)
        image = Image.open(str(image_path))

        # Call Gemini with prompt and image (same pattern as your notebook)
        start_time = time.time()
        try:
            response = self.model.generate_content([
                self.EXTRACTION_PROMPT,
                image,
            ])
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            if not response.text:
                raise ValueError("Gemini returned empty response")

            raw_text = response.text.strip()
            detected_language = self._detect_language(raw_text)

            logger.info(
                f"OCR completed: {len(raw_text)} chars, "
                f"language={detected_language}, time={processing_time_ms}ms"
            )

            return raw_text, detected_language, processing_time_ms

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise ValueError(f"Gemini API error: {str(e)}")

    def transcribe_audio(
        self, audio_path: str, language_hint: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        Transcribe audio file to text using Gemini 3 Flash audio mode.
        
        Args:
            audio_path: Path to the audio file
            language_hint: Optional language hint (e.g., 'en', 'hi', 'gu')
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Transcribed text
            - detected_language: Detected language code
            - processing_time_ms: Processing time in milliseconds
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If Gemini API fails
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.debug(f"Transcribing audio file: {audio_path}")

        # Determine MIME type from file extension
        ext = audio_path.suffix.lower()
        mime_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }
        mime_type = mime_types.get(ext, "audio/mpeg")

        start_time = time.time()
        try:
            # Upload file to Gemini (required for audio)
            print(f"[DEBUG] Uploading audio file: {audio_path}")
            audio_file = genai.upload_file(str(audio_path), mime_type=mime_type)
            logger.debug(f"Audio file uploaded to Gemini: {audio_file.uri}")

            # Build prompt with language hint if provided
            prompt = self.TRANSCRIPTION_PROMPT
            if language_hint:
                prompt += f"\nLanguage hint: {language_hint}"

            # Transcribe using Gemini audio mode
            response = self.model.generate_content([prompt, audio_file])

            # Clean up uploaded file
            genai.delete_file(audio_file.name)

            processing_time_ms = int((time.time() - start_time) * 1000)

            if not response.text:
                raise ValueError("Gemini returned empty response for audio")

            raw_text = response.text.strip()
            detected_language = language_hint or self._detect_language(raw_text)

            logger.info(
                f"Audio transcription completed: {len(raw_text)} chars, "
                f"language={detected_language}, time={processing_time_ms}ms"
            )

            return raw_text, detected_language, processing_time_ms

        except Exception as e:
            logger.error(f"Gemini audio transcription error: {str(e)}")
            raise ValueError(f"Gemini audio transcription error: {str(e)}")

    def _detect_language(self, text: str) -> str:
        """
        Simple language detection based on text content.
        
        Args:
            text: Text to detect language for
            
        Returns:
            Language code (e.g., 'en', 'es', 'fr')
        """
        if not text:
            return "unknown"

        try:
            # Simple heuristic: check for common non-ASCII characters
            ascii_chars = sum(1 for c in text if ord(c) < 128)
            ratio = ascii_chars / len(text)
            
            # If mostly ASCII, assume English
            if ratio > 0.8:
                return "en"
            
            # Check for common non-Latin characters
            if any('\u4e00' <= c <= '\u9fff' for c in text):  # Chinese
                return "zh"
            if any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text):  # Japanese
                return "ja"
            if any('\uac00' <= c <= '\ud7af' for c in text):  # Korean
                return "ko"
            if any('\u0400' <= c <= '\u04ff' for c in text):  # Cyrillic
                return "ru"
            if any('\u0900' <= c <= '\u097f' for c in text):  # Hindi
                return "hi"
            if any('\u0a80' <= c <= '\u0aff' for c in text):  # Gujarati
                return "gu"
            
            return "unknown"
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "unknown"

