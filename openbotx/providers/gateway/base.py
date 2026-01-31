"""Base gateway provider for OpenBotX."""

from abc import abstractmethod
from collections.abc import Callable
from typing import Any

from openbotx.models.enums import GatewayType, ProviderType, ResponseCapability
from openbotx.models.message import InboundMessage, OutboundMessage
from openbotx.providers.base import ProviderBase, ProviderHealth

# Type for message handler callback
MessageHandler = Callable[[InboundMessage], None]


class GatewayProvider(ProviderBase):
    """Base class for gateway providers."""

    provider_type = ProviderType.GATEWAY
    gateway_type: GatewayType

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize gateway provider.

        Args:
            name: Provider name
            config: Provider configuration (can include allowed_users)
        """
        super().__init__(name, config)
        self._message_handler: MessageHandler | None = None
        self._response_capabilities: set[ResponseCapability] = {ResponseCapability.TEXT}

        # Generic authorization
        self.allowed_users: list[str] = []
        if config:
            allowed = config.get("allowed_users", [])
            self.allowed_users = [str(u) for u in allowed] if allowed else []

    @property
    def response_capabilities(self) -> set[ResponseCapability]:
        """Get response capabilities supported by this gateway."""
        return self._response_capabilities

    def supports_response_type(self, response_type: ResponseCapability) -> bool:
        """Check if gateway supports a response type.

        Args:
            response_type: Response type to check

        Returns:
            True if supported
        """
        return response_type in self._response_capabilities

    def build_channel_id(self, identifier: str) -> str:
        """Build channel ID with gateway prefix.

        Args:
            identifier: Unique identifier (chat_id, client_id, session, etc.)

        Returns:
            Prefixed channel ID
        """
        gateway_prefix = self.gateway_type.value
        return f"{gateway_prefix}-{identifier}"

    def is_user_allowed(self, user_id: str | int) -> bool:
        """Check if user is allowed to use this gateway.

        Args:
            user_id: User identifier

        Returns:
            True if allowed (empty allowlist = everyone allowed)
        """
        if not self.allowed_users:
            return True
        return str(user_id) in self.allowed_users

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the message handler callback.

        The handler is called whenever a message is received.

        Args:
            handler: Callback function for incoming messages
        """
        self._message_handler = handler

    async def _handle_message(self, message: InboundMessage) -> None:
        """Handle an incoming message.

        Args:
            message: Incoming message
        """
        if self._message_handler:
            self._message_handler(message)
        else:
            self._logger.warning("no_message_handler", message_id=message.id)

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool:
        """Send an outbound message.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check gateway health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Gateway is running",
            details={
                "gateway_type": self.gateway_type.value,
                "capabilities": [c.value for c in self._response_capabilities],
            },
        )
