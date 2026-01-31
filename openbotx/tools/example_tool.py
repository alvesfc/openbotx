"""Example tools for OpenBotX."""

from datetime import datetime

import requests

from openbotx.core.tools_registry import tool
from openbotx.models.tool_result import ToolResult


@tool(
    name="get_current_time",
    description="Get the current date and time",
)
def tool_get_current_time() -> ToolResult:
    """Get the current date and time.

    Returns:
        Structured result with current datetime
    """
    result = ToolResult()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result.add_text(current_time)
    return result


@tool(
    name="calculate",
    description="Perform a basic calculation",
)
def tool_calculate(expression: str) -> ToolResult:
    """Perform a basic calculation.

    Args:
        expression: Mathematical expression (e.g., "2 + 2")

    Returns:
        Structured result with calculation
    """
    result = ToolResult()

    # only allow safe operations
    allowed_chars = set("0123456789+-*/(). ")
    if not all(c in allowed_chars for c in expression):
        result.add_error("invalid characters in expression")
        return result

    try:
        calc_result = eval(expression)
        result.add_success(f"{expression} = {calc_result}")
        return result
    except Exception as e:
        result.add_error(str(e))
        return result


@tool(
    name="echo",
    description="Echo back the input text",
)
def tool_echo(text: str) -> ToolResult:
    """Echo back the input text.

    Args:
        text: Text to echo

    Returns:
        Structured result with echoed text
    """
    result = ToolResult()
    result.add_text(text)
    return result


@tool(
    name="get_weather",
    description="Get current weather information using latitude and longitude",
)
def tool_get_weather(latitude: float, longitude: float) -> ToolResult:
    """Get current weather from a public weather API.

    Args:
        latitude: Location latitude
        longitude: Location longitude

    Returns:
        Structured result with current weather data
    """
    result = ToolResult()

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current_weather": "true",
            },
            timeout=5,
        )
        response.raise_for_status()

        data = response.json()
        weather = data.get("current_weather")

        if not weather:
            result.add_error("weather data not available")
            return result

        temperature = weather.get("temperature")
        windspeed = weather.get("windspeed")
        weathercode = weather.get("weathercode")
        time = weather.get("time")

        result.add_text(
            f"temperature: {temperature} °C\n"
            f"wind speed: {windspeed} km/h\n"
            f"weather code: {weathercode}\n"
            f"time: {time}"
        )
        return result

    except Exception as e:
        result.add_error(f"failed to fetch weather: {str(e)}")
        return result
