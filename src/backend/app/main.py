"""FastAPI application initialization."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from app.config import API_TITLE, API_VERSION, CORS_ORIGINS, MINIO_IMAGE_BUCKET, MINIO_AUDIO_BUCKET
from app.database import init_db
from app.logger import logger
from app.routers import auth, books, chapters, images, audios, ocr, transcription, text, search, export
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


# Simple request logger middleware to capture incoming request headers/methods
class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            headers = dict(request.headers)
        except Exception:
            headers = {}
        
        # Capture query parameters
        query_params = dict(request.query_params) if request.query_params else {}
        
        # Log full URL with query string
        full_url = str(request.url)
        
        # Extract authorization header
        auth_header = headers.get('authorization', 'NONE')
        
        # Log to both configured logger and stdout so preflight logs appear in console
        log_msg = f"Request: {request.method} {full_url} | Query: {query_params} | Auth: {auth_header}"
        logger.info(log_msg)

        # Also print the body of the request for debugging (may be large)
        body = await request.body()
        print(f"[MIDDLEWARE] {log_msg} | Body: {body.decode('utf-8', errors='replace')}", flush=True)
        
        # Capture response
        response = await call_next(request)
        logger.info(f"Response: {request.method} {full_url} -> Status {response.status_code}")
        print(f"[MIDDLEWARE RESPONSE] {request.method} {full_url} -> Status {response.status_code}", flush=True)
        return response


# Additional simple middleware using decorator to ensure early logging to stdout
@app.middleware("http")
async def early_request_logger(request: Request, call_next):
    try:
        headers = dict(request.headers)
    except Exception:
        headers = {}
    
    # Capture query parameters
    query_params = dict(request.query_params) if request.query_params else {}
    
    # Full URL with query string
    full_url = str(request.url)
    
    # Extract specific headers
    auth_header = headers.get('authorization', 'NONE')
    content_type = headers.get('content-type', 'N/A')
    
    # Log early with all details
    log_msg = f"Method={request.method} | Path={request.url.path} | QueryParams={query_params} | Auth={auth_header} | ContentType={content_type}"
    try:
        print(f"[EARLY] {log_msg}", flush=True)
    except Exception:
        pass
    
    response = await call_next(request)
    print(f"[EARLY-RESPONSE] {request.method} {request.url.path} -> {response.status_code}", flush=True)
    return response


# Attach request logger BEFORE CORS so we can see raw incoming headers
app.add_middleware(RequestLoggerMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Temporarily allow all origins for testing; refine later
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)


# Log exceptions with request context to help debug 400 responses
@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    try:
        headers = dict(request.headers)
    except Exception:
        headers = {}
    logger.error(f"Unhandled exception for {request.method} {request.url.path} - headers={headers} - exc={exc}")
    return PlainTextResponse("Internal server error", status_code=500)


@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
    # Generic handler fallback (keeps previous behavior but logs)
    try:
        headers = dict(request.headers)
    except Exception:
        headers = {}
    logger.error(f"HTTP exception for {request.method} {request.url.path} - headers={headers} - exc={exc}")
    return PlainTextResponse(str(exc), status_code=getattr(exc, 'status_code', 500))


# Include routers
app.include_router(auth.router)
# Include chapters before books so chapters' GET handler with content takes precedence
app.include_router(chapters.router)
app.include_router(books.router)
app.include_router(images.router)
app.include_router(audios.router)
app.include_router(ocr.router)
app.include_router(transcription.router)
app.include_router(text.router)
app.include_router(search.router)
app.include_router(export.router)


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
