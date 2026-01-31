"""Create PydanticAI model string and settings for OpenBotX."""

from typing import Any

from openbotx.helpers.config import LLMConfig
from openbotx.helpers.logger import get_logger

_logger = get_logger("llm_model")


def create_pydantic_model(config: LLMConfig) -> str:
    """Create a PydanticAI model string from config.

    PydanticAI uses the format "provider:model" and automatically handles
    API keys from environment variables (e.g., ANTHROPIC_API_KEY, OPENAI_API_KEY).

    Args:
        config: LLM configuration with provider and model

    Returns:
        Model string in PydanticAI format (e.g., "anthropic:claude-3-5-sonnet")

    Example:
        >>> config = LLMConfig(provider="anthropic", model="claude-3-5-sonnet")
        >>> create_pydantic_model(config)
        "anthropic:claude-3-5-sonnet"
    """
    model_string = f"{config.provider}:{config.model}"

    _logger.info(
        "pydantic_model_string_created",
        model_string=model_string,
    )

    return model_string


def create_model_settings(config: LLMConfig) -> dict[str, Any] | None:
    """Create ModelSettings dict from config.

    Extracts all fields except 'provider' and 'model' and passes them
    to PydanticAI's ModelSettings (e.g., max_tokens, temperature, top_p, etc).

    Args:
        config: LLM configuration

    Returns:
        Dictionary with model settings, or None if no extra settings

    Example:
        >>> config = LLMConfig(
        ...     provider="anthropic",
        ...     model="claude-3-5-sonnet",
        ...     max_tokens=4096,
        ...     temperature=0.7
        ... )
        >>> create_model_settings(config)
        {"max_tokens": 4096, "temperature": 0.7}
    """
    # Get all fields from config
    config_dict = config.model_dump()

    # Remove provider and model (not part of ModelSettings)
    config_dict.pop("provider", None)
    config_dict.pop("model", None)

    # Return settings if any exist
    return config_dict if config_dict else None
