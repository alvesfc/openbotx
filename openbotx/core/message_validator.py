"""Message validator for OpenBotX - validates incoming messages."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.models.message import InboundMessage


class ValidationErrorType(str, Enum):
    """Type of validation error."""

    TEXT_TOO_LONG = "text_too_long"
    TEXT_EMPTY = "text_empty"
    TOO_MANY_ATTACHMENTS = "too_many_attachments"
    ATTACHMENT_TOO_LARGE = "attachment_too_large"
    INVALID_ATTACHMENT_TYPE = "invalid_attachment_type"
    INVALID_CHANNEL = "invalid_channel"
    INVALID_USER = "invalid_user"


@dataclass
class ValidationError:
    """A validation error."""

    error_type: ValidationErrorType
    message: str
    field_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of message validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def add_error(
        self,
        error_type: ValidationErrorType,
        message: str,
        field: str | None = None,
        **details: Any,
    ) -> None:
        """Add a validation error."""
        self.errors.append(
            ValidationError(
                error_type=error_type,
                message=message,
                field_name=field,
                details=details,
            )
        )
        self.valid = False

    @property
    def error_messages(self) -> list[str]:
        """Get list of error messages."""
        return [e.message for e in self.errors]


class MessageValidator:
    """Validates incoming messages before processing."""

    # default allowed attachment types
    DEFAULT_ALLOWED_TYPES = {
        # images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        # audio
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "audio/webm",
        "audio/mp4",
        # video
        "video/mp4",
        "video/webm",
        "video/quicktime",
        # documents
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/json",
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize message validator.

        Args:
            config: Validation configuration
        """
        config = config or {}
        self._max_text_length = config.get("max_text_length", 50000)
        self._max_attachments = config.get("max_attachments", 10)
        self._max_attachment_size = config.get("max_attachment_size", 50 * 1024 * 1024)
        self._require_text = config.get("require_text", False)
        self._allowed_attachment_types = set(
            config.get("allowed_attachment_types", self.DEFAULT_ALLOWED_TYPES)
        )
        self._blocked_users: set[str] = set(config.get("blocked_users", []))
        self._logger = get_logger("message_validator")

    def validate(self, message: InboundMessage) -> ValidationResult:
        """Validate a message.

        Args:
            message: Message to validate

        Returns:
            ValidationResult with valid flag and any errors
        """
        result = ValidationResult(valid=True)

        # check text
        self._validate_text(message, result)

        # check attachments
        self._validate_attachments(message, result)

        # check channel
        self._validate_channel(message, result)

        # check user
        self._validate_user(message, result)

        if not result.valid:
            self._logger.warning(
                "message_validation_failed",
                message_id=message.id,
                errors=[e.error_type.value for e in result.errors],
            )

        return result

    def _validate_text(self, message: InboundMessage, result: ValidationResult) -> None:
        """Validate message text."""
        text = message.text

        # check if text is required
        if self._require_text and not text and not message.has_attachments:
            result.add_error(
                ValidationErrorType.TEXT_EMPTY,
                "Message text is required",
                field="text",
            )
            return

        if not text:
            return

        # check text length
        if len(text) > self._max_text_length:
            result.add_error(
                ValidationErrorType.TEXT_TOO_LONG,
                f"Message text exceeds maximum length of {self._max_text_length} characters",
                field="text",
                length=len(text),
                max_length=self._max_text_length,
            )

    def _validate_attachments(self, message: InboundMessage, result: ValidationResult) -> None:
        """Validate message attachments."""
        if not message.attachments:
            return

        # check attachment count
        if len(message.attachments) > self._max_attachments:
            result.add_error(
                ValidationErrorType.TOO_MANY_ATTACHMENTS,
                f"Too many attachments (max: {self._max_attachments})",
                field="attachments",
                count=len(message.attachments),
                max_count=self._max_attachments,
            )

        # validate each attachment
        for i, attachment in enumerate(message.attachments):
            # check size
            if attachment.size > self._max_attachment_size:
                result.add_error(
                    ValidationErrorType.ATTACHMENT_TOO_LARGE,
                    f"Attachment '{attachment.filename}' exceeds maximum size",
                    field=f"attachments[{i}]",
                    size=attachment.size,
                    max_size=self._max_attachment_size,
                )

            # check type
            if self._allowed_attachment_types:
                # check exact type or category
                type_allowed = (
                    attachment.content_type in self._allowed_attachment_types
                    or attachment.content_type.split("/")[0] + "/*"
                    in self._allowed_attachment_types
                )

                if not type_allowed:
                    result.add_error(
                        ValidationErrorType.INVALID_ATTACHMENT_TYPE,
                        f"Attachment type '{attachment.content_type}' not allowed",
                        field=f"attachments[{i}]",
                        content_type=attachment.content_type,
                    )

    def _validate_channel(self, message: InboundMessage, result: ValidationResult) -> None:
        """Validate channel ID."""
        if not message.channel_id:
            result.add_error(
                ValidationErrorType.INVALID_CHANNEL,
                "Channel ID is required",
                field="channel_id",
            )

    def _validate_user(self, message: InboundMessage, result: ValidationResult) -> None:
        """Validate user ID."""
        if message.user_id and message.user_id in self._blocked_users:
            result.add_error(
                ValidationErrorType.INVALID_USER,
                "User is blocked",
                field="user_id",
                user_id=message.user_id,
            )


# global instance
_validator: MessageValidator | None = None


def get_message_validator() -> MessageValidator:
    """Get the global message validator instance."""
    global _validator
    if _validator is None:
        _validator = MessageValidator()
    return _validator


def set_message_validator(validator: MessageValidator) -> None:
    """Set the global message validator instance."""
    global _validator
    _validator = validator
