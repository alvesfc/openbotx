"""CDP browser tool – control Chrome via Chrome DevTools Protocol.

Connect to an existing Chrome (or CDP-compatible) instance, e.g.:
  - Chrome with remote debugging: chrome --remote-debugging-port=9222
  - Or a CDP relay that exposes the same HTTP/WS API.

Default CDP endpoint: http://127.0.0.1:18792
"""

import asyncio
import json
import tempfile
from typing import Any

from openbotx.core.tools_registry import tool
from openbotx.models.tool_result import ToolResult

_cdp_browser: Any = None
_cdp_playwright: Any = None
_cdp_endpoint: str | None = None

# Console, errors, requests: key = (endpoint, id(page)) -> list
_cdp_console_logs: dict[tuple[str, int], list[dict]] = {}
_cdp_page_errors: dict[tuple[str, int], list[dict]] = {}
_cdp_requests_log: dict[tuple[str, int], list[dict]] = {}
_cdp_response_bodies: dict[tuple[str, int], list[dict]] = {}
_cdp_listeners_attached: set[tuple[str, int]] = set()
_MAX_CONSOLE = 500
_MAX_ERRORS = 200
_MAX_REQUESTS = 500
_MAX_RESPONSE_BODIES = 50
_MAX_BODY_PREVIEW = 100_000

# Next dialog response (one-shot)
_cdp_next_dialog: dict | None = None


def _normalize_cdp_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if not endpoint.startswith(("http://", "https://", "ws://", "wss://")):
        endpoint = "http://" + endpoint
    return endpoint


async def _get_cdp_browser(cdp_url: str):
    """Get or create Playwright browser connected over CDP. One connection per endpoint."""
    global _cdp_browser, _cdp_playwright, _cdp_endpoint

    endpoint = _normalize_cdp_endpoint(cdp_url)
    if _cdp_browser is not None and _cdp_endpoint == endpoint:
        return _cdp_browser

    if _cdp_browser is not None:
        try:
            await _cdp_browser.close()
        except Exception:
            pass
        _cdp_browser = None
    if _cdp_playwright is not None:
        try:
            await _cdp_playwright.stop()
        except Exception:
            pass
        _cdp_playwright = None
    _cdp_listeners_attached.clear()
    _cdp_console_logs.clear()
    _cdp_page_errors.clear()
    _cdp_requests_log.clear()
    _cdp_response_bodies.clear()

    try:
        from playwright.async_api import async_playwright

        _cdp_playwright = await async_playwright().start()
        _cdp_browser = await _cdp_playwright.chromium.connect_over_cdp(endpoint)
        _cdp_endpoint = endpoint
        return _cdp_browser
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Install with: pip install playwright && playwright install chromium"
        )


async def close_cdp_resources() -> None:
    """Close CDP browser and stop Playwright. Call on app shutdown so the Node process exits."""
    global _cdp_browser, _cdp_playwright, _cdp_endpoint

    if _cdp_browser is not None:
        try:
            await _cdp_browser.close()
        except Exception:
            pass
        _cdp_browser = None
    if _cdp_playwright is not None:
        try:
            await _cdp_playwright.stop()
        except Exception:
            pass
        _cdp_playwright = None
    _cdp_endpoint = None
    _cdp_listeners_attached.clear()
    _cdp_console_logs.clear()
    _cdp_page_errors.clear()
    _cdp_requests_log.clear()
    _cdp_response_bodies.clear()


def _get_page(browser, page_index: int = 0):
    """Get page by index from default context. Creates a new page if none exist."""
    if not browser.contexts:
        raise RuntimeError("CDP browser has no context")
    ctx = browser.contexts[0]
    pages = ctx.pages
    if not pages:
        raise RuntimeError(
            "CDP browser has no open tabs. Open a tab in Chrome or use cdp_new_tab first."
        )
    idx = max(0, min(page_index, len(pages) - 1))
    return pages[idx]


