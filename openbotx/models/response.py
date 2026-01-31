"""Agent response models for OpenBotX."""

from pydantic import BaseModel, Field

from openbotx.models.enums import GatewayType, ResponseCapability, ResponseContentType


class ResponseContent(BaseModel):
    """Individual content item in agent response."""

    type: ResponseContentType
    text: str | None = None
    url: str | None = None  # For images, videos, audios
    path: str | None = None  # Local path if applicable
    metadata: dict[str, str] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """Structured response from agent.

    This response contains different types of content that gateways
    can render according to their capabilities.

    If a gateway doesn't support a content type (e.g., CLI with images),
    it should fall back to text representation.
    """

    contents: list[ResponseContent] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    needs_learning: bool = False
    learning_topic: str | None = None

    def add_error(self, text: str) -> None:
        """Add error message."""
        self.contents.append(ResponseContent(type=ResponseContentType.ERROR, text=text))

    def add_warning(self, text: str) -> None:
        """Add warning message."""
        self.contents.append(ResponseContent(type=ResponseContentType.WARNING, text=text))

    def add_info(self, text: str) -> None:
        """Add info message."""
        self.contents.append(ResponseContent(type=ResponseContentType.INFO, text=text))

    def add_success(self, text: str) -> None:
        """Add success message."""
        self.contents.append(ResponseContent(type=ResponseContentType.SUCCESS, text=text))

    def add_text(self, text: str) -> None:
        """Add plain text message."""
        self.contents.append(ResponseContent(type=ResponseContentType.TEXT, text=text))

    def add_image(self, url: str | None = None, path: str | None = None) -> None:
        """Add image."""
        self.contents.append(ResponseContent(type=ResponseContentType.IMAGE, url=url, path=path))

    def add_video(self, url: str | None = None, path: str | None = None) -> None:
        """Add video."""
        self.contents.append(ResponseContent(type=ResponseContentType.VIDEO, url=url, path=path))

    def add_audio(self, url: str | None = None, path: str | None = None) -> None:
        """Add audio."""
        self.contents.append(ResponseContent(type=ResponseContentType.AUDIO, url=url, path=path))

    def get_by_type(self, content_type: ResponseContentType) -> list[ResponseContent]:
        """Get all contents of specific type."""
        return [c for c in self.contents if c.type == content_type]

    def get_errors(self) -> list[ResponseContent]:
        """Get all error messages."""
        return self.get_by_type(ResponseContentType.ERROR)

    def get_warnings(self) -> list[ResponseContent]:
        """Get all warning messages."""
        return self.get_by_type(ResponseContentType.WARNING)

    def get_infos(self) -> list[ResponseContent]:
        """Get all info messages."""
        return self.get_by_type(ResponseContentType.INFO)

    def get_successes(self) -> list[ResponseContent]:
        """Get all success messages."""
        return self.get_by_type(ResponseContentType.SUCCESS)

    def get_texts(self) -> list[ResponseContent]:
        """Get all text messages."""
        return self.get_by_type(ResponseContentType.TEXT)

    def get_images(self) -> list[ResponseContent]:
        """Get all images."""
        return self.get_by_type(ResponseContentType.IMAGE)

    def get_videos(self) -> list[ResponseContent]:
        """Get all videos."""
        return self.get_by_type(ResponseContentType.VIDEO)

    def get_audios(self) -> list[ResponseContent]:
        """Get all audios."""
        return self.get_by_type(ResponseContentType.AUDIO)

    def to_plain_text(self) -> str:
        """Convert all content to plain text representation.

        This is used as fallback for gateways that don't support rich content.
        """
        lines = []

        for content in self.contents:
            if content.type == ResponseContentType.ERROR:
                lines.append(f"❌ ERROR: {content.text}")
            elif content.type == ResponseContentType.WARNING:
                lines.append(f"⚠️ WARNING: {content.text}")
            elif content.type == ResponseContentType.INFO:
                lines.append(f"ℹ️ INFO: {content.text}")
            elif content.type == ResponseContentType.SUCCESS:
                lines.append(f"✅ SUCCESS: {content.text}")
            elif content.type == ResponseContentType.TEXT:
                lines.append(content.text or "")
            elif content.type == ResponseContentType.IMAGE:
                lines.append(f"🖼️ Image: {content.url or content.path}")
            elif content.type == ResponseContentType.VIDEO:
                lines.append(f"🎥 Video: {content.url or content.path}")
            elif content.type == ResponseContentType.AUDIO:
                lines.append(f"🔊 Audio: {content.url or content.path}")

        return "\n".join(lines)

    @property
    def text(self) -> str:
        """Get plain text representation (for backward compatibility)."""
        return self.to_plain_text()

    def to_outbound_message(
        self,
        channel_id: str,
        gateway_capabilities: set[ResponseCapability],
        gateway_type: GatewayType,
        reply_to: str | None = None,
        correlation_id: str | None = None,
    ):
        """Convert agent response to outbound message based on gateway capabilities.

        Args:
            channel_id: Channel ID
            gateway_capabilities: What the gateway supports
            gateway_type: Gateway type enum
            reply_to: Message ID to reply to
            correlation_id: Correlation ID for tracking

        Returns:
            OutboundMessage formatted for the gateway's capabilities
        """
        from openbotx.models.message import Attachment, OutboundMessage

        text_parts = []
        attachments = []

        for content in self.contents:
            # Text-based content types
            if content.type in (
                ResponseContentType.TEXT,
                ResponseContentType.ERROR,
                ResponseContentType.WARNING,
                ResponseContentType.INFO,
                ResponseContentType.SUCCESS,
            ):
                if content.type == ResponseContentType.ERROR:
                    text_parts.append(f"❌ ERROR: {content.text}")
                elif content.type == ResponseContentType.WARNING:
                    text_parts.append(f"⚠️ WARNING: {content.text}")
                elif content.type == ResponseContentType.INFO:
                    text_parts.append(f"ℹ️ INFO: {content.text}")
                elif content.type == ResponseContentType.SUCCESS:
                    text_parts.append(f"✅ SUCCESS: {content.text}")
                else:  # TEXT
                    text_parts.append(content.text or "")

            # Media content - only add if gateway supports it
            elif content.type == ResponseContentType.IMAGE:
                if ResponseCapability.IMAGE in gateway_capabilities:
                    # Gateway supports images, add as attachment
                    if content.path or content.url:
                        attachments.append(
                            Attachment(
                                filename=content.path or content.url or "image.png",
                                content_type="image/png",
                                size=0,
                                storage_path=content.path,
                                url=content.url,
                                metadata=content.metadata,
                            )
                        )
                else:
                    # Gateway doesn't support images, add as text
                    text_parts.append(f"🖼️ Image: {content.url or content.path}")

            elif content.type == ResponseContentType.VIDEO:
                if ResponseCapability.VIDEO in gateway_capabilities:
                    if content.path or content.url:
                        attachments.append(
                            Attachment(
                                filename=content.path or content.url or "video.mp4",
                                content_type="video/mp4",
                                size=0,
                                storage_path=content.path,
                                url=content.url,
                                metadata=content.metadata,
                            )
                        )
                else:
                    text_parts.append(f"🎥 Video: {content.url or content.path}")

            elif content.type == ResponseContentType.AUDIO:
                if ResponseCapability.AUDIO in gateway_capabilities:
                    if content.path or content.url:
                        attachments.append(
                            Attachment(
                                filename=content.path or content.url or "audio.mp3",
                                content_type="audio/mpeg",
                                size=0,
                                storage_path=content.path,
                                url=content.url,
                                metadata=content.metadata,
                            )
                        )
                else:
                    text_parts.append(f"🔊 Audio: {content.url or content.path}")

        return OutboundMessage(
            channel_id=channel_id,
            reply_to=reply_to,
            gateway=gateway_type,
            text="\n".join(text_parts) if text_parts else None,
            attachments=attachments,
            correlation_id=correlation_id,
        )
