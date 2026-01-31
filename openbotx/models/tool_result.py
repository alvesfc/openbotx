"""Tool result models for OpenBotX.

Tools should return structured results instead of plain strings,
making the system more consistent and predictable.
"""

from typing import Any

from pydantic import BaseModel, Field

from openbotx.models.enums import ResponseContentType


class ToolResultContent(BaseModel):
    """Individual content item in a tool result."""

    type: ResponseContentType
    text: str | None = None
    url: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Structured result from a tool execution.

    Tools should return this instead of plain strings to make
    the system more predictable and type-safe.
    """

    success: bool = True
    contents: list[ToolResultContent] = Field(default_factory=list)
    error: str | None = None

    def add_text(self, text: str) -> None:
        """Add text content."""
        self.contents.append(ToolResultContent(type=ResponseContentType.TEXT, text=text))

    def add_info(self, text: str) -> None:
        """Add info message."""
        self.contents.append(ToolResultContent(type=ResponseContentType.INFO, text=text))

    def add_success(self, text: str) -> None:
        """Add success message."""
        self.contents.append(ToolResultContent(type=ResponseContentType.SUCCESS, text=text))

    def add_warning(self, text: str) -> None:
        """Add warning message."""
        self.contents.append(ToolResultContent(type=ResponseContentType.WARNING, text=text))

    def add_error(self, text: str) -> None:
        """Add error message."""
        self.success = False
        self.error = text
        self.contents.append(ToolResultContent(type=ResponseContentType.ERROR, text=text))

    def add_image(self, path: str | None = None, url: str | None = None) -> None:
        """Add image."""
        self.contents.append(ToolResultContent(type=ResponseContentType.IMAGE, path=path, url=url))

    def add_video(self, path: str | None = None, url: str | None = None) -> None:
        """Add video."""
        self.contents.append(ToolResultContent(type=ResponseContentType.VIDEO, path=path, url=url))

    def add_audio(self, path: str | None = None, url: str | None = None) -> None:
        """Add audio."""
        self.contents.append(ToolResultContent(type=ResponseContentType.AUDIO, path=path, url=url))

    def to_string(self) -> str:
        """Convert to string representation (for backward compatibility)."""
        if self.error:
            return f"Error: {self.error}"

        parts = []
        for content in self.contents:
            if content.type == ResponseContentType.TEXT:
                parts.append(content.text or "")
            elif content.type == ResponseContentType.INFO:
                parts.append(f"ℹ️ {content.text}")
            elif content.type == ResponseContentType.SUCCESS:
                parts.append(f"✅ {content.text}")
            elif content.type == ResponseContentType.WARNING:
                parts.append(f"⚠️ {content.text}")
            elif content.type == ResponseContentType.ERROR:
                parts.append(f"❌ {content.text}")
            elif content.type == ResponseContentType.IMAGE:
                parts.append(f"🖼️ Image: {content.path or content.url}")
            elif content.type == ResponseContentType.VIDEO:
                parts.append(f"🎥 Video: {content.path or content.url}")
            elif content.type == ResponseContentType.AUDIO:
                parts.append(f"🔊 Audio: {content.path or content.url}")

        return "\n".join(parts) if parts else "Success"
