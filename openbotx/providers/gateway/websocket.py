"""WebSocket gateway provider for OpenBotX."""

import asyncio
import base64
import json
import mimetypes
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
from openbotx.models.message import Attachment, InboundMessage, OutboundMessage
from openbotx.providers.gateway.base import GatewayProvider


class WebSocketGateway(GatewayProvider):
    """WebSocket gateway for real-time communication.

    Supports graceful shutdown through _stop_event.
    """

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
            ResponseCapability.AUDIO,
            ResponseCapability.VIDEO,
        }
        self.host = config.get("host", "0.0.0.0") if config else "0.0.0.0"
        self.port = config.get("port", 8765) if config else 8765
        self._server: Any = None
        self._clients: dict[str, WebSocketServerProtocol] = {}
        self._client_channels: dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize the WebSocket gateway."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._set_status(ProviderStatus.STARTING)
        self._stop_event.clear()
        self._running = True

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
            self._running = False
            self._logger.error("websocket_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server gracefully."""
        self._set_status(ProviderStatus.STOPPING)
        self._running = False
        self._stop_event.set()

        # close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # close all client connections gracefully
        close_tasks = []
        for client_id, websocket in list(self._clients.items()):
            try:
                close_tasks.append(websocket.close(1001, "Server shutting down"))
            except Exception:
                pass

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self._clients.clear()
        self._client_channels.clear()

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("websocket_gateway_stopped")

    async def _run(self) -> None:
        """Main run loop for the gateway.

        Waits for the stop event to be set.
        The server handles connections in separate tasks.
        """
        await self._stop_event.wait()

    async def _handle_connection(
        self,
        websocket: WebSocketServerProtocol,
        path: str = "",
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
            # send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "client_id": client_id,
                        "channel_id": channel_id,
                    }
                )
            )

            # handle messages until connection closed or stop requested
            async for raw_message in websocket:
                if self._stop_event.is_set():
                    break
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

        Message format:
        {
            "type": "text|image|video|audio|file",
            "text": "optional text content",
            "user_id": "optional user id",
            "attachments": [
                {
                    "filename": "image.jpg",
                    "content_type": "image/jpeg",
                    "data": "base64 encoded data"
                }
            ]
        }
        """
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            data = json.loads(raw_message)

            message_type_str = data.get("type", "text")
            text = data.get("text") or data.get("content") or data.get("message")
            user_id = data.get("user_id")
            raw_attachments = data.get("attachments", [])

            # determine message type
            message_type = MessageType.TEXT
            if message_type_str == "image":
                message_type = MessageType.IMAGE
            elif message_type_str == "video":
                message_type = MessageType.VIDEO
            elif message_type_str == "audio":
                message_type = MessageType.AUDIO
            elif message_type_str == "file":
                message_type = MessageType.FILE

            # process attachments
            attachments = []
            for raw_att in raw_attachments:
                attachment = self._process_attachment(raw_att)
                if attachment:
                    attachments.append(attachment)
                    if message_type == MessageType.TEXT and attachments:
                        message_type = self._detect_message_type(attachment)

            if not text and not attachments:
                return

            message = InboundMessage(
                channel_id=channel_id,
                user_id=user_id,
                gateway=self.gateway_type,
                message_type=message_type,
                text=text,
                attachments=attachments,
                metadata={
                    "client_id": client_id,
                    "raw_type": message_type_str,
                },
            )

            self._logger.info(
                "websocket_message_received",
                message_id=message.id,
                client_id=client_id,
                text_length=len(text) if text else 0,
                attachments_count=len(attachments),
            )

            await self._handle_message(message)

        except json.JSONDecodeError:
            # treat as plain text
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

    def _process_attachment(self, raw_att: dict[str, Any]) -> Attachment | None:
        """Process a raw attachment from WebSocket message."""
        filename = raw_att.get("filename")
        content_type = raw_att.get("content_type")
        data_b64 = raw_att.get("data")

        if not filename or not data_b64:
            return None

        try:
            data = base64.b64decode(data_b64)

            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                content_type = content_type or "application/octet-stream"

            return Attachment(
                filename=filename,
                content_type=content_type,
                size=len(data),
                data=data,
                metadata=raw_att.get("metadata", {}),
            )

        except Exception as e:
            self._logger.error(
                "attachment_processing_error",
                filename=filename,
                error=str(e),
            )
            return None

    def _detect_message_type(self, attachment: Attachment) -> MessageType:
        """Detect message type from attachment content type."""
        ct = attachment.content_type.lower()

        if ct.startswith("image/"):
            return MessageType.IMAGE
        elif ct.startswith("video/"):
            return MessageType.VIDEO
        elif ct.startswith("audio/"):
            return MessageType.AUDIO
        else:
            return MessageType.FILE

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to a WebSocket client."""
        # find client by channel_id
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
        """Broadcast a message to all connected clients."""
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
