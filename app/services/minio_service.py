"""MinIO S3-compatible object storage service."""
import boto3
import hashlib
import logging
from botocore.client import Config
from botocore.exceptions import ClientError
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MinIOService:
    """S3-compatible MinIO client for image and audio storage."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        """
        Initialize MinIO client using boto3 (S3-compatible).

        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000" or "minio.example.com")
            access_key: MinIO access key
            secret_key: MinIO secret key
            secure: Use HTTPS (True) or HTTP (False)
        """
        protocol = "https" if secure else "http"
        endpoint_url = f"{protocol}://{endpoint}"

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )
        self.endpoint = endpoint
        logger.info(f"MinIO client initialized: {endpoint_url}")

    async def ensure_buckets_exist(self, buckets: list[str]) -> None:
        """
        Create buckets if they don't exist.

        Args:
            buckets: List of bucket names to create
        """
        for bucket_name in buckets:
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                logger.info(f"Bucket '{bucket_name}' already exists")
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    try:
                        self.s3_client.create_bucket(Bucket=bucket_name)
                        logger.info(f"Created bucket '{bucket_name}'")
                    except ClientError as create_error:
                        logger.error(f"Failed to create bucket '{bucket_name}': {create_error}")
                        raise
                else:
                    logger.error(f"Error checking bucket '{bucket_name}': {e}")
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

            self.s3_client.upload_file(
                Filename=file_path,
                Bucket=bucket,
                Key=object_key,
            )
            logger.info(f"Uploaded file to s3://{bucket}/{object_key} (size: {file_size} bytes)")

            return {
                "object_key": object_key,
                "file_size": file_size,
                "file_hash": file_hash,
            }
        except Exception as e:
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
            self.s3_client.download_file(Bucket=bucket, Key=object_key, Filename=local_path)
            logger.info(f"Downloaded file from s3://{bucket}/{object_key} to {local_path}")
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
            self.s3_client.delete_object(Bucket=bucket, Key=object_key)
            logger.info(f"Deleted file from s3://{bucket}/{object_key}")
            return True
        except Exception as e:
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
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expiration,
            )
            logger.info(f"Generated presigned URL for s3://{bucket}/{object_key}")
            return url
        except Exception as e:
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
            self.s3_client.head_object(Bucket=bucket, Key=object_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"Error checking file existence: {e}")
            raise
