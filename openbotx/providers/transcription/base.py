"""Base transcription provider for OpenBotX."""

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from openbotx.models.enums import ProviderType, TranscriptionProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth


class TranscriptionResult(BaseModel):
    """Result of audio transcription."""

    text: str
    language: str | None = None
    duration_seconds: float = 0.0
    confidence: float = 1.0
    segments: list[dict[str, Any]] = Field(default_factory=list)


class TranscriptionProvider(ProviderBase):
    """Base class for transcription providers."""

    provider_type = ProviderType.TRANSCRIPTION
    transcription_type: TranscriptionProviderType

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize transcription provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self.model = config.get("model", "base") if config else "base"

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            language: Optional language code

        Returns:
            TranscriptionResult with text and metadata
        """
        pass

    @abstractmethod
    async def transcribe_bytes(
        self,
        audio_data: bytes,
        format: str = "wav",
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Audio data as bytes
            format: Audio format (wav, mp3, etc.)
            language: Optional language code

        Returns:
            TranscriptionResult with text and metadata
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check transcription provider health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Transcription provider is available",
            details={
                "transcription_type": self.transcription_type.value,
                "model": self.model,
            },
        )
