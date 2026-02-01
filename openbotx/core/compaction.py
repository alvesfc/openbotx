"""Message compaction and summarization for OpenBotX.

Implements:
- Adaptive chunking based on context budget
- Progressive summarization when history exceeds limits
- Token-aware context management
"""

from dataclasses import dataclass, field
from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.helpers.tokens import count_tokens
from openbotx.models.enums import CompactionStrategy

logger = get_logger("compaction")


@dataclass
class CompactionConfig:
    """Configuration for message compaction."""

    strategy: CompactionStrategy = CompactionStrategy.ADAPTIVE
    context_budget_ratio: float = 0.4
    max_context_tokens: int = 100000
    reserve_for_response: int = 4096
    summary_target_tokens: int = 1000
    min_messages_to_keep: int = 4
    chunk_overlap_tokens: int = 200


@dataclass
class CompactionResult:
    """Result of compaction operation."""

    messages: list[dict[str, Any]]
    summary: str | None = None
    tokens_before: int = 0
    tokens_after: int = 0
    messages_removed: int = 0
    summary_updated: bool = False


@dataclass
class MessageChunk:
    """A chunk of messages for processing."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    token_count: int = 0
    start_index: int = 0
    end_index: int = 0


class MessageCompactor:
    """Handles message compaction and summarization.

    Implements three strategies:
    - ADAPTIVE: Dynamically adjusts based on available context budget
    - PROGRESSIVE: Incrementally summarizes older messages
    - TRUNCATE: Simple truncation of old messages
    """

    def __init__(self, config: CompactionConfig | None = None) -> None:
        """Initialize compactor.

        Args:
            config: Compaction configuration
        """
        self.config = config or CompactionConfig()
        self._logger = get_logger("compactor")

    def calculate_context_budget(self, total_tokens: int) -> int:
        """Calculate available context budget.

        Args:
            total_tokens: Total available tokens

        Returns:
            Token budget for context
        """
        budget = int(total_tokens * self.config.context_budget_ratio)
        return min(budget, self.config.max_context_tokens - self.config.reserve_for_response)

    def needs_compaction(
        self,
        messages: list[dict[str, Any]],
        token_budget: int,
    ) -> bool:
        """Check if messages need compaction.

        Args:
            messages: Message history
            token_budget: Available token budget

        Returns:
            True if compaction is needed
        """
        total_tokens = sum(count_tokens(m.get("content", "")) for m in messages)
        return total_tokens > token_budget

    def compact(
        self,
        messages: list[dict[str, Any]],
        token_budget: int,
        existing_summary: str | None = None,
    ) -> CompactionResult:
        """Compact messages to fit within token budget.

        Args:
            messages: Message history
            token_budget: Available token budget
            existing_summary: Existing conversation summary

        Returns:
            Compaction result with processed messages
        """
        if self.config.strategy == CompactionStrategy.ADAPTIVE:
            return self._compact_adaptive(messages, token_budget, existing_summary)
        elif self.config.strategy == CompactionStrategy.PROGRESSIVE:
            return self._compact_progressive(messages, token_budget, existing_summary)
        else:
            return self._compact_truncate(messages, token_budget, existing_summary)

    def _compact_adaptive(
        self,
        messages: list[dict[str, Any]],
        token_budget: int,
        existing_summary: str | None,
    ) -> CompactionResult:
        """Adaptive compaction that prioritizes recent context.

        Args:
            messages: Message history
            token_budget: Available token budget
            existing_summary: Existing summary

        Returns:
            Compaction result
        """
        tokens_before = sum(count_tokens(m.get("content", "")) for m in messages)

        # Reserve space for summary if exists
        summary_tokens = count_tokens(existing_summary) if existing_summary else 0
        available_budget = token_budget - summary_tokens

        # Start from most recent messages
        kept_messages: list[dict[str, Any]] = []
        current_tokens = 0
        removed_count = 0

        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.get("content", ""))

            if current_tokens + msg_tokens <= available_budget:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                removed_count += 1

        # Ensure minimum messages are kept
        if len(kept_messages) < self.config.min_messages_to_keep:
            kept_messages = messages[-self.config.min_messages_to_keep :]
            current_tokens = sum(count_tokens(m.get("content", "")) for m in kept_messages)
            removed_count = len(messages) - len(kept_messages)

        tokens_after = current_tokens + summary_tokens

        self._logger.info(
            "adaptive_compaction_complete",
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=removed_count,
        )

        return CompactionResult(
            messages=kept_messages,
            summary=existing_summary,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=removed_count,
            summary_updated=False,
        )

    def _compact_progressive(
        self,
        messages: list[dict[str, Any]],
        token_budget: int,
        existing_summary: str | None,
    ) -> CompactionResult:
        """Progressive compaction that summarizes older messages.

        Args:
            messages: Message history
            token_budget: Available token budget
            existing_summary: Existing summary

        Returns:
            Compaction result with updated summary
        """
        tokens_before = sum(count_tokens(m.get("content", "")) for m in messages)

        # Calculate how much space to reserve for new messages
        recent_budget = int(token_budget * 0.7)

        # Keep recent messages
        kept_messages: list[dict[str, Any]] = []
        current_tokens = 0
        cutoff_index = len(messages)

        for i, msg in enumerate(reversed(messages)):
            msg_tokens = count_tokens(msg.get("content", ""))

            if current_tokens + msg_tokens <= recent_budget:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
                cutoff_index = len(messages) - i - 1
            else:
                break

        # Messages to summarize
        messages_to_summarize = messages[:cutoff_index]
        removed_count = len(messages_to_summarize)

        # Generate summary for older messages (to be done by LLM)
        new_summary = None
        if messages_to_summarize:
            # Prepare content for summarization
            summary_content = self._prepare_for_summarization(
                messages_to_summarize,
                existing_summary,
            )
            # Note: Actual LLM summarization is done by the caller
            new_summary = summary_content

        tokens_after = current_tokens + (count_tokens(new_summary) if new_summary else 0)

        self._logger.info(
            "progressive_compaction_complete",
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_summarized=removed_count,
        )

        return CompactionResult(
            messages=kept_messages,
            summary=new_summary,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=removed_count,
            summary_updated=new_summary is not None,
        )

    def _compact_truncate(
        self,
        messages: list[dict[str, Any]],
        token_budget: int,
        existing_summary: str | None,
    ) -> CompactionResult:
        """Simple truncation compaction.

        Args:
            messages: Message history
            token_budget: Available token budget
            existing_summary: Existing summary

        Returns:
            Compaction result
        """
        tokens_before = sum(count_tokens(m.get("content", "")) for m in messages)

        # Reserve space for summary
        summary_tokens = count_tokens(existing_summary) if existing_summary else 0
        available_budget = token_budget - summary_tokens

        # Keep as many recent messages as possible
        kept_messages: list[dict[str, Any]] = []
        current_tokens = 0

        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.get("content", ""))

            if current_tokens + msg_tokens <= available_budget:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens

        removed_count = len(messages) - len(kept_messages)
        tokens_after = current_tokens + summary_tokens

        self._logger.info(
            "truncate_compaction_complete",
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=removed_count,
        )

        return CompactionResult(
            messages=kept_messages,
            summary=existing_summary,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=removed_count,
            summary_updated=False,
        )

    def _prepare_for_summarization(
        self,
        messages: list[dict[str, Any]],
        existing_summary: str | None,
    ) -> str:
        """Prepare messages for summarization.

        Args:
            messages: Messages to summarize
            existing_summary: Existing summary to incorporate

        Returns:
            Text ready for summarization
        """
        parts = []

        if existing_summary:
            parts.append(f"Previous summary:\n{existing_summary}\n")

        parts.append("Messages to incorporate:\n")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")

        return "\n".join(parts)

    def chunk_messages(
        self,
        messages: list[dict[str, Any]],
        chunk_size_tokens: int,
    ) -> list[MessageChunk]:
        """Split messages into chunks for processing.

        Args:
            messages: Messages to chunk
            chunk_size_tokens: Target size for each chunk

        Returns:
            List of message chunks
        """
        chunks: list[MessageChunk] = []
        current_chunk = MessageChunk(start_index=0)

        for i, msg in enumerate(messages):
            msg_tokens = count_tokens(msg.get("content", ""))

            if current_chunk.token_count + msg_tokens > chunk_size_tokens:
                # Save current chunk
                if current_chunk.messages:
                    current_chunk.end_index = i - 1
                    chunks.append(current_chunk)

                # Start new chunk with overlap
                overlap_start = max(0, len(current_chunk.messages) - 2)
                overlap_messages = current_chunk.messages[overlap_start:]
                overlap_tokens = sum(count_tokens(m.get("content", "")) for m in overlap_messages)

                current_chunk = MessageChunk(
                    messages=overlap_messages.copy(),
                    token_count=overlap_tokens,
                    start_index=i - len(overlap_messages),
                )

            current_chunk.messages.append(msg)
            current_chunk.token_count += msg_tokens

        # Add final chunk
        if current_chunk.messages:
            current_chunk.end_index = len(messages) - 1
            chunks.append(current_chunk)

        return chunks


# Summarization prompt for LLM
SUMMARIZATION_PROMPT = """Create a concise summary of the following conversation.

Focus on:
- Key topics discussed
- Important decisions made
- Action items or tasks completed
- Relevant context for future conversations

Keep the summary under 500 words but include all important information.

{content}

Summary:"""


def create_summarization_prompt(
    messages: list[dict[str, Any]],
    existing_summary: str | None = None,
) -> str:
    """Create a prompt for LLM summarization.

    Args:
        messages: Messages to summarize
        existing_summary: Existing summary to incorporate

    Returns:
        Prompt for LLM
    """
    parts = []

    if existing_summary:
        parts.append(f"Previous summary:\n{existing_summary}\n\n---\n")

    parts.append("Recent conversation:\n")

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        parts.append(f"**{role.capitalize()}**: {content}")

    content = "\n".join(parts)
    return SUMMARIZATION_PROMPT.format(content=content)


# Global compactor instance
_compactor: MessageCompactor | None = None


def get_compactor() -> MessageCompactor:
    """Get the global compactor instance."""
    global _compactor
    if _compactor is None:
        _compactor = MessageCompactor()
    return _compactor


def set_compactor(compactor: MessageCompactor) -> None:
    """Set the global compactor instance."""
    global _compactor
    _compactor = compactor
