"""MinIO S3-compatible object storage service."""
import hashlib
import logging
from pathlib import Path
from typing import Optional
from datetime import timedelta
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class MinIOService:
    """MinIO client for image and audio storage."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False, public_endpoint: Optional[str] = None):
        """
        Initialize MinIO client using official minio library.

        Args:
            endpoint: MinIO endpoint for internal access (e.g., "minio:9000")
            access_key: MinIO access key
            secret_key: MinIO secret key
            secure: Use HTTPS (True) or HTTP (False)
            public_endpoint: MinIO endpoint for public URLs (e.g., "127.0.0.1:9000" or "192.168.29.22:9000")
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region='us-east-1',  # Set region explicitly for presigned URL compatibility
        )
        self.endpoint = endpoint
        self.public_endpoint = public_endpoint or endpoint
        logger.info(f"MinIO client initialized: internal={endpoint}, public={self.public_endpoint}")

    async def ensure_buckets_exist(self, buckets: list[str]) -> None:
        """
        Create buckets if they don't exist.

        Args:
            buckets: List of bucket names to create
        """
        for bucket_name in buckets:
            try:
                exists = self.client.bucket_exists(bucket_name)
                if exists:
                    logger.info(f"Bucket '{bucket_name}' already exists")
                else:
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Created bucket '{bucket_name}'")
            except S3Error as e:
                logger.error(f"Error handling bucket '{bucket_name}': {e}")
                raise

    async def upload_file(self, bucket: str, object_key: str, file_path: str) -> dict:
        """
        Upload file to MinIO bucket.

        Args:
            bucket: Bucket name
            object_key: Object key/path in MinIO
            file_path: Local file path to upload

        Returns:
            Dict with object_key, file_size, and file_hash
        """
        try:
            file_size = Path(file_path).stat().st_size
            file_hash = await self.get_file_hash(file_path)

            self.client.fput_object(
                bucket_name=bucket,
                object_name=object_key,
                file_path=file_path,
            )
            logger.info(f"Uploaded file to minio://{bucket}/{object_key} (size: {file_size} bytes)")

            return {
                "object_key": object_key,
                "file_size": file_size,
                "file_hash": file_hash,
            }
        except S3Error as e:
            logger.error(f"Failed to upload file to MinIO: {e}")
            raise

    async def download_file(self, bucket: str, object_key: str, local_path: str) -> bool:
        """
        Download file from MinIO to local path.

        Args:
            bucket: Bucket name
            object_key: Object key in MinIO
            local_path: Local path to save file

        Returns:
            True if successful
        """
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            self.client.fget_object(bucket_name=bucket, object_name=object_key, file_path=local_path)
            logger.info(f"Downloaded file from minio://{bucket}/{object_key} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download file from MinIO: {e}")
            return False

    async def delete_file(self, bucket: str, object_key: str) -> bool:
        """
        Delete file from MinIO.

        Args:
            bucket: Bucket name
            object_key: Object key in MinIO

        Returns:
            True if successful
        """
        try:
            self.client.remove_object(bucket_name=bucket, object_name=object_key)
            logger.info(f"Deleted file from minio://{bucket}/{object_key}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete file from MinIO: {e}")
            return False

    async def get_file_hash(self, file_path: str) -> str:
        """
        Calculate SHA256 hash of file for deduplication.

        Args:
            file_path: Path to file

        Returns:
            Hex string of SHA256 hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def get_presigned_url(self, bucket: str, object_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for temporary file access.

        Args:
            bucket: Bucket name
            object_key: Object key in MinIO
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL with public endpoint
        """
        try:
            # Convert seconds to timedelta (MinIO SDK requires timedelta)
            expires_delta = timedelta(seconds=expiration)

            # Generate presigned URL with public endpoint directly
            # We need to create a temporary client with the public endpoint
            # because the signature is tied to the hostname
            from minio import Minio as MinioClient
            from urllib.parse import urlparse, urlunparse

            # Parse the public endpoint to get scheme and host
            if self.public_endpoint != self.endpoint:
                public_client = MinioClient(
                    endpoint=self.public_endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                    region='us-east-1',
                )
                url = public_client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=object_key,
                    expires=expires_delta,
                )
                logger.info(f"Generated presigned URL for minio://{bucket}/{object_key} using public endpoint")
            else:
                url = self.client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=object_key,
                    expires=expires_delta,
                )
                logger.info(f"Generated presigned URL for minio://{bucket}/{object_key}")

            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    async def file_exists(self, bucket: str, object_key: str) -> bool:
        """
        Check if file exists in MinIO.

        Args:
            bucket: Bucket name
            object_key: Object key in MinIO

        Returns:
            True if file exists
        """
        try:
            self.client.stat_object(bucket_name=bucket, object_name=object_key)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Error checking file existence: {e}")
            raise
