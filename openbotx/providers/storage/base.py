"""Base storage provider for OpenBotX."""

from abc import abstractmethod
from datetime import UTC, datetime
from typing import Any, BinaryIO

from pydantic import BaseModel, Field

from openbotx.models.enums import ProviderType, StorageType
from openbotx.providers.base import ProviderBase, ProviderHealth


class StoredFile(BaseModel):
    """Metadata for a stored file."""

    id: str
    filename: str
    content_type: str
    size: int
    path: str
    url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class StorageProvider(ProviderBase):
    """Base class for storage providers."""

    provider_type = ProviderType.STORAGE
    storage_type: StorageType

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize storage provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)

    @abstractmethod
    async def save(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredFile:
        """Save a file to storage.

        Args:
            file: File-like object to save
            filename: Original filename
            content_type: MIME type
            metadata: Optional metadata

        Returns:
            StoredFile with path and metadata
        """
        pass

    @abstractmethod
    async def save_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredFile:
        """Save bytes to storage.

        Args:
            data: Bytes to save
            filename: Original filename
            content_type: MIME type
            metadata: Optional metadata

        Returns:
            StoredFile with path and metadata
        """
        pass

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """Get file contents.

        Args:
            path: File path in storage

        Returns:
            File contents as bytes
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: File path in storage

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: File path in storage

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def list_files(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> list[StoredFile]:
        """List files in storage.

        Args:
            prefix: Path prefix to filter by
            limit: Maximum number of files to return

        Returns:
            List of stored files
        """
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a URL for accessing the file.

        Args:
            path: File path in storage
            expires_in: URL expiration time in seconds

        Returns:
            URL or None if not supported
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check storage provider health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Storage provider is available",
            details={
                "storage_type": self.storage_type.value,
            },
        )
