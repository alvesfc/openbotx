"""Create PydanticAI model string or model instance for OpenBotX."""

from typing import Any

from openbotx.helpers.config import LLMConfig
from openbotx.helpers.logger import get_logger

_logger = get_logger("llm_model")


def create_pydantic_model(config: LLMConfig) -> str | Any:
    """Create a PydanticAI model string or OpenAIChatModel from config.

    When base_url and api_key are set, returns an OpenAIChatModel using
    OpenAIProvider(base_url=..., api_key=...) for OpenAI-compatible endpoints.
    Otherwise returns "provider:model" and PydanticAI uses env API keys.

    Args:
        config: LLM configuration

    Returns:
        Model string (e.g. "anthropic:claude-3-5-sonnet") or OpenAIChatModel
    """
    if config.base_url and config.api_key:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(base_url=config.base_url, api_key=config.api_key)
        model = OpenAIChatModel(config.model, provider=provider)
        _logger.info(
            "openai_compatible_model_created",
            model=config.model,
            base_url=config.base_url,
        )
        return model

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
    config_dict = config.model_dump()
    config_dict.pop("provider", None)
    config_dict.pop("model", None)
    config_dict.pop("base_url", None)
    config_dict.pop("api_key", None)
    return config_dict if config_dict else None
