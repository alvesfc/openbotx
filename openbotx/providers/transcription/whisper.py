"""Whisper transcription provider for OpenBotX."""

import tempfile
from pathlib import Path
from typing import Any

from openbotx.models.enums import ProviderStatus, TranscriptionProviderType
from openbotx.providers.base import ProviderHealth
from openbotx.providers.transcription.base import (
    TranscriptionProvider,
    TranscriptionResult,
)


class WhisperProvider(TranscriptionProvider):
    """Whisper transcription provider using faster-whisper."""

    transcription_type = TranscriptionProviderType.WHISPER

    def __init__(
        self,
        name: str = "whisper",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize Whisper provider.

        Args:
            name: Provider name
            config: Provider configuration with 'model' key
        """
        super().__init__(name, config)
        self.model_size = config.get("model", "base") if config else "base"
        self._model: Any = None

    async def initialize(self) -> None:
        """Initialize the Whisper provider."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the Whisper provider and load model."""
        self._set_status(ProviderStatus.STARTING)

        try:
            from faster_whisper import WhisperModel

            # Load the model
            self._model = WhisperModel(
                self.model_size,
                device="cpu",  # Use 'cuda' for GPU
                compute_type="int8",
            )

            self._set_status(ProviderStatus.RUNNING)
            self._logger.info("whisper_started", model=self.model_size)

        except ImportError:
            self._logger.warning(
                "faster_whisper_not_installed",
                message="Install faster-whisper for transcription support",
            )
            self._set_status(ProviderStatus.ERROR)
        except Exception as e:
            self._logger.error("whisper_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)

    async def stop(self) -> None:
        """Stop the Whisper provider."""
        self._model = None
        self._set_status(ProviderStatus.STOPPED)

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio file to text."""
        if not self._model:
            raise RuntimeError("Whisper model not loaded")

        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._logger.info("transcribing", path=audio_path, language=language)

        # Transcribe
        segments, info = self._model.transcribe(
            str(path),
            language=language,
            beam_size=5,
        )

        # Collect segments
        segment_list = []
        text_parts = []

        for segment in segments:
            segment_list.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
            )
            text_parts.append(segment.text)

        full_text = " ".join(text_parts).strip()

        self._logger.info(
            "transcription_complete",
            path=audio_path,
            duration=info.duration,
            language=info.language,
            text_length=len(full_text),
        )

        return TranscriptionResult(
            text=full_text,
            language=info.language,
            duration_seconds=info.duration,
            confidence=info.language_probability,
            segments=segment_list,
        )

    async def transcribe_bytes(
        self,
        audio_data: bytes,
        format: str = "wav",
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text."""
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            return await self.transcribe(temp_path, language)
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

    async def health_check(self) -> ProviderHealth:
        """Check Whisper provider health."""
        if self._model is None:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message="Whisper model not loaded",
                details={
                    "transcription_type": self.transcription_type.value,
                    "model": self.model_size,
                },
            )

        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Whisper provider is available",
            details={
                "transcription_type": self.transcription_type.value,
                "model": self.model_size,
            },
        )
