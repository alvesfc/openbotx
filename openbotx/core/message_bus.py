"""Message bus for OpenBotX - queue system for processing messages."""

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.models.message import InboundMessage


class QueuedMessage(BaseModel):
    """Message in the queue with metadata."""

    message: InboundMessage
    retry_count: int = 0
    max_retries: int = 3
    queued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_attempt: datetime | None = None


class MessageBus:
    """Message bus for async message processing."""

    def __init__(
        self,
        max_queue_size: int = 1000,
        max_retries: int = 3,
    ) -> None:
        """Initialize message bus.

        Args:
            max_queue_size: Maximum queue size
            max_retries: Maximum retry attempts
        """
        self._queue: deque[QueuedMessage] = deque(maxlen=max_queue_size)
        self._dead_letter: deque[QueuedMessage] = deque(maxlen=100)
        self._processing: dict[str, QueuedMessage] = {}
        self._max_retries = max_retries
        self._logger = get_logger("message_bus")

        # Events
        self._message_event = asyncio.Event()
        self._running = False

        # Handlers
        self._handlers: list[Callable[[InboundMessage], Any]] = []

        # Stats
        self._stats = {
            "enqueued": 0,
            "processed": 0,
            "failed": 0,
            "retried": 0,
        }

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    @property
    def processing_count(self) -> int:
        """Get number of messages being processed."""
        return len(self._processing)

    @property
    def dead_letter_count(self) -> int:
        """Get dead letter queue size."""
        return len(self._dead_letter)

    @property
    def stats(self) -> dict[str, int]:
        """Get queue statistics."""
        return {
            **self._stats,
            "queue_size": self.queue_size,
            "processing": self.processing_count,
            "dead_letter": self.dead_letter_count,
        }

    def add_handler(self, handler: Callable[[InboundMessage], Any]) -> None:
        """Add a message handler.

        Args:
            handler: Async function to handle messages
        """
        self._handlers.append(handler)

    def enqueue(self, message: InboundMessage) -> str:
        """Add a message to the queue.

        Args:
            message: Message to enqueue

        Returns:
            Message ID
        """
        queued = QueuedMessage(
            message=message,
            max_retries=self._max_retries,
        )
        self._queue.append(queued)
        self._stats["enqueued"] += 1
        self._message_event.set()

        self._logger.info(
            "message_enqueued",
            message_id=message.id,
            channel_id=message.channel_id,
            gateway=message.gateway.value,
        )

        return message.id

    async def dequeue(self, timeout: float = 1.0) -> InboundMessage | None:
        """Get next message from queue.

        Args:
            timeout: Timeout in seconds

        Returns:
            Next message or None
        """
        while self._running:
            if self._queue:
                queued = self._queue.popleft()
                queued.last_attempt = datetime.now(UTC)
                self._processing[queued.message.id] = queued
                return queued.message

            # Wait for new message
            self._message_event.clear()
            try:
                await asyncio.wait_for(
                    self._message_event.wait(),
                    timeout=timeout,
                )
            except TimeoutError:
                continue

        return None

    def ack(self, message_id: str) -> None:
        """Acknowledge message processing completion.

        Args:
            message_id: ID of processed message
        """
        if message_id in self._processing:
            del self._processing[message_id]
            self._stats["processed"] += 1
            self._logger.info("message_acked", message_id=message_id)

    def nack(self, message_id: str, error: str | None = None) -> None:
        """Negative acknowledge - message processing failed.

        Args:
            message_id: ID of failed message
            error: Error message
        """
        if message_id not in self._processing:
            return

        queued = self._processing.pop(message_id)
        queued.retry_count += 1

        if queued.retry_count >= queued.max_retries:
            # Move to dead letter queue
            self._dead_letter.append(queued)
            self._stats["failed"] += 1
            self._logger.error(
                "message_dead_lettered",
                message_id=message_id,
                retry_count=queued.retry_count,
                error=error,
            )
        else:
            # Requeue for retry
            self._queue.appendleft(queued)
            self._stats["retried"] += 1
            self._message_event.set()
            self._logger.warning(
                "message_requeued",
                message_id=message_id,
                retry_count=queued.retry_count,
                error=error,
            )

    async def start(self) -> None:
        """Start the message bus."""
        self._running = True
        self._logger.info("message_bus_started")

    async def stop(self) -> None:
        """Stop the message bus."""
        self._running = False
        self._message_event.set()  # Wake up any waiting consumers
        self._logger.info("message_bus_stopped", stats=self._stats)

    async def process_one(self) -> bool:
        """Process a single message.

        Returns:
            True if a message was processed
        """
        message = await self.dequeue(timeout=0.1)
        if not message:
            return False

        try:
            for handler in self._handlers:
                result = handler(message)
                if asyncio.iscoroutine(result):
                    await result

            self.ack(message.id)
            return True

        except Exception as e:
            self._logger.error(
                "message_processing_error",
                message_id=message.id,
                error=str(e),
            )
            self.nack(message.id, str(e))
            return True

    async def run(self) -> None:
        """Run the message bus processing loop."""
        await self.start()

        while self._running:
            try:
                await self.process_one()
            except Exception as e:
                self._logger.error("message_bus_error", error=str(e))
                await asyncio.sleep(0.1)

    def get_dead_letters(self, limit: int = 100) -> list[QueuedMessage]:
        """Get messages from dead letter queue.

        Args:
            limit: Maximum number to return

        Returns:
            List of dead letter messages
        """
        return list(self._dead_letter)[:limit]

    def retry_dead_letter(self, message_id: str) -> bool:
        """Retry a dead letter message.

        Args:
            message_id: Message ID to retry

        Returns:
            True if message was requeued
        """
        for i, queued in enumerate(self._dead_letter):
            if queued.message.id == message_id:
                # Remove from dead letter and requeue
                del self._dead_letter[i]
                queued.retry_count = 0
                self._queue.append(queued)
                self._message_event.set()
                self._logger.info("dead_letter_retried", message_id=message_id)
                return True
        return False

    def clear_dead_letters(self) -> int:
        """Clear all dead letter messages.

        Returns:
            Number of messages cleared
        """
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count


# Global message bus instance
_message_bus: MessageBus | None = None


def get_message_bus() -> MessageBus:
    """Get the global message bus instance."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus
