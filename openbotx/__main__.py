"""OpenBotX main entry point.

Usage:
    python -m openbotx [--gateway cli|websocket|all] [--config config.yaml]

Examples:
    python -m openbotx                     # Run CLI gateway
    python -m openbotx --gateway websocket # Run WebSocket gateway
    python -m openbotx --gateway all       # Run all gateways
"""

import argparse
import asyncio
import os
import signal
import sys

from openbotx.core.gateway_manager import get_gateway_manager
from openbotx.core.orchestrator import get_orchestrator
from openbotx.helpers.browser_cleanup import close_browser_tools
from openbotx.helpers.config import get_config, load_config
from openbotx.helpers.gateway_loader import setup_gateways
from openbotx.helpers.logger import get_logger
from openbotx.helpers.memory_loader import initialize_memory_index
from openbotx.providers.base import get_provider_registry

logger = get_logger("main")


async def run_application(gateway_type: str = "cli", config_path: str | None = None) -> None:
    """Run the OpenBotX application.

    Args:
        gateway_type: Type of gateway to run (cli, websocket, all)
        config_path: Optional path to configuration file
    """
    # load configuration
    if config_path:
        config = load_config(config_path)
    else:
        config = get_config()

    logger.info("starting_openbotx", gateway=gateway_type)

    # initialize components
    orchestrator = get_orchestrator()
    gateway_manager = get_gateway_manager()

    # initialize memory index
    memory_index = await initialize_memory_index(config)
    if memory_index:
        logger.info("memory_index_ready")

    # set up gateways
    await setup_gateways(gateway_manager, gateway_type, config)

    # set message handler for all gateways
    gateway_manager.set_message_handler(orchestrator.enqueue_message)

    # initialize orchestrator
    await orchestrator.initialize()

    # register gateways with provider registry
    registry = get_provider_registry()
    for name in gateway_manager.list_gateways():
        gateway = gateway_manager.get(name)
        if gateway:
            registry.register(gateway)

    # start orchestrator
    await orchestrator.start()

    # set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("shutdown_signal_received", signal=sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # signal handlers not supported on Windows
            pass

    # start all gateways
    await gateway_manager.start_all()
    logger.info("all_gateways_started", gateways=gateway_manager.list_gateways())

    # wait for shutdown signal or gateway completion
    try:
        if gateway_type == "cli":
            # for CLI, wait for the gateway to finish (user exits)
            await gateway_manager.wait_for_shutdown()
        else:
            # for server gateways, wait for shutdown signal
            await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    # graceful shutdown
    logger.info("shutting_down")

    await gateway_manager.stop_all()
    await orchestrator.stop()
    await close_browser_tools()

    # close memory index
    if memory_index:
        memory_index.close()

    logger.info("shutdown_complete")


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="OpenBotX - AI Agent Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--gateway",
        "-g",
        choices=["cli", "websocket", "all"],
        default="cli",
        help="Gateway type to run (default: cli)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8765,
        help="WebSocket server port (default: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="WebSocket server host (default: 0.0.0.0)",
    )

    args = parser.parse_args()

    # set environment variables from command line args
    if args.port != 8765:
        os.environ["OPENBOTX_WS_PORT"] = str(args.port)
    if args.host != "0.0.0.0":
        os.environ["OPENBOTX_WS_HOST"] = args.host

    try:
        asyncio.run(run_application(args.gateway, args.config))
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("application_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
