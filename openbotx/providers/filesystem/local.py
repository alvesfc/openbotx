"""Local filesystem provider for OpenBotX."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from openbotx.models.enums import ProviderStatus
from openbotx.providers.base import ProviderHealth
from openbotx.providers.filesystem.base import FileInfo, FilesystemProvider


class LocalFilesystemProvider(FilesystemProvider):
    """Local filesystem provider."""

    def __init__(
        self,
        name: str = "local",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize local filesystem provider.

        Args:
            name: Provider name
            config: Provider configuration with 'base_path' key
        """
        super().__init__(name, config)
        self.base_path = Path(config.get("base_path", ".") if config else ".")

    async def initialize(self) -> None:
        """Initialize the local filesystem provider."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the local filesystem provider."""
        self._set_status(ProviderStatus.STARTING)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._set_status(ProviderStatus.RUNNING)
        self._logger.info("local_filesystem_started", path=str(self.base_path))

    async def stop(self) -> None:
        """Stop the local filesystem provider."""
        self._set_status(ProviderStatus.STOPPED)

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to base_path."""
        resolved = (self.base_path / path).resolve()
        # Security check: ensure path is within base_path
        if not str(resolved).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Path {path} is outside base path")
        return resolved

    async def read(self, path: str) -> str:
        """Read file contents."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_text()

    async def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_bytes()

    async def write(self, path: str, content: str) -> bool:
        """Write content to file."""
        try:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            self._logger.info("file_written", path=path)
            return True
        except Exception as e:
            self._logger.error("file_write_error", path=path, error=str(e))
            return False

    async def write_bytes(self, path: str, content: bytes) -> bool:
        """Write bytes to file."""
        try:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)
            self._logger.info("file_written", path=path, size=len(content))
            return True
        except Exception as e:
            self._logger.error("file_write_error", path=path, error=str(e))
            return False

    async def append(self, path: str, content: str) -> bool:
        """Append content to file."""
        try:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "a") as f:
                f.write(content)
            self._logger.info("file_appended", path=path)
            return True
        except Exception as e:
            self._logger.error("file_append_error", path=path, error=str(e))
            return False

    async def delete(self, path: str) -> bool:
        """Delete a file or directory."""
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return False

            if full_path.is_file():
                full_path.unlink()
            else:
                shutil.rmtree(full_path)

            self._logger.info("file_deleted", path=path)
            return True
        except Exception as e:
            self._logger.error("file_delete_error", path=path, error=str(e))
            return False

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        full_path = self._resolve_path(path)
        return full_path.exists()

    async def mkdir(self, path: str) -> bool:
        """Create directory."""
        try:
            full_path = self._resolve_path(path)
            full_path.mkdir(parents=True, exist_ok=True)
            self._logger.info("directory_created", path=path)
            return True
        except Exception as e:
            self._logger.error("mkdir_error", path=path, error=str(e))
            return False

    async def list_dir(self, path: str = "") -> list[FileInfo]:
        """List directory contents."""
        full_path = self._resolve_path(path)
        if not full_path.exists() or not full_path.is_dir():
            return []

        files = []
        for item in full_path.iterdir():
            stat = item.stat()
            files.append(
                FileInfo(
                    path=str(item.relative_to(self.base_path)),
                    name=item.name,
                    is_file=item.is_file(),
                    is_directory=item.is_dir(),
                    size=stat.st_size if item.is_file() else 0,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                )
            )

        return files

    async def get_info(self, path: str) -> FileInfo | None:
        """Get file/directory info."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            return None

        stat = full_path.stat()
        return FileInfo(
            path=path,
            name=full_path.name,
            is_file=full_path.is_file(),
            is_directory=full_path.is_dir(),
            size=stat.st_size if full_path.is_file() else 0,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            created_at=datetime.fromtimestamp(stat.st_ctime),
        )

    async def copy(self, src: str, dst: str) -> bool:
        """Copy file or directory."""
        try:
            src_path = self._resolve_path(src)
            dst_path = self._resolve_path(dst)

            if not src_path.exists():
                return False

            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path.is_file():
                shutil.copy2(src_path, dst_path)
            else:
                shutil.copytree(src_path, dst_path)

            self._logger.info("file_copied", src=src, dst=dst)
            return True
        except Exception as e:
            self._logger.error("file_copy_error", src=src, dst=dst, error=str(e))
            return False

    async def move(self, src: str, dst: str) -> bool:
        """Move file or directory."""
        try:
            src_path = self._resolve_path(src)
            dst_path = self._resolve_path(dst)

            if not src_path.exists():
                return False

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))

            self._logger.info("file_moved", src=src, dst=dst)
            return True
        except Exception as e:
            self._logger.error("file_move_error", src=src, dst=dst, error=str(e))
            return False

    async def health_check(self) -> ProviderHealth:
        """Check local filesystem provider health."""
        try:
            # Check if base path is writable
            test_file = self.base_path / ".health_check"
            test_file.write_text("test")
            test_file.unlink()

            return ProviderHealth(
                healthy=True,
                status=self.status,
                message="Local filesystem is available",
                details={
                    "base_path": str(self.base_path),
                },
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message=f"Filesystem error: {e}",
                details={
                    "base_path": str(self.base_path),
                    "error": str(e),
                },
            )
