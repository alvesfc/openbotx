"""Close Playwright/browser resources on app shutdown so the Node process exits."""

import asyncio

from openbotx.helpers.logger import get_logger

logger = get_logger("browser_cleanup")

_SHUTDOWN_TIMEOUT = 5.0


async def close_browser_tools() -> None:
    """Close browser and CDP resources (Playwright/Node). Call once on app shutdown.

    Uses a short timeout so if the Node process hangs, we do not block shutdown forever.
    """
    try:
        from openbotx.tools.browser_tool import close_browser_resources

        await asyncio.wait_for(close_browser_resources(), timeout=_SHUTDOWN_TIMEOUT)
    except TimeoutError:
        logger.warning("browser_cleanup_timeout", which="browser", timeout=_SHUTDOWN_TIMEOUT)
    except Exception as e:
        logger.debug("browser_cleanup_error", which="browser", error=str(e))

    try:
        from openbotx.tools.cdp_tool import close_cdp_resources

        await asyncio.wait_for(close_cdp_resources(), timeout=_SHUTDOWN_TIMEOUT)
    except TimeoutError:
        logger.warning("browser_cleanup_timeout", which="cdp", timeout=_SHUTDOWN_TIMEOUT)
    except Exception as e:
        logger.debug("browser_cleanup_error", which="cdp", error=str(e))
