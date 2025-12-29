"""FastAPI application initialization."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import API_TITLE, API_VERSION, CORS_ORIGINS
from app.database import init_db
from app.logger import logger
from app.routers import auth

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Multi-user OCR and audio transcription platform with Gemini 3 Flash",
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
