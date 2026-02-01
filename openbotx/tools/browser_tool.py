"""Browser tool for OpenBotX - web automation using Playwright."""

import asyncio
import json
import tempfile

from openbotx.core.tools_registry import tool
from openbotx.models.tool_result import ToolResult

# lazy import playwright to avoid startup cost
_browser = None
_playwright = None


async def _get_browser():
    """Get or create browser instance."""
    global _browser, _playwright

    if _browser is None:
        try:
            from playwright.async_api import async_playwright

            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                    "--window-position=0,0",
                ],
            )
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Install with: pip install playwright && playwright install chromium"
            )

    return _browser


async def _cleanup_browser() -> None:
    """Cleanup browser resources (internal)."""
    global _browser, _playwright

    if _browser:
        await _browser.close()
        _browser = None

    if _playwright:
        await _playwright.stop()
        _playwright = None


async def close_browser_resources() -> None:
    """Close browser and stop Playwright. Call on app shutdown so the Node process exits."""
    await _cleanup_browser()


@tool(
    name="browser_navigate",
    description="Launch a new browser window, navigate to a URL, and retrieve page content. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_navigate(
    url: str,
    wait_for: str = "domcontentloaded",
    extract_text: bool = True,
) -> ToolResult:
    """Navigate to a URL and get page content.

    Args:
        url: URL to navigate to
        wait_for: Wait condition (domcontentloaded, networkidle, load)
        extract_text: If True, extract text content; if False, return HTML

    Returns:
        Structured tool result with page content
    """
    result = ToolResult()

    try:
        browser = await _get_browser()
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until=wait_for, timeout=30000)
            await asyncio.sleep(2)

            # get page info
            title = await page.title()
            current_url = page.url

            if extract_text:
                # extract text content
                content = await page.evaluate("() => document.body.innerText")
            else:
                # get html
                content = await page.content()

            # truncate if too long
            max_length = 10000
            if len(content) > max_length:
                content = content[:max_length] + "\n\n[Content truncated...]"

            output = [
                f"# {title}",
                f"**URL**: {current_url}",
                "",
                content,
            ]

            result.add_text("\n".join(output))

        finally:
            await page.close()

        return result

    except Exception as e:
        result.add_error(f"Browser navigation failed: {e}")
        return result


@tool(
    name="browser_screenshot",
    description="Launch a new browser window, navigate to a URL, and take a screenshot. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_screenshot(
    url: str,
    full_page: bool = False,
) -> ToolResult:
    """Take a screenshot of a web page.

    Args:
        url: URL to screenshot
        full_page: If True, capture full scrollable page

    Returns:
        Structured tool result with screenshot path
    """
    result = ToolResult()

    try:
        browser = await _get_browser()
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # take screenshot
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                screenshot_path = f.name

            await page.screenshot(path=screenshot_path, full_page=full_page)

            title = await page.title()
            result.add_image(path=screenshot_path)
            result.add_text(f"Screenshot of: {title}\nURL: {url}")

        finally:
            await page.close()

        return result

    except Exception as e:
        result.add_error(f"Browser screenshot failed: {e}")
        return result


@tool(
    name="browser_extract",
    description="Launch a new browser window, navigate to a URL, and extract elements by CSS. Use only when the user explicitly asks to open or launch a browser.",
)
async def tool_browser_extract(
    url: str,
    selector: str,
    attribute: str | None = None,
) -> ToolResult:
    """Extract elements from a page using CSS selector.

    Args:
        url: URL to navigate to
        selector: CSS selector to find elements
        attribute: Optional attribute to extract (e.g., 'href', 'src')

    Returns:
        Structured tool result with extracted content
    """
    result = ToolResult()

    try:
        browser = await _get_browser()
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # find elements
            elements = await page.query_selector_all(selector)

            if not elements:
                result.add_text(f"No elements found matching selector: {selector}")
                return result

            extracted = []
            for i, element in enumerate(elements[:50]):  # limit to 50 elements
                if attribute:
                    value = await element.get_attribute(attribute)
                    if value:
                        extracted.append(f"{i + 1}. {value}")
                else:
                    text = await element.inner_text()
                    if text.strip():
                        extracted.append(f"{i + 1}. {text.strip()}")

            output = [
                f"# Extracted {len(extracted)} elements",
                f"**Selector**: `{selector}`",
                f"**URL**: {url}",
                "",
            ]
            output.extend(extracted)

            result.add_text("\n".join(output))

        finally:
            await page.close()

        return result

    except Exception as e:
        result.add_error(f"Browser extract failed: {e}")
        return result


