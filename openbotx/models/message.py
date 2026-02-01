"""Message models for OpenBotX."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from openbotx.models.enums import (
    GatewayType,
    MessageDirective,
    MessageStatus,
    MessageType,
    PromptMode,
    ResponseCapability,
    ToolProfile,
)


class ParsedDirectives(BaseModel):
    """Parsed directives from message text."""

    directives: list[MessageDirective] = Field(default_factory=list)
    clean_text: str = ""
    prompt_mode: PromptMode = PromptMode.FULL
    tool_profile: ToolProfile = ToolProfile.FULL
    elevated: bool = False

    @property
    def has_think(self) -> bool:
        """Check if think directive is present."""
        return MessageDirective.THINK in self.directives

    @property
    def has_verbose(self) -> bool:
        """Check if verbose directive is present."""
        return MessageDirective.VERBOSE in self.directives

    @property
    def has_reasoning(self) -> bool:
        """Check if reasoning directive is present."""
        return MessageDirective.REASONING in self.directives


class Attachment(BaseModel):
    """Attachment model for messages."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    content_type: str
    size: int
    storage_path: str | None = None
    url: str | None = None
    data: bytes | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_audio(self) -> bool:
        """Check if attachment is audio."""
        return self.content_type.startswith("audio/")

    @property
    def is_image(self) -> bool:
        """Check if attachment is image."""
        return self.content_type.startswith("image/")

    @property
    def is_video(self) -> bool:
        """Check if attachment is video."""
        return self.content_type.startswith("video/")


class InboundMessage(BaseModel):
    """Inbound message from a gateway."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    channel_id: str
    user_id: str | None = None
    gateway: GatewayType
    message_type: MessageType = MessageType.TEXT
    text: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    status: MessageStatus = MessageStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reply_to: str | None = None
    directives: ParsedDirectives | None = None

    @property
    def has_attachments(self) -> bool:
        """Check if message has attachments."""
        return len(self.attachments) > 0

    @property
    def has_audio(self) -> bool:
        """Check if message has audio attachments."""
        return any(a.is_audio for a in self.attachments)

    def get_content(self) -> str:
        """Get message content (text or transcription)."""
        if self.directives and self.directives.clean_text:
            return self.directives.clean_text
        return self.text or ""

    def get_prompt_mode(self) -> PromptMode:
        """Get the prompt mode from directives."""
        if self.directives:
            return self.directives.prompt_mode
        return PromptMode.FULL

    def get_tool_profile(self) -> ToolProfile:
        """Get the tool profile from directives."""
        if self.directives:
            return self.directives.tool_profile
        return ToolProfile.FULL


class OutboundMessage(BaseModel):
    """Outbound message to send via gateway."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    channel_id: str
    reply_to: str | None = None
    gateway: GatewayType
    response_type: ResponseCapability = ResponseCapability.TEXT
    text: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageContext(BaseModel):
    """Context for message processing."""

    message: InboundMessage
    history: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    user_summary: str | None = None
    conversation_summary: str | None = None
    available_skills: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    token_budget: int = 100000
    estimated_tokens: int = 0
    prompt_mode: PromptMode = PromptMode.FULL
    tool_profile: ToolProfile = ToolProfile.FULL
    show_reasoning: bool = False
    elevated_permissions: bool = False


class ProcessingResult(BaseModel):
    """Result of message processing."""

    success: bool
    response: OutboundMessage | None = None
    error: str | None = None
    tokens_used: int = 0
    tools_called: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    processing_time_ms: int = 0
