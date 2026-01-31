"""Attachment processing for OpenBotX."""

from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import MessageType, ProviderType
from openbotx.models.message import Attachment, InboundMessage
from openbotx.providers.base import get_provider_registry
from openbotx.providers.storage.base import StorageProvider
from openbotx.providers.transcription.base import TranscriptionProvider


class AttachmentProcessor:
    """Process attachments from messages."""

    def __init__(
        self,
        storage_provider: StorageProvider | None = None,
        transcription_provider: TranscriptionProvider | None = None,
    ) -> None:
        """Initialize attachment processor.

        Args:
            storage_provider: Storage provider for saving attachments
            transcription_provider: Transcription provider for audio
        """
        self._storage = storage_provider
        self._transcription = transcription_provider
        self._logger = get_logger("attachments")

    def _get_storage_provider(self) -> StorageProvider | None:
        """Get storage provider from registry if not set."""
        if self._storage:
            return self._storage

        registry = get_provider_registry()
        provider = registry.get(ProviderType.STORAGE)
        if isinstance(provider, StorageProvider):
            return provider
        return None

    def _get_transcription_provider(self) -> TranscriptionProvider | None:
        """Get transcription provider from registry if not set."""
        if self._transcription:
            return self._transcription

        registry = get_provider_registry()
        provider = registry.get(ProviderType.TRANSCRIPTION)
        if isinstance(provider, TranscriptionProvider):
            return provider
        return None

    async def process_attachment(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> Attachment:
        """Process and store an attachment.

        Args:
            data: Attachment data
            filename: Original filename
            content_type: MIME type
            metadata: Optional metadata

        Returns:
            Attachment with storage path
        """
        storage = self._get_storage_provider()
        if not storage:
            raise RuntimeError("No storage provider available")

        self._logger.info(
            "processing_attachment",
            filename=filename,
            content_type=content_type,
            size=len(data),
        )

        # Save to storage
        stored = await storage.save_bytes(
            data=data,
            filename=filename,
            content_type=content_type,
            metadata=metadata,
        )

        return Attachment(
            id=stored.id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            storage_path=stored.path,
            url=stored.url,
            metadata=metadata or {},
        )

    async def transcribe_audio(
        self,
        attachment: Attachment,
        language: str | None = None,
    ) -> str:
        """Transcribe an audio attachment to text.

        Args:
            attachment: Audio attachment
            language: Optional language code

        Returns:
            Transcribed text
        """
        if not attachment.is_audio:
            raise ValueError("Attachment is not an audio file")

        storage = self._get_storage_provider()
        transcription = self._get_transcription_provider()

        if not storage:
            raise RuntimeError("No storage provider available")

        if not transcription:
            raise RuntimeError("No transcription provider available")

        self._logger.info(
            "transcribing_audio",
            attachment_id=attachment.id,
            filename=attachment.filename,
        )

        # Get audio data from storage
        audio_data = await storage.get(attachment.storage_path)

        # Determine format from content type
        format_map = {
            "audio/wav": "wav",
            "audio/wave": "wav",
            "audio/x-wav": "wav",
            "audio/mp3": "mp3",
            "audio/mpeg": "mp3",
            "audio/ogg": "ogg",
            "audio/webm": "webm",
            "audio/m4a": "m4a",
            "audio/mp4": "m4a",
        }
        audio_format = format_map.get(attachment.content_type, "wav")

        # Transcribe
        result = await transcription.transcribe_bytes(
            audio_data=audio_data,
            format=audio_format,
            language=language,
        )

        self._logger.info(
            "transcription_complete",
            attachment_id=attachment.id,
            text_length=len(result.text),
            duration=result.duration_seconds,
        )

        return result.text

    async def process_message_attachments(
        self,
        message: InboundMessage,
    ) -> InboundMessage:
        """Process all attachments in a message.

        Saves attachments to storage and transcribes audio attachments.

        Args:
            message: Inbound message with attachments

        Returns:
            Updated message
        """
        if not message.has_attachments:
            return message

        storage = self._get_storage_provider()
        if not storage:
            self._logger.warning("no_storage_provider", message="Cannot save attachments")
            return message

        transcriptions = []

        for attachment in message.attachments:
            # Save attachment to storage first (if not already saved)
            if not attachment.storage_path and attachment.data:
                try:
                    stored_file = await storage.save_attachment(attachment)
                    attachment.storage_path = stored_file.path
                    attachment.url = stored_file.url

                    # Clear data after saving to free memory
                    attachment.data = None

                    self._logger.info(
                        "attachment_saved",
                        attachment_id=attachment.id,
                        path=stored_file.path,
                    )

                except Exception as e:
                    self._logger.error(
                        "attachment_save_error",
                        attachment_id=attachment.id,
                        error=str(e),
                    )
                    continue

            # Transcribe audio attachments
            if attachment.is_audio:
                try:
                    text = await self.transcribe_audio(attachment)
                    transcriptions.append(text)

                    # Update attachment metadata
                    attachment.metadata["transcription"] = text

                except Exception as e:
                    self._logger.error(
                        "transcription_error",
                        attachment_id=attachment.id,
                        error=str(e),
                    )

        # If we have transcriptions, append to message text
        if transcriptions:
            original_text = message.text or ""
            transcription_text = "\n".join(transcriptions)

            if original_text:
                message.text = f"{original_text}\n\n[Audio transcription]:\n{transcription_text}"
            else:
                message.text = transcription_text

            # Update message type if it was audio-only
            if message.message_type == MessageType.AUDIO and message.text:
                message.message_type = MessageType.TEXT

        return message

    async def get_attachment_content(
        self,
        attachment: Attachment,
    ) -> bytes:
        """Get attachment content from storage.

        Args:
            attachment: Attachment to get

        Returns:
            Attachment data as bytes
        """
        storage = self._get_storage_provider()
        if not storage:
            raise RuntimeError("No storage provider available")

        return await storage.get(attachment.storage_path)

    async def delete_attachment(
        self,
        attachment: Attachment,
    ) -> bool:
        """Delete an attachment from storage.

        Args:
            attachment: Attachment to delete

        Returns:
            True if deleted successfully
        """
        storage = self._get_storage_provider()
        if not storage:
            raise RuntimeError("No storage provider available")

        return await storage.delete(attachment.storage_path)


# Global attachment processor instance
_attachment_processor: AttachmentProcessor | None = None


def get_attachment_processor() -> AttachmentProcessor:
    """Get the global attachment processor instance."""
    global _attachment_processor
    if _attachment_processor is None:
        _attachment_processor = AttachmentProcessor()
    return _attachment_processor


def set_attachment_processor(processor: AttachmentProcessor) -> None:
    """Set the global attachment processor instance."""
    global _attachment_processor
    _attachment_processor = processor
