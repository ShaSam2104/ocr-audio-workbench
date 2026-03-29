"""Google Gemini API wrapper for OCR and text extraction with multi-model support."""
import time
import mimetypes
from enum import Enum
from pathlib import Path
from typing import Tuple, Optional, List
import google.genai as genai
from PIL import Image
from app.logger import logger


class ModelTier(str, Enum):
    """Model tier enumeration for user-friendly selection."""
    HIGHER = "higher"  # More accurate, slower, more expensive
    LOWER = "lower"    # Faster, cheaper, slightly less accurate


class GeminiService:
    """Wrapper around Google Gemini API for image OCR and audio transcription with multi-model support."""

    # Model mappings: Higher tier (accurate), Lower tier (cost-effective)
    MODEL_MAPPING = {
        ModelTier.HIGHER: "gemini-3.1-pro-preview",      # Accurate on old/handwritten documents
        ModelTier.LOWER: "gemini-3-flash-preview",             # Cost-effective, still good quality
    }
    
    # Fallback order when rate limit is hit
    FALLBACK_ORDER = [
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
    ]

    EXTRACTION_PROMPT = """Extract all text from the image EXACTLY as it appears.

CRITICAL INSTRUCTIONS:
1. TEXT CONTENT: Extract every single word, number, and character as shown in the image.
2. LANGUAGE-BASED VALIDATION:
   - The expected language(s) will be provided to you
   - For each word you extract, validate it against the provided language's vocabulary and script
   - If a word appears valid in that language's script, extract it as is
   - If a word has stray marks/dots/diacritics that don't belong to the language script, remove them
   - If uncertain whether a mark is a stray artifact, check if removing it creates a valid word in the language
   - Consider multiple languages if specified, and validate words accordingly
   - If multiple languages are present, preserve the language distribution in the output
3. OCR ARTIFACTS:
   - Look for stray dots, marks, or diacritics that appear to be OCR errors
   - If removing a mark/dot results in a valid word in the provided language, remove it
   - If keeping the mark results in an invalid/non-existent word, try removing it
   - Only keep marks/dots if they are legitimate parts of the word in that language
4. WHEN NO LANGUAGE VOCABULARY MATCH:
   - If a word cannot be validated against the provided languages, extract it exactly as shown in the image
   - Do not try to "correct" it - just transcribe it exactly
5. EDITORIAL MARKS & INSERTIONS:
   - Look for "^" (caret) symbols or other insertion marks in the text
   - These marks indicate words that were inserted between two other words
   - Properly integrate marked insertions into the text flow where they belong
   - Remove the "^" marker once the word is properly positioned
6. LINE BREAKS: Each new line in the image = new line in output.
7. PARAGRAPHS: Maintain paragraph breaks as in the image.
8. TABLES: 
   - Detect tabular data and format it as a VALID MARKDOWN TABLE.
   - You MUST include a header row (use appropriate headers or empty cells) and a separator row (e.g. |---|---|).
   - Ensure all rows in a table section have the same number of columns.
   - Use | characters to separate columns.
9. FORMATTING — Detect and preserve visual formatting from the image:
   - Text that appears **bold** in the image → wrap in **double asterisks**
   - Text that appears *italic* in the image → wrap in *single asterisks*
   - Text that appears underlined in the image → wrap in <u>underline tags</u>
   - Text that appears in ~~strikethrough~~ → wrap in ~~double tildes~~
   - Only apply formatting when it is clearly visible in the image; do not guess
Output ONLY the result text. No explanations."""

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

    def extract_text_from_image(
        self, 
        image_path: str, 
        languages: Optional[List[str]] = None,
        model_tier: str = "higher",
        custom_prompt: Optional[str] = None
    ) -> Tuple[str, str, int, str]:
        """
        Extract text from a single image using Gemini Vision with multi-model support.
        
        Args:
            image_path: Path to the image file
            languages: Optional list of languages to expect in the image (e.g., ['hi', 'gu'])
            model_tier: "higher" (accurate) or "lower" (cost-effective). Defaults to "higher"
            custom_prompt: Optional custom prompt to append to the default extraction prompt
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Text with markdown formatting
            - detected_language: Detected language code (e.g., 'en', 'es')
            - processing_time_ms: Processing time in milliseconds
            - model_used: Which model was actually used (e.g., 'gemini-3.0-flash')
            
        Raises:
            FileNotFoundError: If image doesn't exist
            ValueError: If Gemini API fails
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        logger.debug(f"Extracting text from image: {image_path}, model_tier={model_tier}")

        # Load image using PIL
        image = Image.open(str(image_path))

        # Build prompt - custom prompt comes first
        prompt = ""
        
        # Add custom prompt first if provided
        if custom_prompt:
            prompt += f"{custom_prompt}\n\n"
        
        # Add default extraction prompt
        prompt += self.EXTRACTION_PROMPT
        
        # Add language hints if provided
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
            prompt += f"\n\nThe image contains text in: {', '.join(lang_names)} this is very important to consider so detect the languages in the text properly and make sure if more than one language is present preserve it and give output accordingly too. Preserve the original language and script exactly."
        
        # Add table handling instructions
        prompt += "\n\nIMPORTANT: If the image has a table, keep it as a clear row-by-row structure. If it has mixed text and table, extract both maintaining their original layout."

        # Get the model to use based on tier
        primary_model = self.MODEL_MAPPING.get(model_tier, "gemini-3.0-flash")
        models_to_try = [primary_model] + [m for m in self.FALLBACK_ORDER if m != primary_model]
        
        start_time = time.time()
        last_error = None
        model_used = None
        
        # Try each model in order, falling back on rate limit
        for model in models_to_try:
            try:
                logger.debug(f"Attempting OCR with model: {model}")
                response = self.client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        image,
                    ],
                )
                
                if not response.text:
                    raise ValueError("Gemini returned empty response")

                raw_text = self._normalize_response_text(response.text).strip()
                detected_language = self._detect_language(raw_text)
                processing_time_ms = int((time.time() - start_time) * 1000)
                model_used = model

                logger.info(
                    f"OCR completed with {model}: {len(raw_text)} chars, "
                    f"language={detected_language}, time={processing_time_ms}ms"
                )

                return raw_text, detected_language, processing_time_ms, model_used

            except Exception as e:
                error_str = str(e)
                last_error = error_str
                # Check if it's a rate limit error by looking at the error message
                if "rate_limit" in error_str.lower() or "quota" in error_str.lower() or "429" in error_str:
                    logger.warning(f"Rate limit hit for {model}, trying fallback model: {e}")
                else:
                    logger.error(f"Error with model {model}: {str(e)}")
                continue
        
        # All models failed
        error_msg = f"All models failed. Last error: {last_error}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def transcribe_audio(
        self, 
        audio_path: str, 
        language_hint: Optional[str] = None, 
        languages: Optional[List[str]] = None,
        model_tier: str = "higher",
        custom_prompt: Optional[str] = None
    ) -> Tuple[str, str, int, str]:
        """
        Transcribe audio file to text using Gemini audio mode with multi-model support.
        
        Args:
            audio_path: Path to the audio file
            language_hint: Optional language hint (e.g., 'en', 'hi', 'gu')
            languages: Optional list of languages expected in the audio
            model_tier: "higher" (accurate) or "lower" (cost-effective). Defaults to "higher"
            custom_prompt: Optional custom prompt to append to the default transcription prompt
            
        Returns:
            Tuple of:
            - raw_text_with_formatting: Transcribed text in markdown format
            - detected_language: Detected language code
            - processing_time_ms: Processing time in milliseconds
            - model_used: Which model was actually used
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If Gemini API fails
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.debug(f"Transcribing audio file: {audio_path}, model_tier={model_tier}")

        # Get the model to use based on tier (use same tier for audio)
        primary_model = self.MODEL_MAPPING.get(model_tier, "gemini-2.0-flash")
        models_to_try = [primary_model] + [m for m in self.FALLBACK_ORDER if m != primary_model]
        
        start_time = time.time()
        last_error = None
        model_used = None
        
        for model in models_to_try:
            try:
                logger.debug(f"Uploading audio file: {audio_path}")
                
                # Upload using the Path object directly
                audio_file = self.client.files.upload(file=audio_path)
                logger.debug(f"Audio file uploaded to Gemini: {audio_file.name}")

                # Build prompt - custom prompt comes first
                prompt = ""
                
                # Add custom prompt first if provided
                if custom_prompt:
                    prompt += f"{custom_prompt}\n\n"
                
                # Add default transcription prompt
                prompt += self.TRANSCRIPTION_PROMPT
                
                # Add language hint if provided
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

                logger.debug(f"Attempting transcription with model: {model}")
                # Transcribe using Gemini audio mode
                response = self.client.models.generate_content(
                    model=model,
                    contents=[prompt, audio_file],
                )

                # Clean up uploaded file
                self.client.files.delete(name=audio_file.name)

                if not response.text:
                    raise ValueError("Gemini returned empty response for audio")

                raw_text = self._normalize_response_text(response.text).strip()
                detected_language = language_hint or self._detect_language(raw_text)
                processing_time_ms = int((time.time() - start_time) * 1000)
                model_used = model

                logger.info(
                    f"Audio transcription completed with {model}: {len(raw_text)} chars, "
                    f"language={detected_language}, time={processing_time_ms}ms"
                )

                return raw_text, detected_language, processing_time_ms, model_used

            except Exception as e:
                error_str = str(e)
                last_error = error_str
                # Check if it's a rate limit error by looking at the error message
                if "rate_limit" in error_str.lower() or "quota" in error_str.lower() or "429" in error_str:
                    logger.warning(f"Rate limit hit for {model}, trying fallback model: {e}")
                else:
                    logger.error(f"Error with model {model}: {str(e)}")
                try:
                    self.client.files.delete(name=audio_file.name)
                except:
                    pass
                continue
        
        # All models failed
        error_msg = f"All models failed for transcription. Last error: {last_error}"
        logger.error(error_msg)
        raise ValueError(error_msg)

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
                # For non-table lines, just strip trailing whitespace
                line = line.rstrip()
            
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

