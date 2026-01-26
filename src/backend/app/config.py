"""Configuration and environment variables for OCR Workbench."""
import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production-12345")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600  # 10 hours

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ocr_workbench.db")

# API Configuration
API_TITLE = "OCR Workbench API"
API_DESCRIPTION = "Multi-user OCR and audio transcription platform with Gemini 3 Flash"
API_VERSION = "1.0.0"

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Logging Configuration
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "30"))

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", MINIO_ENDPOINT)
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_IMAGE_BUCKET = "images"
MINIO_AUDIO_BUCKET = "audio"
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# File Upload Configuration
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Pagination
DEFAULT_PAGE_SIZE = 50

# Processing
MAX_CONCURRENT_WORKERS = 5

class Settings:
    """Settings class for easy access to configuration."""
    
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.minio_endpoint = MINIO_ENDPOINT
        self.minio_access_key = MINIO_ACCESS_KEY
        self.minio_secret_key = MINIO_SECRET_KEY


_settings = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings