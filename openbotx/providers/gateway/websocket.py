"""WebSocket gateway provider for OpenBotX."""

import json
from typing import Any
from uuid import uuid4

import websockets
from websockets.server import WebSocketServerProtocol

from openbotx.models.enums import (
    GatewayType,
    MessageType,
    ProviderStatus,
    ResponseCapability,
)
from openbotx.models.message import InboundMessage, OutboundMessage
from openbotx.providers.gateway.base import GatewayProvider


class WebSocketGateway(GatewayProvider):
    """WebSocket gateway for real-time communication."""

    gateway_type = GatewayType.WEBSOCKET

    def __init__(
        self,
        name: str = "websocket",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize WebSocket gateway.

        Args:
            name: Provider name
            config: Provider configuration with host and port
        """
        super().__init__(name, config)
        self._response_capabilities = {
            ResponseCapability.TEXT,
            ResponseCapability.IMAGE,
        }
        self.host = config.get("host", "0.0.0.0") if config else "0.0.0.0"
        self.port = config.get("port", 8765) if config else 8765
        self._server: Any = None
        self._clients: dict[str, WebSocketServerProtocol] = {}
        self._client_channels: dict[str, str] = {}  # client_id -> channel_id

    async def initialize(self) -> None:
        """Initialize the WebSocket gateway."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._set_status(ProviderStatus.STARTING)

        try:
            self._server = await websockets.serve(
                self._handle_connection,
                self.host,
                self.port,
            )

            self._set_status(ProviderStatus.RUNNING)
            self._logger.info(
                "websocket_gateway_started",
                host=self.host,
                port=self.port,
            )

        except Exception as e:
            self._logger.error("websocket_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._set_status(ProviderStatus.STOPPING)

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all client connections
        for client in self._clients.values():
            await client.close()

        self._clients.clear()
        self._client_channels.clear()

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("websocket_gateway_stopped")

    async def _handle_connection(
        self,
        websocket: WebSocketServerProtocol,
        path: str,
    ) -> None:
        """Handle a WebSocket connection.

        Args:
            websocket: WebSocket connection
            path: Connection path
        """
        client_id = str(uuid4())
        channel_id = self.build_channel_id(client_id)

        self._clients[client_id] = websocket
        self._client_channels[client_id] = channel_id

        self._logger.info(
            "websocket_client_connected",
            client_id=client_id,
            channel_id=channel_id,
        )

        try:
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "client_id": client_id,
                        "channel_id": channel_id,
                    }
                )
            )

            # Handle messages
            async for raw_message in websocket:
                await self._process_raw_message(
                    raw_message,
                    client_id,
                    channel_id,
                )

        except websockets.exceptions.ConnectionClosed:
            self._logger.info(
                "websocket_client_disconnected",
                client_id=client_id,
            )
        except Exception as e:
            self._logger.error(
                "websocket_connection_error",
                client_id=client_id,
                error=str(e),
            )
        finally:
            self._clients.pop(client_id, None)
            self._client_channels.pop(client_id, None)

    async def _process_raw_message(
        self,
        raw_message: str | bytes,
        client_id: str,
        channel_id: str,
    ) -> None:
        """Process a raw WebSocket message.

        Args:
            raw_message: Raw message data
            client_id: Client ID
            channel_id: Channel ID
        """
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            data = json.loads(raw_message)

            message_type = data.get("type", "text")
            text = data.get("text") or data.get("content") or data.get("message")
            user_id = data.get("user_id")

            if not text:
                return

            message = InboundMessage(
                channel_id=channel_id,
                user_id=user_id,
                gateway=self.gateway_type,
                message_type=MessageType.TEXT,
                text=text,
                metadata={
                    "client_id": client_id,
                    "raw_type": message_type,
                },
            )

            self._logger.info(
                "websocket_message_received",
                message_id=message.id,
                client_id=client_id,
                text_length=len(text),
            )

            await self._handle_message(message)

        except json.JSONDecodeError:
            # Treat as plain text
            message = InboundMessage(
                channel_id=channel_id,
                gateway=self.gateway_type,
                message_type=MessageType.TEXT,
                text=str(raw_message),
                metadata={"client_id": client_id},
            )
            await self._handle_message(message)

        except Exception as e:
            self._logger.error(
                "websocket_message_error",
                client_id=client_id,
                error=str(e),
            )

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a WebSocket client.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        # Find client by channel_id
        target_client_id = None
        for client_id, channel_id in self._client_channels.items():
            if channel_id == message.channel_id:
                target_client_id = client_id
                break

        if not target_client_id:
            self._logger.warning(
                "websocket_no_client",
                channel_id=message.channel_id,
            )
            return False

        websocket = self._clients.get(target_client_id)
        if not websocket:
            return False

        try:
            response_data = {
                "type": "message",
                "id": message.id,
                "text": message.text,
                "timestamp": message.timestamp.isoformat(),
            }

            if message.reply_to:
                response_data["reply_to"] = message.reply_to

            if message.attachments:
                response_data["attachments"] = [
                    {
                        "id": a.id,
                        "filename": a.filename,
                        "content_type": a.content_type,
                        "url": a.url,
                    }
                    for a in message.attachments
                ]

            await websocket.send(json.dumps(response_data))

            self._logger.info(
                "websocket_message_sent",
                message_id=message.id,
                client_id=target_client_id,
            )

            return True

        except Exception as e:
            self._logger.error(
                "websocket_send_error",
                client_id=target_client_id,
                error=str(e),
            )
            return False

    async def broadcast(self, message: OutboundMessage) -> int:
        """Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast

        Returns:
            Number of clients that received the message
        """
        success_count = 0

        response_data = {
            "type": "broadcast",
            "id": message.id,
            "text": message.text,
            "timestamp": message.timestamp.isoformat(),
        }

        for client_id, websocket in self._clients.items():
            try:
                await websocket.send(json.dumps(response_data))
                success_count += 1
            except Exception as e:
                self._logger.error(
                    "websocket_broadcast_error",
                    client_id=client_id,
                    error=str(e),
                )

        return success_count

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)
