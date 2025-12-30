"""Session state management."""
import streamlit as st
from typing import Dict, Any


def initialize_session_state():
    """Initialize all session state variables."""
    defaults = {
        # Authentication
        "auth_token": None,
        "user_id": None,
        "username": None,
        "backend_url": "http://localhost:8000",
        # Theme
        "theme": "light",
        # Navigation
        "selected_book_id": None,
        "selected_chapter_id": None,
        "selected_image_id": None,
        "selected_audio_id": None,
        # Image management
        "reorder_mode": False,
        "image_page": 1,
        "image_grid_page": 1,
        # Audio management
        "audio_page": 1,
        "audio_grid_page": 1,
        "current_audio_playing": None,
        "audio_playback_position": 0,
        # Crop mode
        "crop_mode": False,
        # OCR processing
        "ocr_task_ids": {},  # { chapter_id: task_id }
        "ocr_statuses": {},  # { task_id: status_data }
        "ocr_polling_active": False,
        # Transcription processing
        "transcription_task_ids": {},  # { chapter_id: task_id }
        "transcription_statuses": {},  # { task_id: status_data }
        "transcription_polling_active": False,
        # Mode selection
        "app_mode": None,  # "Instant Scan" or "Book Management"
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_session_value(key: str, default: Any = None) -> Any:
    """Get a session state value safely."""
    if key in st.session_state:
        return st.session_state[key]
    return default


def set_session_value(key: str, value: Any) -> None:
    """Set a session state value."""
    st.session_state[key] = value


def clear_auth():
    """Clear authentication data."""
    st.session_state.auth_token = None
    st.session_state.user_id = None
    st.session_state.username = None


def update_ocr_task(chapter_id: int, task_id: str) -> None:
    """Update OCR task ID for a chapter."""
    st.session_state.ocr_task_ids[chapter_id] = task_id


def get_ocr_task(chapter_id: int) -> str:
    """Get OCR task ID for a chapter."""
    return st.session_state.ocr_task_ids.get(chapter_id)


def update_transcription_task(chapter_id: int, task_id: str) -> None:
    """Update transcription task ID for a chapter."""
    st.session_state.transcription_task_ids[chapter_id] = task_id


def get_transcription_task(chapter_id: int) -> str:
    """Get transcription task ID for a chapter."""
    return st.session_state.transcription_task_ids.get(chapter_id)
