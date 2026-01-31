"""Base TTS provider for OpenBotX."""

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel

from openbotx.models.enums import ProviderType, TTSProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth


class TTSResult(BaseModel):
    """Result of text-to-speech synthesis."""

    audio_path: str
    format: str = "mp3"
    duration_seconds: float = 0.0
    size_bytes: int = 0


class TTSProvider(ProviderBase):
    """Base class for TTS providers."""

    provider_type = ProviderType.TTS
    tts_type: TTSProviderType

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize TTS provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self.voice = config.get("voice", "alloy") if config else "alloy"

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
    ) -> TTSResult:
        """Synthesize text to speech.

        Args:
            text: Text to synthesize
            output_path: Path for output audio file
            voice: Optional voice override

        Returns:
            TTSResult with audio path and metadata
        """
        pass

    @abstractmethod
    async def synthesize_bytes(
        self,
        text: str,
        voice: str | None = None,
        format: str = "mp3",
    ) -> bytes:
        """Synthesize text to speech and return bytes.

        Args:
            text: Text to synthesize
            voice: Optional voice override
            format: Audio format

        Returns:
            Audio data as bytes
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> list[str]:
        """Get list of available voices.

        Returns:
            List of voice names
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check TTS provider health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="TTS provider is available",
            details={
                "tts_type": self.tts_type.value,
                "voice": self.voice,
                "available_voices": self.get_available_voices(),
            },
        )
