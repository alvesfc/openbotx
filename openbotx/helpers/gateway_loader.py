"""Gateway loader helper for OpenBotX."""

from collections.abc import Callable

from openbotx.helpers.config import Config, get_config
from openbotx.helpers.logger import get_logger
from openbotx.providers.base import get_provider_registry

_logger = get_logger("gateway_loader")


def get_enabled_gateways(config: Config | None = None) -> list[dict[str, str]]:
    """Get list of enabled gateways from config.

    Args:
        config: Configuration (loads from default if not provided)

    Returns:
        List of dicts with 'name' and 'display' keys for each enabled gateway
    """
    if config is None:
        config = get_config()

    enabled = []

    if config.gateways.cli.enabled:
        enabled.append({"name": "cli", "display": "CLI"})

    if config.gateways.websocket.enabled:
        enabled.append(
            {
                "name": "websocket",
                "display": f"WebSocket ({config.gateways.websocket.host}:{config.gateways.websocket.port})",
            }
        )

    if config.gateways.telegram.enabled:
        enabled.append({"name": "telegram", "display": "Telegram"})

    return enabled


async def initialize_gateways(
    config: Config | None = None,
    message_handler: Callable | None = None,
) -> list[str]:
    """Initialize all enabled gateways from config.

    Args:
        config: Configuration (loads from default if not provided)
        message_handler: Handler for incoming messages

    Returns:
        List of initialized gateway names
    """
    if config is None:
        config = get_config()

    registry = get_provider_registry()
    initialized = []

    # CLI Gateway
    if config.gateways.cli.enabled:
        try:
            from openbotx.providers.gateway.cli import CLIGateway

            gateway = CLIGateway(
                name="cli",
                config={"enabled": config.gateways.cli.enabled},
            )
            await gateway.initialize()
            await gateway.start()

            if message_handler:
                gateway.set_message_handler(message_handler)

            registry.register(gateway)
            initialized.append("cli")
            _logger.info("gateway_initialized", gateway="cli")
        except Exception as e:
            _logger.error("gateway_init_error", gateway="cli", error=str(e))

    # WebSocket Gateway
    if config.gateways.websocket.enabled:
        try:
            from openbotx.providers.gateway.websocket import WebSocketGateway

            gateway = WebSocketGateway(
                name="websocket",
                config={
                    "host": config.gateways.websocket.host,
                    "port": config.gateways.websocket.port,
                },
            )
            await gateway.initialize()
            await gateway.start()

            if message_handler:
                gateway.set_message_handler(message_handler)

            registry.register(gateway)
            initialized.append("websocket")
            _logger.info(
                "gateway_initialized",
                gateway="websocket",
                host=config.gateways.websocket.host,
                port=config.gateways.websocket.port,
            )
        except Exception as e:
            _logger.error("gateway_init_error", gateway="websocket", error=str(e))

    # Telegram Gateway
    if config.gateways.telegram.enabled:
        try:
            from openbotx.providers.gateway.telegram import TelegramGateway

            gateway = TelegramGateway(
                name="telegram",
                config={
                    "token": config.gateways.telegram.token,
                    "allowed_users": config.gateways.telegram.allowed_users,
                },
            )
            await gateway.initialize()
            await gateway.start()

            if message_handler:
                gateway.set_message_handler(message_handler)

            registry.register(gateway)
            initialized.append("telegram")
            _logger.info("gateway_initialized", gateway="telegram")
        except Exception as e:
            _logger.error("gateway_init_error", gateway="telegram", error=str(e))

    _logger.info("gateways_initialization_complete", count=len(initialized))
    return initialized


async def stop_all_gateways() -> None:
    """Stop all registered gateways."""
    from openbotx.models.enums import ProviderType
    from openbotx.providers.gateway.base import GatewayProvider

    registry = get_provider_registry()
    gateways = registry.get_all(ProviderType.GATEWAY)

    for gateway in gateways:
        if isinstance(gateway, GatewayProvider):
            try:
                await gateway.stop()
                _logger.info("gateway_stopped", gateway=gateway.name)
            except Exception as e:
                _logger.error("gateway_stop_error", gateway=gateway.name, error=str(e))
