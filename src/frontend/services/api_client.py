"""API client for backend communication."""
import os
from typing import Optional, Dict, Any
import httpx
from utils.logger import get_logger

logger = get_logger(__name__)


class APIClient:
    """HTTP client for OCR Workbench backend."""

    def __init__(self, base_url: Optional[str] = None):
        """Initialize API client."""
        self.base_url = base_url or os.getenv(
            "BACKEND_URL", "http://localhost:8000"
        )
        self.token: Optional[str] = None

    def set_token(self, token: str) -> None:
        """Set authentication token."""
        self.token = token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Login with username and password."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/auth/login",
                    json={"username": username, "password": password},
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Login failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return None

    def get_books(self, page: int = 1, page_size: int = 10) -> Optional[Dict[str, Any]]:
        """Get list of books."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/books",
                    params={"page": page, "page_size": page_size},
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get books failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get books error: {str(e)}")
            return None

    def create_book(self, name: str, description: str = "") -> Optional[Dict[str, Any]]:
        """Create a new book."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/books",
                    json={"name": name, "description": description},
                    headers=self._get_headers(),
                )

                if response.status_code == 201:
                    return response.json()
                else:
                    logger.error(f"Create book failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Create book error: {str(e)}")
            return None

    def get_chapters(
        self, book_id: int, page: int = 1, page_size: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Get chapters for a book."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/books/{book_id}/chapters",
                    params={"page": page, "page_size": page_size},
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get chapters failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get chapters error: {str(e)}")
            return None

    def create_chapter(
        self, book_id: int, name: str, description: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Create a new chapter."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/books/{book_id}/chapters",
                    json={"name": name, "description": description},
                    headers=self._get_headers(),
                )

                if response.status_code == 201:
                    return response.json()
                else:
                    logger.error(f"Create chapter failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Create chapter error: {str(e)}")
            return None

    def get_chapter_images(
        self, chapter_id: int, page: int = 1, page_size: int = 50
    ) -> Optional[Dict[str, Any]]:
        """Get images in a chapter."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/chapters/{chapter_id}/images",
                    params={"page": page, "page_size": page_size},
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get chapter images failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get chapter images error: {str(e)}")
            return None

    def upload_images(self, chapter_id: int, files: list) -> Optional[list]:
        """Upload images to a chapter."""
        try:
            with httpx.Client(timeout=120.0) as client:
                # Prepare multipart files
                multipart_files = []
                for file in files:
                    multipart_files.append(
                        ("files", (file.name, file.getvalue(), "image/*"))
                    )

                headers = {}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                response = client.post(
                    f"{self.base_url}/chapters/{chapter_id}/images/upload",
                    files=multipart_files,
                    headers=headers,
                )

                if response.status_code == 201:
                    return response.json()
                else:
                    logger.error(f"Upload images failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Upload images error: {str(e)}")
            return None

    def get_ocr_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get OCR task status."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/ocr/status/{task_id}",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get OCR status failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get OCR status error: {str(e)}")
            return None

    def start_ocr_processing(
        self, image_ids: list, crop_coordinates: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Start OCR processing for images."""
        try:
            with httpx.Client(timeout=30.0) as client:
                payload = {
                    "image_ids": image_ids,
                }
                if crop_coordinates:
                    payload["crop_coordinates"] = crop_coordinates

                response = client.post(
                    f"{self.base_url}/ocr/process",
                    json=payload,
                    headers=self._get_headers(),
                )

                if response.status_code == 202:
                    return response.json()
                else:
                    logger.error(f"Start OCR failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Start OCR error: {str(e)}")
            return None

    def get_image_text(self, image_id: int) -> Optional[Dict[str, Any]]:
        """Get OCR text for an image."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/images/{image_id}/text",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get image text failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get image text error: {str(e)}")
            return None

    def get_transcription_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get transcription task status."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/transcription/status/{task_id}",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get transcription status failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get transcription status error: {str(e)}")
            return None

    def start_transcription(
        self, audio_ids: list, language_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Start transcription for audio files."""
        try:
            with httpx.Client(timeout=30.0) as client:
                payload = {"audio_ids": audio_ids}
                if language_hint:
                    payload["language_hint"] = language_hint

                response = client.post(
                    f"{self.base_url}/audio/transcribe",
                    json=payload,
                    headers=self._get_headers(),
                )

                if response.status_code == 202:
                    return response.json()
                else:
                    logger.error(f"Start transcription failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Start transcription error: {str(e)}")
            return None

    def get_chapter_audios(
        self, chapter_id: int, page: int = 1, page_size: int = 50
    ) -> Optional[Dict[str, Any]]:
        """Get audio files in a chapter."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/chapters/{chapter_id}/audios",
                    params={"page": page, "page_size": page_size},
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get chapter audios failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Get chapter audios error: {str(e)}")
            return None

    def upload_audios(self, chapter_id: int, files: list) -> Optional[list]:
        """Upload audio files to a chapter."""
        try:
            with httpx.Client(timeout=120.0) as client:
                # Prepare multipart files
                multipart_files = []
                for file in files:
                    multipart_files.append(
                        ("files", (file.name, file.getvalue(), "audio/*"))
                    )

                headers = {}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                response = client.post(
                    f"{self.base_url}/chapters/{chapter_id}/audios/upload",
                    files=multipart_files,
                    headers=headers,
                )

                if response.status_code == 201:
                    return response.json()
                else:
                    logger.error(f"Upload audios failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Upload audios error: {str(e)}")
            return None
