"""Provider loader and manager for OpenBotX.

Centralized logic for initializing and managing providers (storage, transcription, etc.)
based on configuration.
"""

from openbotx.helpers.config import Config, get_config
from openbotx.helpers.logger import get_logger
from openbotx.models.enums import StorageType, TranscriptionProviderType
from openbotx.providers.base import get_provider_registry

_logger = get_logger("provider_loader")


async def initialize_providers(config: Config | None = None) -> list[str]:
    """Initialize and register all configured providers.

    Args:
        config: Configuration object (optional, will load if not provided)

    Returns:
        List of initialized provider names
    """
    if config is None:
        config = get_config()

    registry = get_provider_registry()
    initialized = []

    # Initialize storage provider
    storage_name = await _initialize_storage_provider(config, registry)
    if storage_name:
        initialized.append(storage_name)

    # Initialize transcription provider
    transcription_name = await _initialize_transcription_provider(config, registry)
    if transcription_name:
        initialized.append(transcription_name)

    _logger.info("providers_initialized", providers=initialized)
    return initialized


async def _initialize_storage_provider(config: Config, registry: any) -> str | None:
    """Initialize storage provider based on config.

    Args:
        config: Configuration object
        registry: Provider registry

    Returns:
        Provider name if initialized, None otherwise
    """
    storage_type = config.storage.type

    try:
        if storage_type == StorageType.LOCAL:
            from openbotx.providers.storage.local import LocalStorageProvider

            provider = LocalStorageProvider(
                name="local",
                config=config.storage.get_storage_config(),
            )
            await provider.initialize()
            await provider.start()
            registry.register(provider)
            _logger.info("storage_provider_initialized", type=storage_type.value)
            return "local"

        elif storage_type == StorageType.S3:
            from openbotx.providers.storage.s3 import S3StorageProvider

            provider = S3StorageProvider(
                name="s3",
                config=config.storage.get_storage_config(),
            )
            await provider.initialize()
            await provider.start()
            registry.register(provider)
            _logger.info("storage_provider_initialized", type=storage_type.value)
            return "s3"

        else:
            _logger.error("unknown_storage_type", type=storage_type.value)
            return None

    except Exception as e:
        _logger.error("storage_provider_init_error", type=storage_type.value, error=str(e))
        return None


async def _initialize_transcription_provider(config: Config, registry: any) -> str | None:
    """Initialize transcription provider based on config.

    Args:
        config: Configuration object
        registry: Provider registry

    Returns:
        Provider name if initialized, None otherwise
    """
    transcription_type = config.transcription.provider

    try:
        if transcription_type == TranscriptionProviderType.WHISPER:
            from openbotx.providers.transcription.whisper import WhisperProvider

            provider = WhisperProvider(
                name="whisper",
                config={"model": config.transcription.model},
            )
            await provider.initialize()
            await provider.start()
            registry.register(provider)
            _logger.info(
                "transcription_provider_initialized",
                provider=transcription_type.value,
                model=config.transcription.model,
            )
            return "whisper"

        else:
            _logger.warning("unknown_transcription_provider", provider=transcription_type.value)
            return None

    except Exception as e:
        _logger.error(
            "transcription_provider_init_error",
            provider=(
                transcription_type.value
                if hasattr(transcription_type, "value")
                else str(transcription_type)
            ),
            error=str(e),
        )
        return None


async def stop_all_providers() -> None:
    """Stop all registered providers gracefully."""
    from openbotx.models.enums import ProviderType

    registry = get_provider_registry()

    # Stop storage providers
    storage_providers = registry.get_all(ProviderType.STORAGE)
    for provider in storage_providers:
        try:
            await provider.stop()
            _logger.info("provider_stopped", name=provider.name)
        except Exception as e:
            _logger.error("provider_stop_error", name=provider.name, error=str(e))

    # Stop transcription providers
    transcription_providers = registry.get_all(ProviderType.TRANSCRIPTION)
    for provider in transcription_providers:
        try:
            await provider.stop()
            _logger.info("provider_stopped", name=provider.name)
        except Exception as e:
            _logger.error("provider_stop_error", name=provider.name, error=str(e))


def get_initialized_providers(config: Config | None = None) -> list[dict[str, str]]:
    """Get list of initialized providers.

    Args:
        config: Configuration object (optional)

    Returns:
        List of provider info dicts
    """
    if config is None:
        config = get_config()

    providers = []

    # Storage
    providers.append(
        {
            "name": config.storage.type.value,
            "type": "storage",
            "display": f"Storage ({config.storage.type.value})",
        }
    )

    # Transcription
    providers.append(
        {
            "name": config.transcription.provider.value,
            "type": "transcription",
            "display": f"Transcription ({config.transcription.provider.value}/{config.transcription.model})",
        }
    )

    return providers
