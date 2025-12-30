"""FastAPI application initialization."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import API_TITLE, API_VERSION, CORS_ORIGINS, MINIO_IMAGE_BUCKET, MINIO_AUDIO_BUCKET
from app.database import init_db
from app.logger import logger
from app.routers import auth, books, chapters, images, audios, ocr, transcription
from app.dependencies import get_minio_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Startup: Initialize MinIO buckets
    Shutdown: Cleanup resources
    """
    # Startup
    logger.info("Starting up OCR Workbench...")
    try:
        minio_client = get_minio_client()
        await minio_client.ensure_buckets_exist([MINIO_IMAGE_BUCKET, MINIO_AUDIO_BUCKET])
        logger.info("MinIO buckets initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MinIO: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down OCR Workbench...")


# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Multi-user OCR and audio transcription platform with Gemini 3 Flash",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if isinstance(CORS_ORIGINS, list) else CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router)
app.include_router(books.router)
app.include_router(chapters.router)
app.include_router(images.router)
app.include_router(audios.router)
app.include_router(ocr.router)
app.include_router(transcription.router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": API_VERSION}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "OCR Workbench API",
        "version": API_VERSION,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting OCR Workbench API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
