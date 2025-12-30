"""Input validation utilities."""
import mimetypes
from pathlib import Path


ALLOWED_IMAGE_TYPES = {"jpg", "jpeg", "png"}
ALLOWED_PDF_TYPES = {"pdf"}
ALLOWED_AUDIO_TYPES = {"mp3", "wav", "m4a", "ogg", "flac"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_AUDIO_SIZE = 500 * 1024 * 1024  # 500MB
MAX_PDF_SIZE = 100 * 1024 * 1024  # 100MB


def validate_image_file(file) -> tuple[bool, str]:
    """Validate image file type and size."""
    file_ext = Path(file.name).suffix.lower()

    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f"Invalid image format. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"

    if file.size > MAX_IMAGE_SIZE:
        return False, f"Image size exceeds {MAX_IMAGE_SIZE / 1024 / 1024}MB limit"

    return True, "valid"


def validate_pdf_file(file) -> tuple[bool, str]:
    """Validate PDF file type and size."""
    file_ext = Path(file.name).suffix.lower()

    if file_ext not in ALLOWED_PDF_EXTENSIONS:
        return False, "Invalid PDF format"

    if file.size > MAX_PDF_SIZE:
        return False, f"PDF size exceeds {MAX_PDF_SIZE / 1024 / 1024}MB limit"

    return True, "valid"


def validate_audio_file(file) -> tuple[bool, str]:
    """Validate audio file type and size."""
    file_ext = Path(file.name).suffix.lower()

    if file_ext not in ALLOWED_AUDIO_EXTENSIONS:
        return False, f"Invalid audio format. Allowed: {', '.join(ALLOWED_AUDIO_TYPES)}"

    if file.size > MAX_AUDIO_SIZE:
        return False, f"Audio size exceeds {MAX_AUDIO_SIZE / 1024 / 1024}MB limit"

    return True, "valid"


def get_file_type(filename: str) -> str:
    """Determine file type from filename."""
    ext = Path(filename).suffix.lower()

    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    elif ext in ALLOWED_PDF_EXTENSIONS:
        return "pdf"
    elif ext in ALLOWED_AUDIO_EXTENSIONS:
        return "audio"
    else:
        return "unknown"
