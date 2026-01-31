"""Telegram gateway provider for OpenBotX."""

import os
from typing import Any

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from openbotx.models.enums import (
    GatewayType,
    MessageType,
    ProviderStatus,
    ResponseCapability,
)
from openbotx.models.message import Attachment, InboundMessage, OutboundMessage
from openbotx.providers.gateway.base import GatewayProvider


class TelegramGateway(GatewayProvider):
    """Telegram bot gateway."""

    gateway_type = GatewayType.TELEGRAM

    def __init__(
        self,
        name: str = "telegram",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize Telegram gateway.

        Args:
            name: Provider name
            config: Provider configuration with token
        """
        super().__init__(name, config)
        self._response_capabilities = {
            ResponseCapability.TEXT,
            ResponseCapability.AUDIO,
            ResponseCapability.IMAGE,
        }

        self.token = config.get("token", "") if config else ""
        self.allowed_users = config.get("allowed_users", []) if config else []

        self._application: Any = None
        self._running = False

    async def initialize(self) -> None:
        """Initialize the Telegram gateway."""
        if not self.token:
            self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        if not self.token:
            self._logger.warning("telegram_token_not_set")
            self._set_status(ProviderStatus.ERROR)
            return

        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.token:
            self._logger.error("telegram_cannot_start_no_token")
            return

        self._set_status(ProviderStatus.STARTING)

        try:
            # Create application
            self._application = Application.builder().token(self.token).build()

            # Add handlers
            self._application.add_handler(CommandHandler("start", self._handle_start))
            self._application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self._handle_text,
                )
            )
            self._application.add_handler(
                MessageHandler(filters.VOICE | filters.AUDIO, self._handle_audio)
            )
            self._application.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))

            # Start polling
            self._running = True
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling()

            self._set_status(ProviderStatus.RUNNING)
            self._logger.info("telegram_gateway_started")

        except Exception as e:
            self._logger.error("telegram_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._set_status(ProviderStatus.STOPPING)
        self._running = False

        if self._application:
            try:
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                self._logger.error("telegram_stop_error", error=str(e))

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("telegram_gateway_stopped")

    async def _handle_start(self, update: Any, context: Any) -> None:
        """Handle /start command."""
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        if not self.is_user_allowed(user_id):
            self._logger.warning(
                "telegram_unauthorized_user",
                user_id=user_id,
            )
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        await update.message.reply_text(
            "👋 Hello! I'm OpenBotX, your AI assistant.\n\nSend me a message and I'll help you!"
        )

    async def _handle_text(self, update: Any, context: Any) -> None:
        """Handle text messages."""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not self.is_user_allowed(user_id):
            self._logger.warning(
                "telegram_unauthorized_message",
                user_id=user_id,
            )
            return

        text = update.message.text

        message = InboundMessage(
            channel_id=f"telegram-{chat_id}",
            user_id=str(user_id),
            gateway=self.gateway_type,
            message_type=MessageType.TEXT,
            text=text,
            metadata={
                "chat_id": chat_id,
                "message_id": update.message.message_id,
                "username": update.effective_user.username,
            },
        )

        self._logger.info(
            "telegram_message_received",
            message_id=message.id,
            user_id=user_id,
            chat_id=chat_id,
        )

        await self._handle_message(message)

    async def _handle_audio(self, update: Any, context: Any) -> None:
        """Handle audio/voice messages."""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not self.is_user_allowed(user_id):
            return

        # Get audio file
        audio = update.message.voice or update.message.audio
        if not audio:
            return

        try:
            file = await context.bot.get_file(audio.file_id)
            file_bytes = await file.download_as_bytearray()

            # Generate generic filename with timestamp
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"audio-{timestamp}.ogg"

            attachment = Attachment(
                filename=filename,
                content_type="audio/ogg",
                size=len(file_bytes),
                data=bytes(file_bytes),
                metadata={
                    "file_id": audio.file_id,
                    "duration": audio.duration,
                },
            )

            message = InboundMessage(
                channel_id=self.build_channel_id(str(chat_id)),
                user_id=str(user_id),
                gateway=self.gateway_type,
                message_type=MessageType.AUDIO,
                attachments=[attachment],
                metadata={
                    "chat_id": chat_id,
                    "message_id": update.message.message_id,
                },
            )

            self._logger.info(
                "telegram_audio_received",
                message_id=message.id,
                user_id=user_id,
                duration=audio.duration,
            )

            await self._handle_message(message)

        except Exception as e:
            self._logger.error("telegram_audio_error", error=str(e))

    async def _handle_photo(self, update: Any, context: Any) -> None:
        """Handle photo messages."""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        if not self.is_user_allowed(user_id):
            return

        # Get largest photo
        photos = update.message.photo
        if not photos:
            return

        photo = photos[-1]  # Largest size

        try:
            file = await context.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()

            # Generate generic filename with timestamp
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"photo-{timestamp}.jpg"

            attachment = Attachment(
                filename=filename,
                content_type="image/jpeg",
                size=len(file_bytes),
                data=bytes(file_bytes),
                metadata={
                    "file_id": photo.file_id,
                    "width": photo.width,
                    "height": photo.height,
                },
            )

            # Get caption if any
            text = update.message.caption

            message = InboundMessage(
                channel_id=self.build_channel_id(str(chat_id)),
                user_id=str(user_id),
                gateway=self.gateway_type,
                message_type=MessageType.IMAGE,
                text=text,
                attachments=[attachment],
                metadata={
                    "chat_id": chat_id,
                    "message_id": update.message.message_id,
                },
            )

            self._logger.info(
                "telegram_photo_received",
                message_id=message.id,
                user_id=user_id,
            )

            await self._handle_message(message)

        except Exception as e:
            self._logger.error("telegram_photo_error", error=str(e))

    async def _get_file_for_telegram(self, attachment: Attachment) -> bytes | str:
        """Get file for telegram (from storage or URL).

        Args:
            attachment: Attachment with storage_path or url

        Returns:
            File bytes (for local files) or URL string (for remote files)
        """
        from openbotx.models.enums import ProviderType
        from openbotx.providers.base import get_provider_registry

        # If URL, Telegram can fetch directly
        if attachment.url:
            return attachment.url

        # If storage_path, get from storage provider
        if attachment.storage_path:
            registry = get_provider_registry()
            storage = registry.get(ProviderType.STORAGE)

            if storage:
                # Get file from storage
                file_data = await storage.get(attachment.storage_path)
                if file_data:
                    return file_data

        raise FileNotFoundError(f"File not found: {attachment.storage_path or attachment.url}")

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via Telegram.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        if not self._application:
            return False

        # Extract chat_id from channel_id (format: telegram-{chat_id})
        if not message.channel_id.startswith("telegram-"):
            return False

        try:
            chat_id = int(message.channel_id.replace("telegram-", ""))
        except ValueError:
            self._logger.error(
                "telegram_invalid_channel",
                channel_id=message.channel_id,
            )
            return False

        try:
            bot = self._application.bot
            reply_to = message.metadata.get("message_id")

            # Send text if present
            if message.text:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message.text,
                    reply_to_message_id=reply_to,
                )

            # Send attachments if present
            if message.attachments:
                for attachment in message.attachments:
                    if not attachment.storage_path and not attachment.url:
                        continue

                    # Get file (bytes or URL)
                    file_data = await self._get_file_for_telegram(attachment)

                    # Determine type from content_type
                    if attachment.is_image:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=file_data,
                            reply_to_message_id=reply_to,
                        )
                    elif attachment.is_audio:
                        await bot.send_audio(
                            chat_id=chat_id,
                            audio=file_data,
                            reply_to_message_id=reply_to,
                        )
                    elif attachment.is_video:
                        await bot.send_video(
                            chat_id=chat_id,
                            video=file_data,
                            reply_to_message_id=reply_to,
                        )
                    else:
                        # Send as document
                        await bot.send_document(
                            chat_id=chat_id,
                            document=file_data,
                            reply_to_message_id=reply_to,
                        )

            self._logger.info(
                "telegram_message_sent",
                message_id=message.id,
                chat_id=chat_id,
            )

            return True

        except Exception as e:
            self._logger.error(
                "telegram_send_error",
                chat_id=chat_id,
                error=str(e),
            )
            return False
