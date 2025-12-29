"""Configuration and environment variables for OCR Workbench."""
import os
from datetime import timedelta

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production-12345")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

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

# File Upload Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Pagination
DEFAULT_PAGE_SIZE = 50

# Processing
MAX_CONCURRENT_WORKERS = 5
