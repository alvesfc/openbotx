"""S3 storage provider for OpenBotX."""

import io
from typing import Any
from uuid import uuid4

from openbotx.models.enums import ProviderStatus
from openbotx.models.message import Attachment
from openbotx.providers.base import ProviderHealth
from openbotx.providers.storage.base import StorageProvider, StoredFile


class S3StorageProvider(StorageProvider):
    """AWS S3 storage provider implementation."""

    def __init__(
        self,
        name: str = "s3",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize S3 storage provider.

        Args:
            name: Provider name
            config: Configuration with 'bucket', 'region', 'access_key', 'secret_key'
        """
        super().__init__(name, config)

        if not config:
            raise ValueError("S3 config is required")

        self.bucket = config.get("bucket")
        self.region = config.get("region", "us-east-1")
        self.access_key = config.get("access_key")
        self.secret_key = config.get("secret_key")

        if not self.bucket:
            raise ValueError("S3 bucket is required")

        self._s3_client: Any = None

    async def initialize(self) -> None:
        """Initialize the S3 storage provider."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the S3 storage provider and connect to S3."""
        self._set_status(ProviderStatus.STARTING)

        try:
            import boto3

            # Create S3 client
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )

            # Verify bucket access
            self._s3_client.head_bucket(Bucket=self.bucket)

            self._set_status(ProviderStatus.RUNNING)
            self._logger.info(
                "s3_storage_started",
                bucket=self.bucket,
                region=self.region,
            )

        except ImportError:
            self._logger.error(
                "boto3_not_installed",
                message="Install boto3 for S3 storage support",
            )
            self._set_status(ProviderStatus.ERROR)
            raise

        except Exception as e:
            self._logger.error("s3_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)
            raise

    async def stop(self) -> None:
        """Stop the S3 storage provider."""
        self._s3_client = None
        self._set_status(ProviderStatus.STOPPED)

    def _generate_unique_path(self, filename: str) -> str:
        """Generate unique path for file in S3.

        Args:
            filename: Original filename

        Returns:
            Unique path with date structure (YYYY/MM/DD/filename-uuid.ext)
        """
        import secrets
        from datetime import datetime
        from pathlib import Path

        now = datetime.now()
        date_path = f"{now.year:04d}/{now.month:02d}/{now.day:02d}"

        # Extract extension
        file_path = Path(filename)
        name = file_path.stem
        ext = file_path.suffix

        # Generate short random suffix
        random_suffix = secrets.token_hex(4)
        unique_filename = f"{name}-{random_suffix}{ext}"

        return f"{date_path}/{unique_filename}"

    async def save(
        self,
        file: io.BytesIO,
        filename: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredFile:
        """Save file to S3.

        Args:
            file: File data
            filename: Original filename
            content_type: MIME type
            metadata: Additional metadata

        Returns:
            StoredFile with S3 URL
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        # Generate unique path
        file_path = self._generate_unique_path(filename)

        # Prepare upload params (public-read so URLs work for Telegram, etc.)
        extra_args: dict[str, Any] = {"ACL": "public-read"}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        # Upload to S3
        file.seek(0)
        file_data = file.read()
        file_size = len(file_data)

        self._s3_client.put_object(
            Bucket=self.bucket,
            Key=file_path,
            Body=file_data,
            **extra_args,
        )

        # Generate URL
        url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{file_path}"

        self._logger.info(
            "file_saved",
            filename=filename,
            path=file_path,
            size=file_size,
            url=url,
        )

        return StoredFile(
            id=str(uuid4()),
            filename=filename,
            path=file_path,
            url=url,
            size=file_size,
            content_type=content_type or "application/octet-stream",
            metadata=metadata or {},
        )

    async def save_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredFile:
        """Save bytes to S3.

        Args:
            data: File data as bytes
            filename: Original filename
            content_type: MIME type
            metadata: Additional metadata

        Returns:
            StoredFile with S3 details
        """
        file = io.BytesIO(data)
        return await self.save(file, filename, content_type, metadata)

    async def save_attachment(self, attachment: Attachment) -> StoredFile:
        """Save attachment to S3.

        Args:
            attachment: Attachment to save

        Returns:
            StoredFile with S3 details
        """
        # Get file data from attachment metadata
        file_data = attachment.metadata.get("telegram_data")
        if not file_data:
            raise ValueError("No file data in attachment metadata")

        file = io.BytesIO(file_data)

        return await self.save(
            file=file,
            filename=attachment.filename,
            content_type=attachment.content_type,
            metadata={
                "attachment_id": attachment.id,
                **attachment.metadata,
            },
        )

    async def get(self, path: str) -> bytes:
        """Get file contents from S3.

        Args:
            path: File path in S3

        Returns:
            File contents as bytes
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        try:
            response = self._s3_client.get_object(Bucket=self.bucket, Key=path)
            return response["Body"].read()

        except Exception as e:
            self._logger.error("s3_get_error", path=path, error=str(e))
            raise FileNotFoundError(f"File not found in S3: {path}") from e

    async def delete(self, path: str) -> bool:
        """Delete file from S3.

        Args:
            path: File path in S3

        Returns:
            True if deleted successfully
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        try:
            self._s3_client.delete_object(Bucket=self.bucket, Key=path)
            self._logger.info("file_deleted", path=path)
            return True

        except Exception as e:
            self._logger.error("s3_delete_error", path=path, error=str(e))
            return False

    async def exists(self, path: str) -> bool:
        """Check if file exists in S3.

        Args:
            path: File path in S3

        Returns:
            True if file exists
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        try:
            self._s3_client.head_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False

    async def list_files(
        self,
        prefix: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        """List files in S3 bucket.

        Args:
            prefix: Optional prefix to filter files
            limit: Maximum number of files to return

        Returns:
            List of file paths
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        params = {"Bucket": self.bucket, "MaxKeys": limit}
        if prefix:
            params["Prefix"] = prefix

        try:
            response = self._s3_client.list_objects_v2(**params)
            contents = response.get("Contents", [])
            return [obj["Key"] for obj in contents]

        except Exception as e:
            self._logger.error("s3_list_error", error=str(e))
            return []

    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a pre-signed URL for accessing the file.

        Args:
            path: File path in S3
            expires_in: URL expiration time in seconds

        Returns:
            Pre-signed URL
        """
        if not self._s3_client:
            raise RuntimeError("S3 client not initialized")

        try:
            url = self._s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": path},
                ExpiresIn=expires_in,
            )
            return url

        except Exception as e:
            self._logger.error("s3_presigned_url_error", path=path, error=str(e))
            return None

    async def health_check(self) -> ProviderHealth:
        """Check S3 storage provider health."""
        if not self._s3_client:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message="S3 client not initialized",
                details={
                    "bucket": self.bucket,
                    "region": self.region,
                },
            )

        try:
            # Try to list objects (just check access)
            self._s3_client.head_bucket(Bucket=self.bucket)

            return ProviderHealth(
                healthy=True,
                status=self.status,
                message="S3 storage is available",
                details={
                    "bucket": self.bucket,
                    "region": self.region,
                },
            )

        except Exception as e:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message=f"S3 storage error: {e}",
                details={
                    "bucket": self.bucket,
                    "region": self.region,
                    "error": str(e),
                },
            )
