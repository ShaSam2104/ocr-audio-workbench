"""Mock MinIO service for testing."""
from typing import Dict, List
import hashlib


class MockMinIOService:
    """Mock MinIO service for testing without actual S3 connection."""

    def __init__(self, endpoint: str = "localhost:9000", access_key: str = "minioadmin", secret_key: str = "minioadmin", secure: bool = False):
        """Initialize mock MinIO service."""
        self.endpoint = endpoint
        self.storage: Dict[str, Dict[str, bytes]] = {}  # bucket -> {object_key: data}
        self.file_metadata: Dict[str, Dict[str, any]] = {}  # bucket/key -> {size, hash}

    async def ensure_buckets_exist(self, buckets: List[str]) -> None:
        """Create mock buckets."""
        for bucket_name in buckets:
            if bucket_name not in self.storage:
                self.storage[bucket_name] = {}

    async def upload_file(self, bucket: str, object_key: str, file_path: str) -> Dict:
        """Mock file upload."""
        if bucket not in self.storage:
            self.storage[bucket] = {}

        with open(file_path, "rb") as f:
            file_data = f.read()

        file_size = len(file_data)
        file_hash = hashlib.sha256(file_data).hexdigest()

        self.storage[bucket][object_key] = file_data
        self.file_metadata[f"{bucket}/{object_key}"] = {
            "size": file_size,
            "hash": file_hash,
        }

        return {
            "object_key": object_key,
            "file_size": file_size,
            "file_hash": file_hash,
        }

    async def download_file(self, bucket: str, object_key: str, local_path: str) -> bool:
        """Mock file download."""
        if bucket not in self.storage or object_key not in self.storage[bucket]:
            return False

        file_data = self.storage[bucket][object_key]
        with open(local_path, "wb") as f:
            f.write(file_data)
        return True

    async def delete_file(self, bucket: str, object_key: str) -> bool:
        """Mock file deletion."""
        if bucket in self.storage and object_key in self.storage[bucket]:
            del self.storage[bucket][object_key]
            if f"{bucket}/{object_key}" in self.file_metadata:
                del self.file_metadata[f"{bucket}/{object_key}"]
            return True
        return False

    async def get_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def get_presigned_url(self, bucket: str, object_key: str, expiration: int = 3600) -> str:
        """Generate mock presigned URL."""
        return f"http://{self.endpoint}/{bucket}/{object_key}?expires={expiration}"

    async def file_exists(self, bucket: str, object_key: str) -> bool:
        """Check if file exists in mock storage."""
        return bucket in self.storage and object_key in self.storage[bucket]
