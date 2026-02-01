"""CLI gateway provider for OpenBotX."""

import asyncio
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from openbotx.models.enums import (
    GatewayType,
    MessageType,
    ProviderStatus,
    ResponseCapability,
)
from openbotx.models.message import Attachment, InboundMessage, OutboundMessage
from openbotx.providers.gateway.base import GatewayProvider


class CLIGateway(GatewayProvider):
    """CLI gateway for interactive terminal mode.

    Runs a non-blocking input loop that checks _stop_event for graceful shutdown.
    """

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
        self._channel_id = self.build_channel_id("session")
        self._pending_responses: dict[str, asyncio.Future[OutboundMessage]] = {}
        self._input_poll_interval = 0.1

    async def initialize(self) -> None:
        """Initialize the CLI gateway."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the CLI gateway."""
        self._set_status(ProviderStatus.STARTING)
        self._running = True
        self._stop_event.clear()
        self._set_status(ProviderStatus.RUNNING)
        self._logger.info("cli_gateway_started")

    async def stop(self) -> None:
        """Stop the CLI gateway."""
        self._set_status(ProviderStatus.STOPPING)
        self._running = False
        self._stop_event.set()
        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("cli_gateway_stopped")

    async def _run(self) -> None:
        """Run the interactive CLI loop.

        This is called by GatewayManager and runs in its own task.
        """
        self._print_banner()

        while not self._stop_event.is_set():
            try:
                # non-blocking input with timeout
                user_input = await self._read_input_async()

                if user_input is None:
                    # timeout, check stop event and continue
                    continue

                if not user_input:
                    continue

                # check for exit commands
                if user_input.lower() in ("quit", "exit", "bye"):
                    print("\nGoodbye!\n")
                    self.request_stop()
                    break

                # check for file command
                if user_input.startswith("/file "):
                    message = await self._process_file_command(user_input[6:].strip())
                    if message:
                        await self._handle_message(message)
                    continue

                # create text message
                message = InboundMessage(
                    channel_id=self._channel_id,
                    user_id="cli-user",
                    gateway=self.gateway_type,
                    message_type=MessageType.TEXT,
                    text=user_input,
                )

                await self._handle_message(message)

            except EOFError:
                break
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!\n")
                break
            except Exception as e:
                self._logger.error("cli_input_error", error=str(e))
                print(f"\nError: {e}\n")

    async def _read_input_async(self) -> str | None:
        """Read input asynchronously with timeout.

        Returns:
            User input string or None if timeout
        """
        loop = asyncio.get_event_loop()

        try:
            # check if stdin has data (for piped input)
            if not sys.stdin.isatty():
                line = sys.stdin.readline()
                if not line:
                    return None
                return line.strip()

            # for interactive input, use executor with timeout
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: input("You: ")),
                    timeout=self._input_poll_interval,
                )
                return result
            except TimeoutError:
                return None

        except Exception:
            return None

    def _print_banner(self) -> None:
        """Print the CLI banner."""
        print("\n" + "=" * 50)
        print("OpenBotX CLI Interface")
        print("=" * 50)
        print("Type your message and press Enter.")
        print("Commands:")
        print("  /file <path> [message] - Send a file with optional message")
        print("  quit, exit - Stop the CLI")
        print("=" * 50 + "\n")

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message to the CLI.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            print(f"\n🤖 Assistant: {message.text}\n")

            # resolve pending response if any
            if message.reply_to and message.reply_to in self._pending_responses:
                future = self._pending_responses.pop(message.reply_to)
                if not future.done():
                    future.set_result(message)

            return True
        except Exception as e:
            self._logger.error("cli_send_error", error=str(e))
            return False

    async def run_interactive(self) -> None:
        """Run interactive CLI loop.

        For backward compatibility. Prefer using GatewayManager.
        """
        await self.start()
        try:
            await self._run()
        finally:
            await self.stop()

    async def _process_file_command(self, args: str) -> InboundMessage | None:
        """Process a /file command.

        Format: /file <path> [optional message]

        Args:
            args: Arguments after /file

        Returns:
            InboundMessage with attachment or None if error
        """
        if not args:
            print("Error: Please specify a file path")
            return None

        # parse arguments - path may be quoted
        parts = args.split(maxsplit=1)
        file_path_str = parts[0].strip('"').strip("'")
        text = parts[1] if len(parts) > 1 else None

        # expand user path and resolve
        file_path = Path(os.path.expanduser(file_path_str)).resolve()

        if not file_path.exists():
            print(f"Error: File not found: {file_path}")
            return None

        if not file_path.is_file():
            print(f"Error: Not a file: {file_path}")
            return None

        try:
            data = file_path.read_bytes()
            filename = file_path.name

            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"

            message_type = self._detect_message_type_from_content_type(content_type)

            attachment = Attachment(
                filename=filename,
                content_type=content_type,
                size=len(data),
                data=data,
                metadata={"source_path": str(file_path)},
            )

            print(f"Sending file: {filename} ({content_type}, {len(data)} bytes)")

            return InboundMessage(
                channel_id=self._channel_id,
                user_id="cli-user",
                gateway=self.gateway_type,
                message_type=message_type,
                text=text,
                attachments=[attachment],
            )

        except Exception as e:
            print(f"Error reading file: {e}")
            return None

    def _detect_message_type_from_content_type(self, content_type: str) -> MessageType:
        """Detect message type from content type.

        Args:
            content_type: MIME content type

        Returns:
            Appropriate MessageType
        """
        ct = content_type.lower()

        if ct.startswith("image/"):
            return MessageType.IMAGE
        elif ct.startswith("video/"):
            return MessageType.VIDEO
        elif ct.startswith("audio/"):
            return MessageType.AUDIO
        else:
            return MessageType.FILE

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

        future: asyncio.Future[OutboundMessage] = asyncio.Future()
        self._pending_responses[message.id] = future

        await self._handle_message(message)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending_responses.pop(message.id, None)
            return None