def _ensure_cdp_listeners(endpoint: str, page: Any) -> None:
    """Attach console/error/request listeners to page once per (endpoint, page)."""
    key = (endpoint, id(page))
    if key in _cdp_listeners_attached:
        return

    if key not in _cdp_console_logs:
        _cdp_console_logs[key] = []
    if key not in _cdp_page_errors:
        _cdp_page_errors[key] = []
    if key not in _cdp_requests_log:
        _cdp_requests_log[key] = []
    if key not in _cdp_response_bodies:
        _cdp_response_bodies[key] = []

    def on_console(msg: Any) -> None:
        arr = _cdp_console_logs.get(key)
        if arr is not None and len(arr) < _MAX_CONSOLE:
            arr.append({"type": msg.type, "text": msg.text})

    def on_page_error(err: Any) -> None:
        arr = _cdp_page_errors.get(key)
        if arr is not None and len(arr) < _MAX_ERRORS:
            arr.append({"message": str(err)})

    def on_request(req: Any) -> None:
        arr = _cdp_requests_log.get(key)
        if arr is not None and len(arr) < _MAX_REQUESTS:
            arr.append({"url": req.url, "method": req.method})

    async def on_response(resp: Any) -> None:
        arr = _cdp_response_bodies.get(key)
        if arr is None or len(arr) >= _MAX_RESPONSE_BODIES:
            return
        try:
            body = await resp.body()
            preview = body[:_MAX_BODY_PREVIEW].decode("utf-8", errors="replace")
            if len(body) > _MAX_BODY_PREVIEW:
                preview += "\n... truncated"
            arr.append({"url": resp.url, "status": resp.status, "body": preview})
        except Exception:
            pass

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("request", on_request)
    page.on("response", lambda r: asyncio.create_task(on_response(r)))
    _cdp_listeners_attached.add(key)


