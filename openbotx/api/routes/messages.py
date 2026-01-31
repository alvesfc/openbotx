"""Messages API routes for OpenBotX."""

from fastapi import APIRouter, HTTPException

from openbotx.api.schemas import (
    MessageCreate,
    MessageHistoryResponse,
    MessageResponse,
    SuccessResponse,
)
from openbotx.core.context_store import get_context_store
from openbotx.core.orchestrator import get_orchestrator
from openbotx.models.enums import MessageStatus
from openbotx.models.message import InboundMessage

router = APIRouter()


@router.post("", response_model=MessageResponse)
async def enqueue_message(request: MessageCreate) -> MessageResponse:
    """Enqueue a message for processing.

    Args:
        request: Message creation request

    Returns:
        Created message
    """
    orchestrator = get_orchestrator()

    message = InboundMessage(
        channel_id=request.channel_id,
        user_id=request.user_id,
        gateway=request.gateway,
        message_type=request.message_type,
        text=request.text,
        metadata=request.metadata,
    )

    message_id = orchestrator.enqueue_message(message)

    return MessageResponse(
        id=message_id,
        channel_id=message.channel_id,
        user_id=message.user_id,
        gateway=message.gateway.value,
        message_type=message.message_type.value,
        text=message.text,
        status=MessageStatus.PENDING.value,
        correlation_id=message.correlation_id,
        timestamp=message.timestamp,
    )


@router.get("/{channel_id}/history", response_model=MessageHistoryResponse)
async def get_message_history(
    channel_id: str,
    limit: int = 50,
) -> MessageHistoryResponse:
    """Get message history for a channel.

    Args:
        channel_id: Channel ID
        limit: Maximum messages to return

    Returns:
        Message history
    """
    context_store = get_context_store()
    context = await context_store.load_context(channel_id)

    messages = []
    for turn in context.history[-limit:]:
        messages.append(
            MessageResponse(
                id="",  # Historical messages don't have IDs stored
                channel_id=channel_id,
                user_id=None,
                gateway="unknown",
                message_type="text",
                text=turn.content,
                status="completed",
                correlation_id="",
                timestamp=turn.timestamp,
            )
        )

    return MessageHistoryResponse(
        channel_id=channel_id,
        messages=messages,
        total=len(messages),
    )


@router.delete("/{channel_id}/history", response_model=SuccessResponse)
async def clear_message_history(channel_id: str) -> SuccessResponse:
    """Clear message history for a channel.

    Args:
        channel_id: Channel ID

    Returns:
        Success response
    """
    context_store = get_context_store()
    success = await context_store.clear_context(channel_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear history")

    return SuccessResponse(message=f"History cleared for channel {channel_id}")
