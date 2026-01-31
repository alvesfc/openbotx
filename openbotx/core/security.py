"""Security module for OpenBotX - prompt injection detection and policy enforcement."""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import SecurityViolationType


class SecurityViolation(BaseModel):
    """Record of a security violation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    violation_type: SecurityViolationType
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    severity: str = "medium"  # low, medium, high, critical
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel_id: str | None = None
    user_id: str | None = None
    blocked: bool = True


class SecurityConfig(BaseModel):
    """Security configuration."""

    prompt_injection_detection: bool = True
    tool_approval_required: bool = False
    max_tokens_per_request: int = 100000
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)


class SecurityManager:
    """Security manager for prompt injection detection and policy enforcement."""

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        # Direct instruction override
        r"ignore\s+(previous|above|all)\s+(instructions?|prompts?)",
        r"disregard\s+(previous|above|all)\s+(instructions?|prompts?)",
        r"forget\s+(previous|above|all)\s+(instructions?|prompts?)",
        # Role playing attacks
        r"you\s+are\s+(now|actually)\s+",
        r"pretend\s+(to\s+be|you\s+are)",
        r"act\s+as\s+(if\s+you|a\s+)",
        r"from\s+now\s+on\s+(you|ignore)",
        # System prompt extraction
        r"(reveal|show|display|output)\s+(your|the)\s+(system|initial)\s+prompt",
        r"what\s+(is|are)\s+your\s+(system|initial)\s+(prompt|instructions)",
        r"repeat\s+(your|the)\s+(system|initial)\s+(prompt|instructions)",
        # Jailbreak attempts
        r"(dan|dude|evil)\s*mode",
        r"do\s+anything\s+now",
        r"jailbreak",
        r"bypass\s+(safety|security|filters?)",
        # Delimiter injection
        r"\[system\]",
        r"\[assistant\]",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"```system",
        # Encoding attacks
        r"base64\s*decode",
        r"rot13",
        r"hex\s*decode",
    ]

    # Compiled patterns
    _compiled_patterns: list[re.Pattern[str]] = []

    def __init__(self, config: SecurityConfig | None = None) -> None:
        """Initialize security manager.

        Args:
            config: Security configuration
        """
        self.config = config or SecurityConfig()
        self._logger = get_logger("security")
        self._violations: list[SecurityViolation] = []

        # Compile patterns
        if not self._compiled_patterns:
            self._compiled_patterns = [
                re.compile(pattern, re.IGNORECASE) for pattern in self.INJECTION_PATTERNS
            ]

    def check_prompt_injection(
        self,
        text: str,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> SecurityViolation | None:
        """Check text for prompt injection attempts.

        Args:
            text: Text to check
            channel_id: Channel ID for logging
            user_id: User ID for logging

        Returns:
            SecurityViolation if detected, None otherwise
        """
        if not self.config.prompt_injection_detection:
            return None

        text_lower = text.lower()

        for pattern in self._compiled_patterns:
            match = pattern.search(text_lower)
            if match:
                violation = SecurityViolation(
                    violation_type=SecurityViolationType.PROMPT_INJECTION,
                    message=f"Prompt injection detected: {match.group()}",
                    details={
                        "pattern": pattern.pattern,
                        "matched": match.group(),
                        "position": match.span(),
                    },
                    severity="high",
                    channel_id=channel_id,
                    user_id=user_id,
                )

                self._violations.append(violation)
                self._logger.warning(
                    "prompt_injection_detected",
                    violation_id=violation.id,
                    pattern=pattern.pattern,
                    channel_id=channel_id,
                    user_id=user_id,
                )

                return violation

        return None

    def check_tool_allowed(
        self,
        tool_name: str,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> SecurityViolation | None:
        """Check if a tool is allowed.

        Args:
            tool_name: Tool name to check
            channel_id: Channel ID for logging
            user_id: User ID for logging

        Returns:
            SecurityViolation if tool is denied, None if allowed
        """
        # Check denied list first
        if tool_name in self.config.denied_tools:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.FORBIDDEN_ACTION,
                message=f"Tool '{tool_name}' is denied",
                details={"tool_name": tool_name},
                severity="medium",
                channel_id=channel_id,
                user_id=user_id,
            )

            self._violations.append(violation)
            self._logger.warning(
                "tool_denied",
                tool_name=tool_name,
                channel_id=channel_id,
                user_id=user_id,
            )

            return violation

        # If allowed list is specified, tool must be in it
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.FORBIDDEN_ACTION,
                message=f"Tool '{tool_name}' is not in allowed list",
                details={"tool_name": tool_name},
                severity="medium",
                channel_id=channel_id,
                user_id=user_id,
            )

            self._violations.append(violation)
            self._logger.warning(
                "tool_not_allowed",
                tool_name=tool_name,
                channel_id=channel_id,
                user_id=user_id,
            )

            return violation

        return None

    def sanitize_input(self, text: str) -> str:
        """Sanitize input text by removing potential injection markers.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text
        """
        # Remove common delimiter patterns
        sanitized = text

        # Remove potential role markers
        sanitized = re.sub(r"\[(?:system|assistant|user)\]", "", sanitized)
        sanitized = re.sub(r"<\|im_(?:start|end)\|>", "", sanitized)
        sanitized = re.sub(r"```(?:system|assistant)", "```", sanitized)

        return sanitized.strip()

    def validate_message(
        self,
        text: str,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[bool, SecurityViolation | None]:
        """Validate a message for security issues.

        Args:
            text: Message text
            channel_id: Channel ID
            user_id: User ID

        Returns:
            Tuple of (is_valid, violation)
        """
        # Check for prompt injection
        violation = self.check_prompt_injection(text, channel_id, user_id)
        if violation:
            return False, violation

        return True, None

    def get_violations(
        self,
        limit: int = 100,
        channel_id: str | None = None,
    ) -> list[SecurityViolation]:
        """Get recent security violations.

        Args:
            limit: Maximum number to return
            channel_id: Filter by channel ID

        Returns:
            List of violations
        """
        violations = self._violations

        if channel_id:
            violations = [v for v in violations if v.channel_id == channel_id]

        return violations[-limit:]

    def clear_violations(self) -> int:
        """Clear violation history.

        Returns:
            Number of violations cleared
        """
        count = len(self._violations)
        self._violations.clear()
        return count

    @property
    def rejection_message(self) -> str:
        """Get the standard rejection message for security violations."""
        return "I cannot process this request due to security policy."


# Global security manager instance
_security_manager: SecurityManager | None = None


def get_security_manager() -> SecurityManager:
    """Get the global security manager instance."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


def set_security_manager(manager: SecurityManager) -> None:
    """Set the global security manager instance."""
    global _security_manager
    _security_manager = manager