@tool(
    name="browser_click",
    description="Launch a new browser window, navigate to a URL, and click an element. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_click(
    url: str,
    selector: str,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Click an element on the page.

    Args:
        url: URL to navigate to
        selector: CSS selector of the element to click
        timeout_ms: Max time to wait for the element (default 8000)

    Returns:
        Structured tool result
    """
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            locator = page.locator(selector).first
            await locator.click(timeout=timeout)
            result.add_text(f"Clicked element: {selector}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser click failed: {e}")
        return result


@tool(
    name="browser_type",
    description="Launch a new browser window, navigate to a URL, and type into an element. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_type(
    url: str,
    selector: str,
    text: str,
    submit: bool = False,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Type text into an input field.

    Args:
        url: URL to navigate to
        selector: CSS selector of the input/textarea
        text: Text to type
        submit: If True, press Enter after typing (e.g. submit form)
        timeout_ms: Max time to wait for the element (default 8000)

    Returns:
        Structured tool result
    """
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            locator = page.locator(selector).first
            await locator.fill(text, timeout=timeout)
            if submit:
                await locator.press("Enter", timeout=timeout)
            result.add_text(
                f"Typed into {selector}\nURL: {url}" + (" (submitted)" if submit else "")
            )
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser type failed: {e}")
        return result


@tool(
    name="browser_wait",
    description="Launch a new browser window, navigate to a URL, and wait. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_wait(
    url: str,
    selector: str | None = None,
    timeout_ms: int = 10000,
) -> ToolResult:
    """Wait for an element to appear on the page.

    Args:
        url: URL to navigate to
        selector: CSS selector to wait for; if omitted, waits for domcontentloaded only
        timeout_ms: Max time to wait (default 10000)

    Returns:
        Structured tool result
    """
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            if selector:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                result.add_text(f"Element visible: {selector}\nURL: {url}")
            else:
                result.add_text(f"Page loaded: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser wait failed: {e}")
        return result


@tool(
    name="browser_evaluate",
    description="Launch a new browser window, navigate to a URL, and run JavaScript. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": True},
)
async def tool_browser_evaluate(
    url: str,
    script: str,
    timeout_ms: int = 30000,
) -> ToolResult:
    """Execute JavaScript on the page.

    Args:
        url: URL to navigate to
        script: JavaScript expression or function body. Use a return statement for a value (e.g. "return document.title").
        timeout_ms: Max time for navigation + script (default 30000)

    Returns:
        Structured tool result with script return value
    """
    result = ToolResult()
    timeout = max(1000, min(60_000, timeout_ms))

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout - 2000)
            await asyncio.sleep(2)
            s = script.strip()
            body = s if s.startswith("return ") else f"return {s}"
            value = await page.evaluate(f"() => {{ {body} }}")
            if value is not None:
                result.add_text(str(value))
            else:
                result.add_text("ok")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser evaluate failed: {e}")
        return result


