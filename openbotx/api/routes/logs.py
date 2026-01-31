"""Logs API routes for OpenBotX."""

from fastapi import APIRouter

from openbotx.core.telemetry import get_telemetry

router = APIRouter()


@router.get("", response_model=dict)
async def get_logs(
    limit: int = 100,
    correlation_id: str | None = None,
) -> dict:
    """Get logs/telemetry data.

    Args:
        limit: Maximum entries to return
        correlation_id: Filter by correlation ID

    Returns:
        Log entries
    """
    telemetry = get_telemetry()

    return {
        "stats": telemetry.get_stats(),
        "token_usage": [u.model_dump() for u in telemetry.get_token_usage(limit=limit)],
        "tool_calls": [
            t.model_dump()
            for t in telemetry.get_tool_calls(
                correlation_id=correlation_id,
                limit=limit,
            )
        ],
    }


@router.get("/stats")
async def get_stats() -> dict:
    """Get telemetry statistics.

    Returns:
        Statistics
    """
    telemetry = get_telemetry()
    return telemetry.get_stats()


@router.get("/tokens")
async def get_token_usage(
    channel_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get token usage logs.

    Args:
        channel_id: Filter by channel
        limit: Maximum entries

    Returns:
        Token usage entries
    """
    telemetry = get_telemetry()
    usage = telemetry.get_token_usage(channel_id=channel_id, limit=limit)
    return [u.model_dump() for u in usage]


@router.get("/tools")
async def get_tool_calls(
    correlation_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get tool call logs.

    Args:
        correlation_id: Filter by correlation ID
        limit: Maximum entries

    Returns:
        Tool call entries
    """
    telemetry = get_telemetry()
    calls = telemetry.get_tool_calls(correlation_id=correlation_id, limit=limit)
    return [c.model_dump() for c in calls]


@router.delete("")
async def clear_logs(older_than_hours: int = 24) -> dict:
    """Clear old telemetry data.

    Args:
        older_than_hours: Clear data older than this

    Returns:
        Number of entries cleared
    """
    telemetry = get_telemetry()
    count = telemetry.clear_history(older_than_hours=older_than_hours)
    return {"cleared": count}
