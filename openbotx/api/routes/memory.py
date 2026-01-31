"""Memory API routes for OpenBotX."""

from fastapi import APIRouter, HTTPException

from openbotx.api.schemas import MemoryResponse, MemoryWriteRequest, SuccessResponse
from openbotx.core.context_store import get_context_store

router = APIRouter()


@router.get("/{channel_id}", response_model=MemoryResponse)
async def get_memory(channel_id: str) -> MemoryResponse:
    """Get memory for a channel.

    Args:
        channel_id: Channel ID

    Returns:
        Channel memory info
    """
    context_store = get_context_store()
    context = await context_store.load_context(channel_id)

    return MemoryResponse(
        channel_id=channel_id,
        history_count=len(context.history),
        summary=context.summary,
        total_tokens=context.total_tokens,
    )


@router.post("/{channel_id}", response_model=SuccessResponse)
async def write_memory(
    channel_id: str,
    request: MemoryWriteRequest,
) -> SuccessResponse:
    """Write to channel memory.

    Args:
        channel_id: Channel ID
        request: Memory write request

    Returns:
        Success response
    """
    context_store = get_context_store()

    await context_store.add_turn(
        channel_id=channel_id,
        role=request.role,
        content=request.content,
    )

    return SuccessResponse(message="Memory updated")


@router.delete("/{channel_id}", response_model=SuccessResponse)
async def clear_memory(channel_id: str) -> SuccessResponse:
    """Clear memory for a channel.

    Args:
        channel_id: Channel ID

    Returns:
        Success response
    """
    context_store = get_context_store()
    success = await context_store.clear_context(channel_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear memory")

    return SuccessResponse(message=f"Memory cleared for channel {channel_id}")


@router.get("", response_model=list[str])
async def list_channels() -> list[str]:
    """List all channels with stored memory.

    Returns:
        List of channel IDs
    """
    context_store = get_context_store()
    return context_store.list_channels()
