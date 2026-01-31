"""Local filesystem storage provider for OpenBotX."""

import mimetypes
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from openbotx.models.enums import ProviderStatus, StorageType
from openbotx.models.message import Attachment
from openbotx.providers.base import ProviderHealth
from openbotx.providers.storage.base import StorageProvider, StoredFile


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider."""

    storage_type = StorageType.LOCAL

    def __init__(
        self,
        name: str = "local",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize local storage provider.

        Args:
            name: Provider name
            config: Provider configuration with 'path' key
        """
        super().__init__(name, config)
        self.base_path = Path(config.get("path", "./media") if config else "./media")

    async def initialize(self) -> None:
        """Initialize the local storage provider."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the local storage provider."""
        self._set_status(ProviderStatus.STARTING)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._set_status(ProviderStatus.RUNNING)
        self._logger.info("local_storage_started", path=str(self.base_path))

    async def stop(self) -> None:
        """Stop the local storage provider."""
        self._set_status(ProviderStatus.STOPPED)

    def _generate_path(self, filename: str) -> str:
        """Generate a unique storage path for a file."""
        # Organize by date
        now = datetime.now(UTC)
        date_path = f"{now.year}/{now.month:02d}/{now.day:02d}"

        # Add UUID to ensure uniqueness
        file_id = str(uuid4())[:8]
        name, ext = os.path.splitext(filename)
        unique_filename = f"{name}-{file_id}{ext}"

        return f"{date_path}/{unique_filename}"

    async def save(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredFile:
        """Save a file to local storage."""
        rel_path = self._generate_path(filename)
        full_path = self.base_path / rel_path

        # Ensure directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Save file
        with open(full_path, "wb") as f:
            shutil.copyfileobj(file, f)

        size = full_path.stat().st_size

        self._logger.info(
            "file_saved",
            filename=filename,
            path=rel_path,
            size=size,
        )

        return StoredFile(
            id=str(uuid4()),
            filename=filename,
            content_type=content_type,
            size=size,
            path=rel_path,
            metadata=metadata or {},
        )

    async def save_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredFile:
        """Save bytes to local storage."""
        rel_path = self._generate_path(filename)
        full_path = self.base_path / rel_path

        # Ensure directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Save file
        with open(full_path, "wb") as f:
            f.write(data)

        self._logger.info(
            "file_saved",
            filename=filename,
            path=rel_path,
            size=len(data),
        )

        return StoredFile(
            id=str(uuid4()),
            filename=filename,
            content_type=content_type,
            size=len(data),
            path=rel_path,
            metadata=metadata or {},
        )

    async def save_attachment(self, attachment: Attachment) -> StoredFile:
        """Save attachment to local storage.

        Args:
            attachment: Attachment to save

        Returns:
            StoredFile with local path
        """
        if not attachment.data:
            raise ValueError("No file data in attachment")

        return await self.save_bytes(
            data=attachment.data,
            filename=attachment.filename,
            content_type=attachment.content_type,
            metadata={
                "attachment_id": attachment.id,
                **attachment.metadata,
            },
        )

    async def get(self, path: str) -> bytes:
        """Get file contents."""
        full_path = self.base_path / path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(full_path, "rb") as f:
            return f.read()

    async def delete(self, path: str) -> bool:
        """Delete a file from storage."""
        full_path = self.base_path / path

        if not full_path.exists():
            return False

        full_path.unlink()
        self._logger.info("file_deleted", path=path)
        return True

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self.base_path / path
        return full_path.exists()

    async def list_files(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> list[StoredFile]:
        """List files in storage."""
        search_path = self.base_path / prefix if prefix else self.base_path

        if not search_path.exists():
            return []

        files = []
        count = 0

        for item in search_path.rglob("*"):
            if item.is_file() and count < limit:
                rel_path = str(item.relative_to(self.base_path))
                stat = item.stat()

                content_type, _ = mimetypes.guess_type(str(item))

                files.append(
                    StoredFile(
                        id=str(uuid4()),
                        filename=item.name,
                        content_type=content_type or "application/octet-stream",
                        size=stat.st_size,
                        path=rel_path,
                        created_at=datetime.fromtimestamp(stat.st_ctime),
                    )
                )
                count += 1

        return files

    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a URL for accessing the file.

        Local storage doesn't support URLs, returns None.
        """
        return None

    async def health_check(self) -> ProviderHealth:
        """Check local storage provider health."""
        try:
            # Check if base path is writable
            test_file = self.base_path / ".health_check"
            test_file.write_text("test")
            test_file.unlink()

            return ProviderHealth(
                healthy=True,
                status=self.status,
                message="Local storage is available",
                details={
                    "storage_type": self.storage_type.value,
                    "path": str(self.base_path),
                },
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message=f"Local storage error: {e}",
                details={
                    "storage_type": self.storage_type.value,
                    "path": str(self.base_path),
                    "error": str(e),
                },
            )
