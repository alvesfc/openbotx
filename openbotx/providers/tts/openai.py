"""OpenAI TTS provider for OpenBotX."""

import os
from pathlib import Path
from typing import Any

from openbotx.models.enums import ProviderStatus, TTSProviderType
from openbotx.providers.base import ProviderHealth
from openbotx.providers.tts.base import TTSProvider, TTSResult


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS provider."""

    tts_type = TTSProviderType.OPENAI

    AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(
        self,
        name: str = "openai",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize OpenAI TTS provider.

        Args:
            name: Provider name
            config: Provider configuration with 'voice' key
        """
        super().__init__(name, config)
        self.voice = config.get("voice", "alloy") if config else "alloy"
        self.model = config.get("model", "tts-1") if config else "tts-1"
        self._client: Any = None

    async def initialize(self) -> None:
        """Initialize the OpenAI TTS provider."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the OpenAI TTS provider."""
        self._set_status(ProviderStatus.STARTING)

        try:
            from openai import AsyncOpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                self._logger.warning("openai_api_key_not_set")
                self._set_status(ProviderStatus.ERROR)
                return

            self._client = AsyncOpenAI(api_key=api_key)
            self._set_status(ProviderStatus.RUNNING)
            self._logger.info("openai_tts_started", voice=self.voice)

        except ImportError:
            self._logger.warning(
                "openai_not_installed",
                message="Install openai for TTS support",
            )
            self._set_status(ProviderStatus.ERROR)
        except Exception as e:
            self._logger.error("openai_tts_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)

    async def stop(self) -> None:
        """Stop the OpenAI TTS provider."""
        self._client = None
        self._set_status(ProviderStatus.STOPPED)

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
    ) -> TTSResult:
        """Synthesize text to speech."""
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")

        voice = voice or self.voice
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        self._logger.info("synthesizing", text_length=len(text), voice=voice)

        response = await self._client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
        )

        # Save to file
        await response.astream_to_file(output_path)

        size = output.stat().st_size

        self._logger.info(
            "synthesis_complete",
            output_path=output_path,
            size=size,
        )

        return TTSResult(
            audio_path=output_path,
            format="mp3",
            size_bytes=size,
        )

    async def synthesize_bytes(
        self,
        text: str,
        voice: str | None = None,
        format: str = "mp3",
    ) -> bytes:
        """Synthesize text to speech and return bytes."""
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")

        voice = voice or self.voice

        self._logger.info("synthesizing_bytes", text_length=len(text), voice=voice)

        response = await self._client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
            response_format=format,
        )

        return response.content

    def get_available_voices(self) -> list[str]:
        """Get list of available voices."""
        return self.AVAILABLE_VOICES

    async def health_check(self) -> ProviderHealth:
        """Check OpenAI TTS provider health."""
        if self._client is None:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message="OpenAI client not initialized",
                details={
                    "tts_type": self.tts_type.value,
                    "voice": self.voice,
                },
            )

        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="OpenAI TTS provider is available",
            details={
                "tts_type": self.tts_type.value,
                "voice": self.voice,
                "model": self.model,
                "available_voices": self.AVAILABLE_VOICES,
            },
        )
