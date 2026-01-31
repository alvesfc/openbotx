"""Screenshot tool - Capture screenshots and save to storage."""

import io
import platform
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import ImageGrab

from openbotx.core.tools_registry import tool
from openbotx.models.enums import ProviderType
from openbotx.models.tool_result import ToolResult
from openbotx.providers.base import get_provider_registry
from openbotx.providers.storage.base import StorageProvider


def _get_storage_provider() -> StorageProvider | None:
    """Get storage provider from registry."""
    registry = get_provider_registry()
    provider = registry.get(ProviderType.STORAGE)
    if isinstance(provider, StorageProvider):
        return provider
    return None


@tool(
    name="take_screenshot",
    description="Take a screenshot of the current screen and save it to storage. Returns a structured result with the screenshot path.",
)
async def tool_take_screenshot(filename: str | None = None) -> ToolResult:
    """Take a screenshot and save it to storage.

    Args:
        filename: Optional filename for the screenshot (default: screenshot-TIMESTAMP.png)

    Returns:
        Structured tool result with screenshot information
    """
    result = ToolResult()

    try:
        # Get storage provider
        storage = _get_storage_provider()
        if not storage:
            result.add_error("No storage provider configured")
            return result

        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            filename = f"screenshot-{timestamp}.png"

        # Ensure .png extension
        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename += ".png"

        # Create temporary file for screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            # Detect OS and take screenshot to temp file
            system = platform.system()

            if system == "Darwin":  # macOS
                _take_screenshot_macos(tmp_path)
            elif system == "Linux":
                _take_screenshot_linux(tmp_path)
            elif system == "Windows":
                _take_screenshot_windows(tmp_path)
            else:
                result.add_error(f"Unsupported operating system: {system}")
                return result

            # Verify file was created
            if not tmp_path.exists():
                result.add_error("Screenshot file was not created")
                return result

            # Read screenshot data
            screenshot_data = tmp_path.read_bytes()

            # Upload to storage
            stored_file = await storage.save(
                file=io.BytesIO(screenshot_data),
                filename=filename,
                content_type="image/png",
                metadata={"source": "screenshot_tool"},
            )

            result_path = stored_file.url or stored_file.path

            result.add_image(
                path=result_path if not stored_file.url else None, url=stored_file.url
            )

            return result

        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

    except Exception as e:
        result.add_error(f"Error taking screenshot: {e}")
        return result


def _take_screenshot_macos(filepath: Path) -> None:
    """Take screenshot on macOS using screencapture."""
    subprocess.run(
        ["screencapture", "-x", str(filepath)],
        check=True,
        capture_output=True,
    )


def _take_screenshot_linux(filepath: Path) -> None:
    """Take screenshot on Linux using scrot or gnome-screenshot."""
    # Try scrot first (most common)
    try:
        subprocess.run(
            ["scrot", str(filepath)],
            check=True,
            capture_output=True,
        )
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Try gnome-screenshot
    try:
        subprocess.run(
            ["gnome-screenshot", "-f", str(filepath)],
            check=True,
            capture_output=True,
        )
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Try import (ImageMagick)
    try:
        subprocess.run(
            ["import", "-window", "root", str(filepath)],
            check=True,
            capture_output=True,
        )
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to Python PIL
    screenshot = ImageGrab.grab()
    screenshot.save(str(filepath))


def _take_screenshot_windows(filepath: Path) -> None:
    """Take screenshot on Windows using PIL."""
    screenshot = ImageGrab.grab()
    screenshot.save(str(filepath))
