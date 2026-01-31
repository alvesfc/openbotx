"""Base filesystem provider for OpenBotX."""

from abc import abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from openbotx.models.enums import ProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth


class FileInfo(BaseModel):
    """Information about a file."""

    path: str
    name: str
    is_file: bool
    is_directory: bool
    size: int = 0
    modified_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilesystemProvider(ProviderBase):
    """Base class for filesystem providers."""

    provider_type = ProviderType.FILESYSTEM

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize filesystem provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self.base_path = config.get("base_path", ".") if config else "."

    @abstractmethod
    async def read(self, path: str) -> str:
        """Read file contents.

        Args:
            path: File path (relative to base_path)

        Returns:
            File contents as string
        """
        pass

    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes.

        Args:
            path: File path (relative to base_path)

        Returns:
            File contents as bytes
        """
        pass

    @abstractmethod
    async def write(self, path: str, content: str) -> bool:
        """Write content to file.

        Args:
            path: File path (relative to base_path)
            content: Content to write

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def write_bytes(self, path: str, content: bytes) -> bool:
        """Write bytes to file.

        Args:
            path: File path (relative to base_path)
            content: Bytes to write

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def append(self, path: str, content: str) -> bool:
        """Append content to file.

        Args:
            path: File path (relative to base_path)
            content: Content to append

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file or directory.

        Args:
            path: File path (relative to base_path)

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if path exists.

        Args:
            path: File path (relative to base_path)

        Returns:
            True if exists
        """
        pass

    @abstractmethod
    async def mkdir(self, path: str) -> bool:
        """Create directory.

        Args:
            path: Directory path (relative to base_path)

        Returns:
            True if created successfully
        """
        pass

    @abstractmethod
    async def list_dir(self, path: str = "") -> list[FileInfo]:
        """List directory contents.

        Args:
            path: Directory path (relative to base_path)

        Returns:
            List of file info
        """
        pass

    @abstractmethod
    async def get_info(self, path: str) -> FileInfo | None:
        """Get file/directory info.

        Args:
            path: Path (relative to base_path)

        Returns:
            FileInfo or None if not found
        """
        pass

    @abstractmethod
    async def copy(self, src: str, dst: str) -> bool:
        """Copy file or directory.

        Args:
            src: Source path
            dst: Destination path

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def move(self, src: str, dst: str) -> bool:
        """Move file or directory.

        Args:
            src: Source path
            dst: Destination path

        Returns:
            True if successful
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check filesystem provider health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Filesystem provider is available",
            details={
                "base_path": self.base_path,
            },
        )