@tool(
    name="cdp_tabs",
    description="List open tabs (title, url, index). Use when accessing sites; prefer with cdp_navigate/cdp_snapshot over browser_* unless user asks to open a new browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_tabs(cdp_url: str = "http://127.0.0.1:18792") -> ToolResult:
    """List tabs from the CDP-connected browser."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_text("No context (no tabs)")
            return result
        ctx = browser.contexts[0]
        pages = ctx.pages
        lines = []
        for i, p in enumerate(pages):
            try:
                title = await p.title()
                url = p.url
                lines.append(f"{i}. {title or '(no title)'} | {url}")
            except Exception:
                lines.append(f"{i}. (unable to read)")
        result.add_text("\n".join(lines) if lines else "No tabs")
        return result
    except Exception as e:
        result.add_error(f"CDP tabs failed: {e}")
        return result


@tool(
    name="cdp_new_tab",
    description="Open a new tab and optionally navigate to a URL. Over relay this often fails; then call cdp_tabs and use cdp_navigate with page_index on an existing tab, or ask the user to open a tab in Chrome (Ctrl+T) and attach it.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_new_tab(
    cdp_url: str = "http://127.0.0.1:18792",
    url: str | None = None,
) -> ToolResult:
    """Open a new tab; optionally goto url. Over relay, new_page() may fail: ask user to open a tab, then use cdp_tabs and cdp_navigate."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        ctx = browser.contexts[0]
        try:
            page = await ctx.new_page()
        except Exception as e:
            err = str(e).lower()
            if "_page" in err or "undefined" in err or "new_page" in err:
                result.add_error(
                    "New tab not supported (relay). Ask the user: open a tab in Chrome (Ctrl+T or Cmd+T) and attach it with the extension, then say when ready. Then call cdp_tabs and cdp_navigate with the URL; do not refuse the request."
                )
                return result
            raise
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        result.add_text("New tab opened" + (f", navigated to {url}" if url else ""))
        return result
    except Exception as e:
        result.add_error(f"CDP new tab failed: {e}")
        return result


@tool(
    name="cdp_navigate",
    description="Navigate current tab to a URL. Use when user says 'access [site]', 'open [URL]', 'go to', 'navigate to'; prefer over browser_* unless user asks to open a new browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_navigate(
    url: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    wait_until: str = "domcontentloaded",
) -> ToolResult:
    """Navigate the selected tab to url."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.goto(url, wait_until=wait_until, timeout=30000)
        result.add_text(f"Navigated to {url}\nCurrent: {page.url}")
        return result
    except Exception as e:
        result.add_error(f"CDP navigate failed: {e}")
        return result


@tool(
    name="cdp_snapshot",
    description="Get text snapshot of the current page (truncated to max_chars, default 12000). Use after cdp_navigate to read page content; prefer over browser_* unless user asks to open a new browser.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_snapshot(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    max_chars: int = 12000,
) -> ToolResult:
    """Get body text of the page, truncated to max_chars (default 12000). Increase max_chars if you need more."""
    result = ToolResult()
    limit = max(1000, min(200_000, max_chars))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        content = await page.evaluate("() => document.body.innerText")
        text = (content or "").strip()
        truncated = len(text) > limit
        if truncated:
            text = (
                text[:limit]
                + "\n\n[... truncated, "
                + str(len(text) - limit)
                + " chars omitted; use max_chars to get more ...]"
            )
        result.add_text(text or "(empty)")
        return result
    except Exception as e:
        result.add_error(f"CDP snapshot failed: {e}")
        return result


@tool(
    name="cdp_screenshot",
    description="Take a screenshot of the current tab.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_screenshot(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    full_page: bool = False,
) -> ToolResult:
    """Capture screenshot of the page."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        await page.screenshot(path=path, full_page=full_page)
        title = await page.title()
        result.add_image(path=path)
        result.add_text(f"Screenshot: {title or page.url}")
        return result
    except Exception as e:
        result.add_error(f"CDP screenshot failed: {e}")
        return result


@tool(
    name="cdp_click",
    description="Click an element by CSS selector. Optionally double-click.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_click(
    selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
    double_click: bool = False,
) -> ToolResult:
    """Click the first element matching selector. Set double_click=True for double-click."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        locator = page.locator(selector).first
        if double_click:
            await locator.dblclick(timeout=timeout)
        else:
            await locator.click(timeout=timeout)
        result.add_text(f"{'Double-clicked' if double_click else 'Clicked'}: {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP click failed: {e}")
        return result


@tool(
    name="cdp_type",
    description="Type text into an element (e.g. input) by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_type(
    selector: str,
    text: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    submit: bool = False,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Fill and optionally submit (Enter) on the element."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        locator = page.locator(selector).first
        await locator.fill(text, timeout=timeout)
        if submit:
            await locator.press("Enter", timeout=timeout)
        result.add_text(f"Typed into {selector}" + (" (submitted)" if submit else ""))
        return result
    except Exception as e:
        result.add_error(f"CDP type failed: {e}")
        return result


@tool(
    name="cdp_press",
    description="Press a key on the page.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_press(
    cdp_url: str = "http://127.0.0.1:18792",
    key: str = "Enter",
    page_index: int = 0,
) -> ToolResult:
    """Press a keyboard key (e.g. Enter, Tab, Escape)."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.keyboard.press(key)
        result.add_text(f"Pressed key: {key}")
        return result
    except Exception as e:
        result.add_error(f"CDP press failed: {e}")
        return result


@tool(
    name="cdp_hover",
    description="Hover over an element by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_hover(
    selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Hover over the first element matching selector."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.locator(selector).first.hover(timeout=timeout)
        result.add_text(f"Hovered: {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP hover failed: {e}")
        return result


@tool(
    name="cdp_scroll",
    description="Scroll the page or an element.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_scroll(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    selector: str | None = None,
    delta_x: int = 0,
    delta_y: int = 500,
) -> ToolResult:
    """Scroll: use selector for element, or leave empty for viewport. delta_x/delta_y in pixels."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        if selector:
            await page.locator(selector).first.evaluate(f"el => el.scrollBy({delta_x}, {delta_y})")
            result.add_text(f"Scrolled element {selector} by ({delta_x}, {delta_y})")
        else:
            await page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
            result.add_text(f"Scrolled page by ({delta_x}, {delta_y})")
        return result
    except Exception as e:
        result.add_error(f"CDP scroll failed: {e}")
        return result


@tool(
    name="cdp_evaluate",
    description="Run JavaScript in the page. Returns JSON-serializable result.",
    security={"approval_required": False, "dangerous": True},
)
async def tool_cdp_evaluate(
    script: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Execute script in the page. Use return for a value."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        s = script.strip()
        body = s if "return " in s else f"return {s}"
        value = await page.evaluate(f"() => {{ {body} }}")
        if value is not None:
            result.add_text(json.dumps(value) if not isinstance(value, str) else value)
        else:
            result.add_text("ok")
        return result
    except Exception as e:
        result.add_error(f"CDP evaluate failed: {e}")
        return result


@tool(
    name="cdp_wait",
    description="Wait for a selector to appear or for a timeout.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_wait(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    selector: str | None = None,
    timeout_ms: int = 10000,
) -> ToolResult:
    """Wait for selector to be visible, or just wait timeout_ms if no selector."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        if selector:
            await page.locator(selector).first.wait_for(state="visible", timeout=timeout)
            result.add_text(f"Element visible: {selector}")
        else:
            await asyncio.sleep(timeout / 1000)
            result.add_text(f"Waited {timeout}ms")
        return result
    except Exception as e:
        result.add_error(f"CDP wait failed: {e}")
        return result


@tool(
    name="cdp_drag",
    description="Drag from one element to another by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_drag(
    start_selector: str,
    end_selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Drag from start element to end element."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        start_loc = page.locator(start_selector).first
        end_loc = page.locator(end_selector).first
        await start_loc.drag_to(end_loc, timeout=timeout)
        result.add_text(f"Dragged {start_selector} -> {end_selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP drag failed: {e}")
        return result


@tool(
    name="cdp_select",
    description="Select option(s) in a <select> by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_select(
    selector: str,
    values: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Select option(s). values: comma-separated value or label."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    value_list = [v.strip() for v in values.split(",") if v.strip()]
    if not value_list:
        result.add_error("values must be non-empty comma-separated list")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.locator(selector).first.select_option(value_list, timeout=timeout)
        result.add_text(f"Selected {value_list} in {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP select failed: {e}")
        return result


@tool(
    name="cdp_fill",
    description="Fill multiple form fields (CDP). fields_json: JSON array of {selector, type: text|checkbox|radio, value?}.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_fill(
    fields_json: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Fill form fields. Example: [{\"selector\": \"#q\", \"type\": \"text\", \"value\": \"hello\"}]."""
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
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
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
        result.add_text(f"Filled {len(raw)} field(s)")
        return result
    except Exception as e:
        result.add_error(f"CDP fill failed: {e}")
        return result


@tool(
    name="cdp_resize",
    description="Set viewport size.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_resize(
    width: int,
    height: int,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Set viewport width and height in pixels."""
    result = ToolResult()
    w, h = max(1, int(width)), max(1, int(height))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.set_viewport_size({"width": w, "height": h})
        result.add_text(f"Viewport set to {w}x{h}")
        return result
    except Exception as e:
        result.add_error(f"CDP resize failed: {e}")
        return result


@tool(
    name="cdp_close_tab",
    description="Close a tab by index.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_close_tab(
    page_index: int = 0,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Close the tab at page_index. At least one tab must remain."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        pages = ctx.pages
        if len(pages) <= 1:
            result.add_error("Cannot close the only tab")
            return result
        idx = max(0, min(page_index, len(pages) - 1))
        await pages[idx].close()
        result.add_text(f"Closed tab {idx}")
        return result
    except Exception as e:
        result.add_error(f"CDP close tab failed: {e}")
        return result


@tool(
    name="cdp_screenshot_element",
    description="Take a screenshot of a single element by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_screenshot_element(
    selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Screenshot only the element matching selector."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        locator = page.locator(selector).first
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        await locator.screenshot(path=path, timeout=timeout)
        result.add_image(path=path)
        result.add_text(f"Screenshot of element: {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP screenshot element failed: {e}")
        return result


@tool(
    name="cdp_download",
    description="Wait for the next download after optional click.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_download(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    click_selector: str | None = None,
    save_path: str | None = None,
    timeout_ms: int = 60000,
) -> ToolResult:
    """Wait for download; optionally click an element to trigger it."""
    result = ToolResult()
    timeout = max(1000, min(120_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        async with page.expect_download(timeout=timeout) as download_info:
            if click_selector:
                await page.locator(click_selector).first.click(timeout=timeout)
        download = await download_info.value
        suggested = getattr(download, "suggested_filename", None) or "download.bin"
        out_path = save_path or tempfile.mktemp(suffix="-" + suggested)
        await download.save_as(out_path)
        result.add_text(f"Download saved: {out_path}\nSuggested: {suggested}")
        return result
    except Exception as e:
        result.add_error(f"CDP download failed: {e}")
        return result


_cdp_trace_active = False


@tool(
    name="cdp_trace_start",
    description="Start Playwright trace recording.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_trace_start(
    cdp_url: str = "http://127.0.0.1:18792",
    screenshots: bool = True,
    snapshots: bool = True,
) -> ToolResult:
    """Start tracing the context."""
    global _cdp_trace_active
    result = ToolResult()
    if _cdp_trace_active:
        result.add_error("Trace already running; call cdp_trace_stop first")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.tracing.start(screenshots=screenshots, snapshots=snapshots)
        _cdp_trace_active = True
        result.add_text("Trace started")
        return result
    except Exception as e:
        result.add_error(f"CDP trace start failed: {e}")
        return result


@tool(
    name="cdp_trace_stop",
    description="Stop trace and save to path.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_trace_stop(
    path: str,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Stop tracing and save to file (e.g. trace.zip)."""
    global _cdp_trace_active
    result = ToolResult()
    if not _cdp_trace_active:
        result.add_error("No active trace; call cdp_trace_start first")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            _cdp_trace_active = False
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.tracing.stop(path=path)
        _cdp_trace_active = False
        result.add_text(f"Trace saved to {path}")
        return result
    except Exception as e:
        _cdp_trace_active = False
        result.add_error(f"CDP trace stop failed: {e}")
        return result


@tool(
    name="cdp_cookies_get",
    description="Get cookies for the CDP browser context.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_cookies_get(
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Get all cookies."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        cookies = await ctx.cookies()
        result.add_text(json.dumps(cookies, indent=2))
        return result
    except Exception as e:
        result.add_error(f"CDP cookies get failed: {e}")
        return result


@tool(
    name="cdp_cookies_set",
    description="Set a cookie.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_cookies_set(
    name: str,
    value: str,
    url: str,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Set one cookie; url is required for domain."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.add_cookies([{"name": name, "value": value, "url": url}])
        result.add_text(f"Cookie set: {name}")
        return result
    except Exception as e:
        result.add_error(f"CDP cookies set failed: {e}")
        return result


@tool(
    name="cdp_cookies_clear",
    description="Clear all cookies.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_cookies_clear(
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Clear all cookies in the context."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.clear_cookies()
        result.add_text("Cookies cleared")
        return result
    except Exception as e:
        result.add_error(f"CDP cookies clear failed: {e}")
        return result


@tool(
    name="cdp_storage_get",
    description="Get localStorage or sessionStorage.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_storage_get(
    kind: str = "local",
    key: str | None = None,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Get storage. kind: 'local' or 'session'. key: optional single key."""
    result = ToolResult()
    if kind not in ("local", "session"):
        result.add_error("kind must be 'local' or 'session'")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        script = (
            "({ kind, key }) => { const s = kind === 'session' ? sessionStorage : localStorage; "
            "if (key) { const v = s.getItem(key); return v === null ? {} : { [key]: v }; } "
            "const o = {}; for (let i = 0; i < s.length; i++) { const k = s.key(i); if (k) o[k] = s.getItem(k); } return o; }"
        )
        values = await page.evaluate(script, {"kind": kind, "key": key})
        result.add_text(json.dumps(values or {}))
        return result
    except Exception as e:
        result.add_error(f"CDP storage get failed: {e}")
        return result


@tool(
    name="cdp_storage_set",
    description="Set a key in localStorage or sessionStorage.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_storage_set(
    kind: str,
    key: str,
    value: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Set one storage key."""
    result = ToolResult()
    if kind not in ("local", "session"):
        result.add_error("kind must be 'local' or 'session'")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.evaluate(
            "({ kind, key, value }) => { const s = kind === 'session' ? sessionStorage : localStorage; s.setItem(key, value); }",
            {"kind": kind, "key": key, "value": value},
        )
        result.add_text(f"Storage set: {kind} {key}")
        return result
    except Exception as e:
        result.add_error(f"CDP storage set failed: {e}")
        return result


@tool(
    name="cdp_highlight",
    description="Highlight an element by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_highlight(
    selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Temporarily highlight the element (for debugging)."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.locator(selector).first.highlight(timeout=timeout)
        result.add_text(f"Highlighted: {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP highlight failed: {e}")
        return result


@tool(
    name="cdp_snapshot_dom",
    description="Get DOM snapshot with refs (ref=selector map) for interactive elements.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_snapshot_dom(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    limit: int = 500,
    max_text: int = 200,
) -> ToolResult:
    """Get compact DOM tree with refs (n1, n2...) for use with selectors."""
    result = ToolResult()
    limit = max(1, min(2000, limit))
    max_text = max(0, min(1000, max_text))
    for_each_js = "refToSelector[n.ref] = n.selector;"
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        script = f"""
        (() => {{
          const limit = {limit};
          const maxText = {max_text};
          const nodes = [];
          const root = document.body || document.documentElement;
          if (!root) return {{ nodes: [], refToSelector: {{}} }};
          const stack = [{{ el: root, depth: 0 }}];
          while (stack.length && nodes.length < limit) {{
            const {{ el, depth }} = stack.pop();
            if (!el || el.nodeType !== 1) continue;
            const ref = 'n' + (nodes.length + 1);
            const tag = (el.tagName || '').toLowerCase();
            let text = '';
            try {{ text = (el.innerText || '').trim().slice(0, maxText); }} catch {{}}
            const role = el.getAttribute?.('role') || '';
            const name = el.getAttribute?.('aria-label') || el.title || '';
            const id = el.id ? '#' + el.id : '';
            const sel = tag + (id || (el.className ? '.' + String(el.className).split(/\\s+/)[0] : ''));
            nodes.push({{ ref, depth, tag, role, name, text: text || undefined, selector: sel }});
            const children = el.children ? Array.from(el.children) : [];
            for (let i = children.length - 1; i >= 0; i--) stack.push({{ el: children[i], depth: depth + 1 }});
          }}
          const refToSelector = {{}};
          nodes.forEach(n => {{ {for_each_js} }});
          return {{ nodes, refToSelector }};
        }})()
        """
        data = await page.evaluate(script)
        nodes = data.get("nodes", [])
        ref_to_sel = data.get("refToSelector", {})
        lines = []
        for n in nodes:
            indent = "  " * n.get("depth", 0)
            parts = [
                n.get("ref", ""),
                n.get("tag", ""),
                n.get("role", ""),
                n.get("name", ""),
                (n.get("text") or "")[:80],
            ]
            lines.append(indent + " | ".join(p for p in parts if p))
        result.add_text("\n".join(lines) + "\n\nrefToSelector: " + json.dumps(ref_to_sel)[:2000])
        return result
    except Exception as e:
        result.add_error(f"CDP snapshot dom failed: {e}")
        return result


@tool(
    name="cdp_scroll_into_view",
    description="Scroll an element into view by CSS selector.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_scroll_into_view(
    selector: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    timeout_ms: int = 8000,
) -> ToolResult:
    """Scroll the element into view."""
    result = ToolResult()
    timeout = max(500, min(60_000, timeout_ms))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.locator(selector).first.scroll_into_view_if_needed(timeout=timeout)
        result.add_text(f"Scrolled into view: {selector}")
        return result
    except Exception as e:
        result.add_error(f"CDP scroll into view failed: {e}")
        return result


@tool(
    name="cdp_set_offline",
    description="Set offline mode (simulate no network) for the CDP browser context.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_offline(
    offline: bool,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Enable or disable offline mode."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_offline(offline)
        result.add_text(f"Offline mode: {offline}")
        return result
    except Exception as e:
        result.add_error(f"CDP set offline failed: {e}")
        return result


@tool(
    name="cdp_set_headers",
    description="Set extra HTTP headers for all requests.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_headers(
    headers_json: str,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Set extra headers. Example: {\"X-Debug\": \"1\"}. Pass {} to clear."""
    result = ToolResult()
    try:
        headers = json.loads(headers_json)
        if not isinstance(headers, dict):
            result.add_error("headers_json must be a JSON object")
            return result
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_extra_http_headers({k: str(v) for k, v in headers.items()})
        result.add_text(f"Headers set: {list(headers.keys())}")
        return result
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON: {e}")
        return result
    except Exception as e:
        result.add_error(f"CDP set headers failed: {e}")
        return result


@tool(
    name="cdp_set_credentials",
    description="Set HTTP Basic Auth credentials.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_credentials(
    username: str,
    password: str,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Set HTTP auth credentials for the context."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_http_credentials({"username": username, "password": password})
        result.add_text("Credentials set")
        return result
    except Exception as e:
        result.add_error(f"CDP set credentials failed: {e}")
        return result


@tool(
    name="cdp_set_credentials_clear",
    description="Clear HTTP Basic Auth credentials.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_credentials_clear(
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Clear HTTP auth credentials."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_http_credentials(None)
        result.add_text("Credentials cleared")
        return result
    except Exception as e:
        result.add_error(f"CDP set credentials clear failed: {e}")
        return result


@tool(
    name="cdp_set_geo",
    description="Set geolocation for the CDP browser context.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_geo(
    latitude: float,
    longitude: float,
    accuracy: float | None = None,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Set geolocation (lat, lon, optional accuracy in meters)."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        opts: dict = {"latitude": latitude, "longitude": longitude}
        if accuracy is not None:
            opts["accuracy"] = accuracy
        await ctx.grant_permissions(["geolocation"])
        await ctx.set_geolocation(opts)
        result.add_text(f"Geo set: {latitude}, {longitude}")
        return result
    except Exception as e:
        result.add_error(f"CDP set geo failed: {e}")
        return result


@tool(
    name="cdp_set_geo_clear",
    description="Clear geolocation.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_geo_clear(
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Clear geolocation and geolocation permission."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_geolocation(None)
        try:
            await ctx.clear_permissions()
        except AttributeError:
            pass
        result.add_text("Geo cleared")
        return result
    except Exception as e:
        result.add_error(f"CDP set geo clear failed: {e}")
        return result


@tool(
    name="cdp_set_locale",
    description="Set Accept-Language header for the CDP browser context.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_locale(
    locale: str,
    cdp_url: str = "http://127.0.0.1:18792",
) -> ToolResult:
    """Set locale (e.g. en-US, pt-BR) via Accept-Language."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        if not browser.contexts:
            result.add_error("No context")
            return result
        ctx = browser.contexts[0]
        await ctx.set_extra_http_headers({"Accept-Language": locale})
        result.add_text(f"Locale set: {locale}")
        return result
    except Exception as e:
        result.add_error(f"CDP set locale failed: {e}")
        return result


@tool(
    name="cdp_set_device",
    description="Set viewport and User-Agent to a Playwright device preset.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_set_device(
    device_name: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Set device (e.g. iPhone 14, Pixel 5). Uses Playwright device list."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        device = _cdp_playwright.devices.get(device_name) if _cdp_playwright else None
        if not device:
            result.add_error(
                f"Unknown device: {device_name}. Common: iPhone 14, Pixel 5, Galaxy S9+."
            )
            return result
        page = _get_page(browser, page_index)
        if device.get("viewport"):
            await page.set_viewport_size(device["viewport"])
        if device.get("user_agent"):
            ctx = browser.contexts[0]
            await ctx.set_extra_http_headers({"User-Agent": device["user_agent"]})
        result.add_text(f"Device set: {device_name}")
        return result
    except Exception as e:
        result.add_error(f"CDP set device failed: {e}")
        return result


@tool(
    name="cdp_pdf",
    description="Save the current page as PDF.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_pdf(
    path: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Save page as PDF to the given path."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.pdf(path=path)
        result.add_text(f"PDF saved to {path}")
        return result
    except Exception as e:
        result.add_error(f"CDP pdf failed: {e}")
        return result


@tool(
    name="cdp_dialog_respond",
    description="Set response for the next JavaScript dialog (alert/confirm/prompt). Call before the action that opens the dialog.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_dialog_respond(
    accept: bool,
    prompt_text: str | None = None,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Arm next dialog: accept=True/False, prompt_text for prompt()."""
    global _cdp_next_dialog
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)

        async def handle_dialog(dialog: Any) -> None:
            if accept:
                await dialog.accept(prompt_text)
            else:
                await dialog.dismiss()

        page.once("dialog", handle_dialog)
        _cdp_next_dialog = {"accept": accept, "prompt_text": prompt_text}
        result.add_text(
            f"Next dialog will be {'accepted' if accept else 'dismissed'}"
            + (" with prompt_text" if prompt_text else "")
        )
        return result
    except Exception as e:
        result.add_error(f"CDP dialog respond failed: {e}")
        return result


@tool(
    name="cdp_upload_arm",
    description="Arm file chooser: set files to use for the next file input.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_upload_arm(
    paths: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Set file paths (comma-separated) for the next file chooser. Then trigger the chooser (e.g. click upload button)."""
    result = ToolResult()
    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    if not path_list:
        result.add_error("paths must be non-empty comma-separated list")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)

        async def handle_file_chooser(chooser: Any) -> None:
            await chooser.set_files(path_list)

        page.once("filechooser", handle_file_chooser)
        result.add_text(
            f"File chooser armed with {len(path_list)} path(s). Trigger the upload to use them."
        )
        return result
    except Exception as e:
        result.add_error(f"CDP upload arm failed: {e}")
        return result


@tool(
    name="cdp_console_start",
    description="Start collecting console messages, page errors, and requests for this tab.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_console_start(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Start collecting console/errors/requests. Then use cdp_console_get, cdp_errors_get, cdp_requests_get."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        endpoint = _normalize_cdp_endpoint(cdp_url)
        _ensure_cdp_listeners(endpoint, page)
        result.add_text("Collecting console, errors, and requests for this tab.")
        return result
    except Exception as e:
        result.add_error(f"CDP console start failed: {e}")
        return result


@tool(
    name="cdp_console_get",
    description="Get collected console messages (call cdp_console_start first).",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_console_get(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    clear: bool = False,
) -> ToolResult:
    """Return collected console messages. clear=True to reset after returning."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        endpoint = _normalize_cdp_endpoint(cdp_url)
        _ensure_cdp_listeners(endpoint, page)
        key = (endpoint, id(page))
        messages = _cdp_console_logs.get(key, [])
        result.add_text(json.dumps(messages, indent=2))
        if clear:
            _cdp_console_logs[key] = []
        return result
    except Exception as e:
        result.add_error(f"CDP console get failed: {e}")
        return result


@tool(
    name="cdp_errors_get",
    description="Get collected page errors (call cdp_console_start first).",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_errors_get(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    clear: bool = False,
) -> ToolResult:
    """Return collected page errors."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        endpoint = _normalize_cdp_endpoint(cdp_url)
        _ensure_cdp_listeners(endpoint, page)
        key = (endpoint, id(page))
        errors = _cdp_page_errors.get(key, [])
        result.add_text(json.dumps(errors, indent=2))
        if clear:
            _cdp_page_errors[key] = []
        return result
    except Exception as e:
        result.add_error(f"CDP errors get failed: {e}")
        return result


@tool(
    name="cdp_requests_get",
    description="Get collected request log (call cdp_console_start first).",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_requests_get(
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    clear: bool = False,
) -> ToolResult:
    """Return collected requests (url, method)."""
    result = ToolResult()
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        endpoint = _normalize_cdp_endpoint(cdp_url)
        _ensure_cdp_listeners(endpoint, page)
        key = (endpoint, id(page))
        requests = _cdp_requests_log.get(key, [])
        result.add_text(json.dumps(requests, indent=2))
        if clear:
            _cdp_requests_log[key] = []
        return result
    except Exception as e:
        result.add_error(f"CDP requests get failed: {e}")
        return result


@tool(
    name="cdp_response_body",
    description="Get response body for a URL pattern from collected responses (call cdp_console_start first).",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_response_body(
    url_pattern: str,
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
    max_chars: int = 10000,
) -> ToolResult:
    """Return body of first response whose URL contains url_pattern. Requires cdp_console_start."""
    result = ToolResult()
    max_chars = max(0, min(500_000, max_chars))
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        endpoint = _normalize_cdp_endpoint(cdp_url)
        _ensure_cdp_listeners(endpoint, page)
        key = (endpoint, id(page))
        bodies = _cdp_response_bodies.get(key, [])
        for b in bodies:
            if url_pattern in b.get("url", ""):
                text = b.get("body", "")[:max_chars]
                if len(b.get("body", "")) > max_chars:
                    text += "\n... truncated"
                result.add_text(text)
                return result
        result.add_text(
            "No matching response body found. Call cdp_console_start and trigger the request."
        )
        return result
    except Exception as e:
        result.add_error(f"CDP response body failed: {e}")
        return result


@tool(
    name="cdp_storage_clear",
    description="Clear all localStorage or sessionStorage.",
    security={"approval_required": False, "dangerous": False},
)
async def tool_cdp_storage_clear(
    kind: str = "local",
    cdp_url: str = "http://127.0.0.1:18792",
    page_index: int = 0,
) -> ToolResult:
    """Clear all keys in localStorage or sessionStorage."""
    result = ToolResult()
    if kind not in ("local", "session"):
        result.add_error("kind must be 'local' or 'session'")
        return result
    try:
        browser = await _get_cdp_browser(cdp_url)
        page = _get_page(browser, page_index)
        await page.evaluate(
            "({ kind }) => { const s = kind === 'session' ? sessionStorage : localStorage; s.clear(); }",
            {"kind": kind},
        )
        result.add_text(f"Storage cleared: {kind}")
        return result
    except Exception as e:
        result.add_error(f"CDP storage clear failed: {e}")
        return result