@tool(
    name="browser_hover",
    description="Launch a new browser window, navigate to a URL, and hover. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_hover(
    url: str,
    selector: str,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Hover over an element on the page."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.locator(selector).first.hover(timeout=timeout)
            result.add_text(f"Hovered: {selector}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser hover failed: {e}")
        return result


@tool(
    name="browser_drag",
    description="Launch a new browser window, navigate to a URL, and drag. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_drag(
    url: str,
    start_selector: str,
    end_selector: str,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Drag from start element to end element."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            start_loc = page.locator(start_selector).first
            end_loc = page.locator(end_selector).first
            await start_loc.drag_to(end_loc, timeout=timeout)
            result.add_text(f"Dragged {start_selector} -> {end_selector}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser drag failed: {e}")
        return result


@tool(
    name="browser_select",
    description="Launch a new browser window, navigate to a URL, and select options. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_select(
    url: str,
    selector: str,
    values: str,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Select option(s) in a select element. values: comma-separated values or labels."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    value_list = [v.strip() for v in values.split(",") if v.strip()]
    if not value_list:
        result.add_error("values must be a non-empty comma-separated list")
        return result
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            locator = page.locator(selector).first
            await locator.select_option(value_list, timeout=timeout)
            result.add_text(f"Selected {value_list} in {selector}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser select failed: {e}")
        return result


@tool(
    name="browser_fill",
    description="Launch a new browser window, navigate to a URL, and fill form fields. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_fill(
    url: str,
    fields_json: str,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Fill form fields. Example: [{\"selector\": \"#q\", \"type\": \"text\", \"value\": \"hello\"}, {\"selector\": \"#agree\", \"type\": \"checkbox\", \"value\": true}]."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        raw = json.loads(fields_json)
        if not isinstance(raw, list):
            result.add_error("fields_json must be a JSON array")
            return result
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            for item in raw:
                if not isinstance(item, dict):
                    continue
                sel = item.get("selector")
                typ = (item.get("type") or "text").strip().lower()
                if not sel:
                    continue
                locator = page.locator(sel).first
                if typ in ("checkbox", "radio"):
                    val = item.get("value")
                    checked = val in (True, 1, "1", "true")
                    await locator.set_checked(checked, timeout=timeout)
                else:
                    val = item.get("value")
                    text = "" if val is None else str(val)
                    await locator.fill(text, timeout=timeout)
            result.add_text(f"Filled {len(raw)} field(s)\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser fill failed: {e}")
        return result


@tool(
    name="browser_press",
    description="Launch a new browser window, navigate to a URL, and press a key. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_press(
    url: str,
    key: str,
    delay_ms: int = 0,
) -> ToolResult:
    """Press a key on the page (global, no selector)."""
    result = ToolResult()
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            delay = max(0, min(5000, delay_ms))
            await page.keyboard.press(key, delay=delay)
            result.add_text(f"Pressed key: {key}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser press failed: {e}")
        return result


@tool(
    name="browser_resize",
    description="Launch a new browser window, navigate to a URL, and set viewport. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_resize(
    url: str,
    width: int,
    height: int,
) -> ToolResult:
    """Set viewport size in pixels."""
    result = ToolResult()
    w, h = max(1, int(width)), max(1, int(height))
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.set_viewport_size({"width": w, "height": h})
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            result.add_text(f"Viewport {w}x{h}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser resize failed: {e}")
        return result


@tool(
    name="browser_snapshot",
    description="Launch a new browser window, navigate to a URL, and get text snapshot. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_snapshot(
    url: str,
    max_chars: int = 50000,
) -> ToolResult:
    """Get a text snapshot of the page content."""
    result = ToolResult()
    limit = max(1000, min(200_000, max_chars))
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            content = await page.evaluate("() => document.body.innerText")
            text = (content or "").strip()
            if len(text) > limit:
                text = text[:limit] + "\n\n[... truncated ...]"
            result.add_text(text or "(empty)")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser snapshot failed: {e}")
        return result


_trace_active = False


@tool(
    name="browser_trace_start",
    description="Start recording a Playwright trace in the launched browser. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_trace_start(
    screenshots: bool = True,
    snapshots: bool = True,
) -> ToolResult:
    """Start tracing the browser context."""
    global _trace_active
    result = ToolResult()
    if _trace_active:
        result.add_error("Trace already running; call browser_trace_stop first")
        return result
    try:
        browser = await _get_browser()
        if not browser.contexts:
            page = await browser.new_page()
            await page.close()
        contexts = browser.contexts
        if not contexts:
            result.add_error("No browser context")
            return result
        ctx = contexts[0]
        await ctx.tracing.start(screenshots=screenshots, snapshots=snapshots)
        _trace_active = True
        result.add_text("Trace started")
        return result
    except Exception as e:
        result.add_error(f"Browser trace start failed: {e}")
        return result


@tool(
    name="browser_trace_stop",
    description="Stop the current Playwright trace and save. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_trace_stop(
    path: str,
) -> ToolResult:
    """Stop tracing and save to path."""
    global _trace_active
    result = ToolResult()
    if not _trace_active:
        result.add_error("No active trace; call browser_trace_start first")
        return result
    try:
        browser = await _get_browser()
        contexts = browser.contexts
        if not contexts:
            _trace_active = False
            result.add_error("No browser context")
            return result
        ctx = contexts[0]
        await ctx.tracing.stop(path=path)
        _trace_active = False
        result.add_text(f"Trace saved to {path}")
        return result
    except Exception as e:
        _trace_active = False
        result.add_error(f"Browser trace stop failed: {e}")
        return result


@tool(
    name="browser_download",
    description="Launch a new browser window, navigate to a URL, and wait for download. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_download(
    url: str,
    timeout_ms: int = 60000,
    click_selector: str | None = None,
    save_path: str | None = None,
) -> ToolResult:
    """Wait for a download; optionally click an element to trigger it. Returns path and suggested filename."""
    result = ToolResult()
    timeout = max(1000, min(120_000, timeout_ms))
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            async with page.expect_download(timeout=timeout) as download_info:
                if click_selector:
                    await page.locator(click_selector).first.click(timeout=timeout)
            download = await download_info.value
            suggested = getattr(download, "suggested_filename", None) or "download.bin"
            out_path = save_path or tempfile.mktemp(suffix="-" + suggested)
            await download.save_as(out_path)
            result.add_text(f"Download saved: {out_path}\nSuggested filename: {suggested}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser download failed: {e}")
        return result


@tool(
    name="browser_cookies_get",
    description="Launch a new browser window, navigate to a URL, and get cookies. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_cookies_get(url: str) -> ToolResult:
    """Get all cookies."""
    result = ToolResult()
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            cookies = await page.context.cookies()
            result.add_text(json.dumps(cookies, indent=2))
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser cookies get failed: {e}")
        return result


@tool(
    name="browser_cookies_set",
    description="Add a cookie in the launched browser. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_cookies_set(
    url: str,
    name: str,
    value: str,
) -> ToolResult:
    """Set one cookie. Navigate to url first so domain is set; then add cookie."""
    result = ToolResult()
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.context.add_cookies([{"name": name, "value": value, "url": url}])
            result.add_text(f"Cookie set: {name}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser cookies set failed: {e}")
        return result


@tool(
    name="browser_cookies_clear",
    description="Launch a new browser window, navigate to a URL, and clear cookies. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_cookies_clear(url: str) -> ToolResult:
    """Clear all cookies."""
    result = ToolResult()
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.context.clear_cookies()
            result.add_text(f"Cookies cleared\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser cookies clear failed: {e}")
        return result


@tool(
    name="browser_storage_get",
    description="Launch a new browser window, navigate to a URL, and get storage. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_storage_get(
    url: str,
    kind: str = "local",
    key: str | None = None,
) -> ToolResult:
    """Get storage. kind: 'local' or 'session'. key: optional single key."""
    result = ToolResult()
    if kind not in ("local", "session"):
        result.add_error("kind must be 'local' or 'session'")
        return result
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            script = (
                "({ kind, key }) => { const s = kind === 'session' ? sessionStorage : localStorage; "
                "if (key) { const v = s.getItem(key); return v === null ? {} : { [key]: v }; } "
                "const o = {}; for (let i = 0; i < s.length; i++) { const k = s.key(i); if (k) o[k] = s.getItem(k); } return o; }"
            )
            values = await page.evaluate(script, {"kind": kind, "key": key})
            result.add_text(json.dumps(values or {}))
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser storage get failed: {e}")
        return result


@tool(
    name="browser_storage_set",
    description="Launch a new browser window, navigate to a URL, and set storage. Use only when the user explicitly asks to open or launch a browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_browser_storage_set(
    url: str,
    kind: str,
    key: str,
    value: str,
) -> ToolResult:
    """Set one storage key."""
    result = ToolResult()
    if kind not in ("local", "session"):
        result.add_error("kind must be 'local' or 'session'")
        return result
    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.evaluate(
                "({ kind, key, value }) => { const s = kind === 'session' ? sessionStorage : localStorage; s.setItem(key, value); }",
                {"kind": kind, "key": key, "value": value},
            )
            result.add_text(f"Storage set: {kind} {key}\nURL: {url}")
        finally:
            await page.close()
        return result
    except Exception as e:
        result.add_error(f"Browser storage set failed: {e}")
        return result
