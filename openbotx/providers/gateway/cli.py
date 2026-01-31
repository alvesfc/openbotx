"""CLI gateway provider for OpenBotX."""

import asyncio
from typing import Any

from openbotx.models.enums import (
    GatewayType,
    MessageType,
    ProviderStatus,
    ResponseCapability,
)
from openbotx.models.message import InboundMessage, OutboundMessage
from openbotx.providers.gateway.base import GatewayProvider


class CLIGateway(GatewayProvider):
    """CLI gateway for interactive terminal mode."""

    gateway_type = GatewayType.CLI

    def __init__(
        self,
        name: str = "cli",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize CLI gateway.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._response_capabilities = {ResponseCapability.TEXT}
        self._running = False
        self._input_task: asyncio.Task[None] | None = None
        self._channel_id = self.build_channel_id("session")
        self._pending_responses: dict[str, asyncio.Future[OutboundMessage]] = {}

    async def initialize(self) -> None:
        """Initialize the CLI gateway."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the CLI gateway."""
        self._set_status(ProviderStatus.STARTING)
        self._running = True
        self._set_status(ProviderStatus.RUNNING)
        self._logger.info("cli_gateway_started")

    async def stop(self) -> None:
        """Stop the CLI gateway."""
        self._set_status(ProviderStatus.STOPPING)
        self._running = False

        if self._input_task:
            self._input_task.cancel()
            try:
                await self._input_task
            except asyncio.CancelledError:
                pass

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("cli_gateway_stopped")

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the CLI.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            print(f"\n🤖 Assistant: {message.text}\n")

            # If there's a pending response, resolve it
            if message.reply_to and message.reply_to in self._pending_responses:
                future = self._pending_responses.pop(message.reply_to)
                if not future.done():
                    future.set_result(message)

            return True
        except Exception as e:
            self._logger.error("cli_send_error", error=str(e))
            return False

    async def run_interactive(self) -> None:
        """Run interactive CLI loop."""
        print("\n" + "=" * 50)
        print("🤖 OpenBotX CLI Interface")
        print("=" * 50)
        print("Type your message and press Enter.")
        print("Type 'quit' or 'exit' to stop.")
        print("=" * 50 + "\n")

        while self._running:
            try:
                # Read input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: input("👤 You: "),
                )

                if not user_input:
                    continue

                # Check for exit commands
                if user_input.lower() in ("quit", "exit", "bye"):
                    print("\n👋 Goodbye!\n")
                    break

                # Create message
                message = InboundMessage(
                    channel_id=self._channel_id,
                    user_id="cli-user",
                    gateway=self.gateway_type,
                    message_type=MessageType.TEXT,
                    text=user_input,
                )

                # Handle message
                await self._handle_message(message)

            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n\n👋 Interrupted. Goodbye!\n")
                break
            except Exception as e:
                self._logger.error("cli_input_error", error=str(e))
                print(f"\n❌ Error: {e}\n")

    async def send_and_wait(
        self,
        text: str,
        timeout: float = 60.0,
    ) -> OutboundMessage | None:
        """Send a message and wait for response.

        Useful for programmatic CLI interaction.

        Args:
            text: Message text
            timeout: Response timeout in seconds

        Returns:
            Response message or None
        """
        message = InboundMessage(
            channel_id=self._channel_id,
            user_id="cli-user",
            gateway=self.gateway_type,
            message_type=MessageType.TEXT,
            text=text,
        )

        # Create future for response
        future: asyncio.Future[OutboundMessage] = asyncio.Future()
        self._pending_responses[message.id] = future

        # Handle message
        await self._handle_message(message)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending_responses.pop(message.id, None)
            return None
