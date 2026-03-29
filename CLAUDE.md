# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OCR Workbench — a multi-user FastAPI backend for OCR and audio transcription powered by Google Gemini 3 Flash. All backend code lives under `src/backend/`.

## Commands

```bash
# Run the dev server (from repo root)
uv run fastapi dev src/backend/app/main.py --host 0.0.0.0 --port 8000

# Run all tests
uv run pytest src/backend/tests/ -v

# Run a single test file
uv run pytest src/backend/tests/test_auth.py -v

# Run a single test by name
uv run pytest src/backend/tests/test_auth.py -k "test_login" -v

# Add a dependency (never use pip)
uv add <package>

# Sync dependencies
uv sync
```

## Architecture

**Tech stack:** FastAPI + SQLAlchemy ORM + SQLite (FTS5) + MinIO (S3-compatible object storage) + Google Gemini 3 Flash API. Python 3.13, managed with `uv`.

### Data hierarchy
Book → Chapter → Images + Audio files. All resources are globally shared — no per-user scoping or RBAC. Authentication is JWT-only (401 if not logged in, never 403 for resource access).

### Key architectural patterns

- **Background processing:** OCR and transcription endpoints return 202 immediately with a `task_id`. Images/audio are processed concurrently via `ThreadPoolExecutor` (max 5 workers), each sent to Gemini one at a time. Frontend polls status endpoints.
- **File storage:** All images and audio stored in MinIO buckets (`images/` and `audio/`), not the local filesystem. Database stores `object_key` references. Temp files used only during processing (cropping, PDF extraction) and deleted after.
- **Formatting preservation:** OCR/transcript text stored with markdown-like tags (`**bold**`, `*italic*`, `__underline__`). A separate `plain_text_for_search` column (stripped of tags) is indexed with FTS5 for full-text search.
- **Export:** Supports `.docx` (with Word formatting from markdown tags) and `.txt` output, covering both image OCR and audio transcripts.

### Code layout (`src/backend/app/`)

| Directory | Purpose |
|-----------|---------|
| `models/` | SQLAlchemy models — `hierarchy.py` (Book, Chapter), `image.py`, `audio.py`, `ocr.py`, `transcript.py`, `user.py` |
| `schemas/` | Pydantic request/response schemas |
| `routers/` | FastAPI route handlers — one per resource (auth, books, chapters, images, audios, ocr, transcription, text, search, export, export_import) |
| `services/` | Business logic — `gemini_service.py` (Gemini API wrapper), `minio_service.py` (S3 client), `export_service.py`, `background_tasks.py`, `audio_task_manager.py` |
| `config.py` | All env var loading (from `.env`), constants |
| `dependencies.py` | FastAPI DI — `get_current_user` (JWT auth), `get_minio_client` (singleton) |
| `database.py` | SQLAlchemy engine, session factory, `init_db()` creates tables |
| `logger.py` | Daily rotating file logs in `logs/`, 30-day auto-cleanup |

### Testing

Tests live in `src/backend/tests/`. They use:
- In-memory SQLite (`sqlite:///:memory:`)
- `MockMinIOService` from `tests/fixtures/minio_mock.py`
- `db_session_with_client` fixture handles DB session + dependency overrides per test
- `auth_headers` fixture provides a valid JWT for protected endpoints

### External dependencies

- **MinIO** must be running for the dev server (default `localhost:9000`)
- **Gemini API key** required in `.env` as `GEMINI_API_KEY`
- Config defaults in `app/config.py`; copy `.env.example` to `.env` for local setup
