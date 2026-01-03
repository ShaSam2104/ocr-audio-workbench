"""Google Gemini 3 Flash API wrapper for OCR and text extraction."""
import time
import mimetypes
from pathlib import Path
from typing import Tuple, Optional, List
import google.genai as genai
from PIL import Image
from app.logger import logger


class GeminiService:
    """Wrapper around Google Gemini 3 Flash API for image OCR and audio transcription."""

    EXTRACTION_PROMPT = """Extract all text from the image EXACTLY as it appears. Preserve the original structure and layout.

CRITICAL INSTRUCTIONS:
1. TEXT CONTENT: Extract every single word, number, and character exactly as shown
2. LINE BREAKS: Each new line in the image = new line in output. This is ESSENTIAL.
3. SPACING: Preserve original spacing and indentation
4. TABLES: 
   - If the image contains a table, extract it row by row
   - Each new row starts on a new line
   - Separate columns with | characters
   - Keep all text content even if cells are partially filled
   - Put multi-line cell content on new lines within the cell (use newlines)
5. NO MARKDOWN FORMATTING: Do not add **bold**, *italic*, or any other markdown unless visibly emphasized
6. MULTILINGUAL TEXT: Preserve all scripts exactly (Hindi, Gujarati, English, etc.)
7. SPECIAL CHARACTERS: Keep all diacritics and punctuation exactly as shown
8. STRUCTURE: Preserve the layout - if something is indented, keep that indentation

MOST IMPORTANT: Output each line exactly as it appears in the image. Do not try to be smart about formatting.
Output ONLY the extracted text with proper line breaks. No explanations."""

    TRANSCRIPTION_PROMPT = """Transcribe the provided audio file. Return only the transcribed text.
Format the output as markdown with proper formatting:
- Use **bold** for emphasized words
- Use *italic* for stressed words
- Use # for new sections or topics
- Use - for bullet points where appropriate
Maintain the original structure, paragraphs, and punctuation.
Do not add any extra commentary or headers."""

    def __init__(self, api_key: str):
        """
        Initialize Gemini service.
        
        Args:
            api_key: Google API key for Gemini
        """
        self.client = genai.Client(api_key=api_key)
        logger.info("GeminiService initialized with gemini-3.0-flash model")

    def extract_text_from_image(self, image_path: str, languages: Optional[List[str]] = None) -> Tuple[str, str, int]:
        """
        Extract text from a single image using Gemini Vision.
        Uses the same approach as the notebook - load PIL image and pass to generate_content.
        
        Args:
            image_path: Path to the image file
            languages: Optional list of languages to expect in the image (e.g., ['hi', 'gu'])
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Text with markdown formatting
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

        # Build prompt with language hints if provided
        prompt = self.EXTRACTION_PROMPT
        if languages:
            language_names = {
                'en': 'English',
                'hi': 'Hindi',
                'gu': 'Gujarati',
                'ja': 'Japanese',
                'zh': 'Chinese',
                'ko': 'Korean',
                'ru': 'Russian',
                'es': 'Spanish',
                'fr': 'French',
                'de': 'German',
            }
            lang_names = [language_names.get(lang, lang) for lang in languages]
            prompt += f"\n\nThe image contains text in: {', '.join(lang_names)}. Preserve the original language and script exactly."
        
        prompt += "\n\nIMPORTANT: If the image has a table, keep it as a clear row-by-row structure. If it has mixed text and table, extract both maintaining their original layout."

        # Call Gemini with prompt and image (same pattern as your notebook)
        start_time = time.time()
        try:
            response = self.client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=[
                    prompt,
                    image,
                ],
            )
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            if not response.text:
                raise ValueError("Gemini returned empty response")

            raw_text = self._normalize_response_text(response.text).strip()
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
        self, audio_path: str, language_hint: Optional[str] = None, languages: Optional[List[str]] = None
    ) -> Tuple[str, str, int]:
        """
        Transcribe audio file to text using Gemini 3 Flash audio mode.
        
        Args:
            audio_path: Path to the audio file
            language_hint: Optional language hint (e.g., 'en', 'hi', 'gu')
            languages: Optional list of languages expected in the audio
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Transcribed text in markdown format
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

        start_time = time.time()
        try:
            # Upload file to Gemini (required for audio)
            # The library should detect file type from path/extension
            logger.debug(f"Uploading audio file: {audio_path}")
            
            # Upload using the Path object directly
            audio_file = self.client.files.upload(file=audio_path)
            logger.debug(f"Audio file uploaded to Gemini: {audio_file.name}")

            # Build prompt with language hint if provided
            prompt = self.TRANSCRIPTION_PROMPT
            if language_hint:
                prompt += f"\nLanguage hint: {language_hint}"
            elif languages:
                language_names = {
                    'en': 'English',
                    'hi': 'Hindi',
                    'gu': 'Gujarati',
                    'ja': 'Japanese',
                    'zh': 'Chinese',
                    'ko': 'Korean',
                    'ru': 'Russian',
                    'es': 'Spanish',
                    'fr': 'French',
                    'de': 'German',
                }
                lang_names = [language_names.get(lang, lang) for lang in languages]
                prompt += f"\nExpected languages: {', '.join(lang_names)}. Preserve any multilingual content."

            # Transcribe using Gemini audio mode
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt, audio_file],
            )

            # Clean up uploaded file using keyword argument
            self.client.files.delete(name=audio_file.name)

            processing_time_ms = int((time.time() - start_time) * 1000)

            if not response.text:
                raise ValueError("Gemini returned empty response for audio")

            raw_text = self._normalize_response_text(response.text).strip()
            detected_language = language_hint or self._detect_language(raw_text)

            logger.info(
                f"Audio transcription completed: {len(raw_text)} chars, "
                f"language={detected_language}, time={processing_time_ms}ms"
            )

            return raw_text, detected_language, processing_time_ms

        except Exception as e:
            logger.error(f"Gemini audio transcription error: {str(e)}")
            raise ValueError(f"Gemini audio transcription error: {str(e)}")

    def _normalize_response_text(self, text: str) -> str:
        """
        Normalize response text by converting escaped characters to actual characters
        and fixing table structure issues.
        
        Args:
            text: Raw response text from Gemini
            
        Returns:
            Normalized text with proper formatting
        """
        if not text:
            return text
        
        # Convert literal escape sequences to actual characters
        text = text.replace('\\n', '\n')
        text = text.replace('\\t', '\t')
        text = text.replace('\\r', '\r')
        
        # Handle any double-escaped sequences
        while '\\n' in text or '\\t' in text:
            text = text.replace('\\n', '\n')
            text = text.replace('\\t', '\t')
        
        # Process lines and fix table structure
        lines = text.split('\n')
        cleaned_lines = []
        
        for i, line in enumerate(lines):
            # For table lines (containing |), normalize the structure
            if '|' in line:
                # Split by pipe and clean each cell
                cells = line.split('|')
                cleaned_cells = [cell.strip() for cell in cells]
                # Rejoin with proper spacing
                line = ' | '.join(cleaned_cells)
            else:
                # For non-table lines, remove multiple spaces within words but preserve spacing between words
                import re
                # Remove spaces between Devanagari characters (OCR artifacts)
                line = re.sub(r'([क-ह]) +([क-ह])', r'\1\2', line)
                # Remove multiple spaces between words (but keep at least one)
                line = re.sub(r'  +', ' ', line)
            
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        return text

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

