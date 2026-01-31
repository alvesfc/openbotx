"""Context store for OpenBotX - memory management using .md files."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.helpers.tokens import TokenBudget, count_tokens


class ConversationTurn(BaseModel):
    """A single turn in a conversation."""

    role: str  # user, assistant
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelContext(BaseModel):
    """Context for a specific channel."""

    channel_id: str
    history: list[ConversationTurn] = Field(default_factory=list)
    summary: str | None = None
    summary_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int = 0


class ContextStore:
    """Store and manage conversation context using markdown files."""

    def __init__(
        self,
        memory_path: str = "./memory",
        max_history_tokens: int = 50000,
        summary_threshold_tokens: int = 30000,
    ) -> None:
        """Initialize context store.

        Args:
            memory_path: Path to memory directory
            max_history_tokens: Maximum tokens in history
            summary_threshold_tokens: Token count to trigger summarization
        """
        self.memory_path = Path(memory_path)
        self.max_history_tokens = max_history_tokens
        self.summary_threshold_tokens = summary_threshold_tokens
        self._logger = get_logger("context_store")
        self._cache: dict[str, ChannelContext] = {}

        # Ensure directory exists
        self.memory_path.mkdir(parents=True, exist_ok=True)

    def _get_channel_path(self, channel_id: str) -> Path:
        """Get path for channel memory file."""
        # Sanitize channel ID for filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_id)
        return self.memory_path / f"{safe_id}.md"

    def _get_summary_path(self, channel_id: str) -> Path:
        """Get path for channel summary file."""
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_id)
        return self.memory_path / f"{safe_id}_summary.md"

    async def load_context(self, channel_id: str) -> ChannelContext:
        """Load context for a channel.

        Args:
            channel_id: Channel identifier

        Returns:
            ChannelContext with history and summary
        """
        # Check cache first
        if channel_id in self._cache:
            return self._cache[channel_id]

        context = ChannelContext(channel_id=channel_id)

        # Load history
        history_path = self._get_channel_path(channel_id)
        if history_path.exists():
            try:
                content = history_path.read_text()
                context.history = self._parse_history(content)
                context.total_tokens = count_tokens(content)
            except Exception as e:
                self._logger.error(
                    "load_history_error",
                    channel_id=channel_id,
                    error=str(e),
                )

        # Load summary
        summary_path = self._get_summary_path(channel_id)
        if summary_path.exists():
            try:
                context.summary = summary_path.read_text()
            except Exception as e:
                self._logger.error(
                    "load_summary_error",
                    channel_id=channel_id,
                    error=str(e),
                )

        self._cache[channel_id] = context
        return context

    def _parse_history(self, content: str) -> list[ConversationTurn]:
        """Parse history from markdown content."""
        history = []
        lines = content.split("\n")

        current_role = None
        current_content = []
        current_timestamp = None

        for line in lines:
            # Check for role headers
            if line.startswith("## User"):
                if current_role and current_content:
                    history.append(
                        ConversationTurn(
                            role=current_role,
                            content="\n".join(current_content).strip(),
                            timestamp=current_timestamp or datetime.now(UTC),
                        )
                    )
                current_role = "user"
                current_content = []
                # Try to parse timestamp
                if " - " in line:
                    try:
                        ts_str = line.split(" - ")[1]
                        current_timestamp = datetime.fromisoformat(ts_str)
                    except (ValueError, IndexError):
                        current_timestamp = datetime.now(UTC)

            elif line.startswith("## Assistant"):
                if current_role and current_content:
                    history.append(
                        ConversationTurn(
                            role=current_role,
                            content="\n".join(current_content).strip(),
                            timestamp=current_timestamp or datetime.now(UTC),
                        )
                    )
                current_role = "assistant"
                current_content = []
                if " - " in line:
                    try:
                        ts_str = line.split(" - ")[1]
                        current_timestamp = datetime.fromisoformat(ts_str)
                    except (ValueError, IndexError):
                        current_timestamp = datetime.now(UTC)

            elif current_role:
                current_content.append(line)

        # Add last entry
        if current_role and current_content:
            history.append(
                ConversationTurn(
                    role=current_role,
                    content="\n".join(current_content).strip(),
                    timestamp=current_timestamp or datetime.now(UTC),
                )
            )

        return history

    def _format_history(self, history: list[ConversationTurn]) -> str:
        """Format history as markdown."""
        lines = ["# Conversation History\n"]

        for turn in history:
            role_name = "User" if turn.role == "user" else "Assistant"
            timestamp = turn.timestamp.isoformat()
            lines.append(f"## {role_name} - {timestamp}\n")
            lines.append(turn.content)
            lines.append("\n")

        return "\n".join(lines)

    async def save_context(self, context: ChannelContext) -> None:
        """Save context for a channel.

        Args:
            context: Context to save
        """
        history_path = self._get_channel_path(context.channel_id)

        try:
            content = self._format_history(context.history)
            history_path.write_text(content)
            context.total_tokens = count_tokens(content)
            self._cache[context.channel_id] = context

            self._logger.info(
                "context_saved",
                channel_id=context.channel_id,
                turns=len(context.history),
                tokens=context.total_tokens,
            )

        except Exception as e:
            self._logger.error(
                "save_context_error",
                channel_id=context.channel_id,
                error=str(e),
            )
            raise

    async def add_turn(
        self,
        channel_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChannelContext:
        """Add a conversation turn.

        Args:
            channel_id: Channel identifier
            role: Role (user or assistant)
            content: Message content
            metadata: Optional metadata

        Returns:
            Updated context
        """
        context = await self.load_context(channel_id)

        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        context.history.append(turn)

        # Check if we need to trigger summarization
        context.total_tokens = sum(count_tokens(t.content) for t in context.history)

        await self.save_context(context)
        return context

    async def save_summary(self, channel_id: str, summary: str) -> None:
        """Save a summary for a channel.

        Args:
            channel_id: Channel identifier
            summary: Summary text
        """
        summary_path = self._get_summary_path(channel_id)

        try:
            summary_path.write_text(summary)

            if channel_id in self._cache:
                self._cache[channel_id].summary = summary
                self._cache[channel_id].summary_updated_at = datetime.now(UTC)

            self._logger.info(
                "summary_saved",
                channel_id=channel_id,
                length=len(summary),
            )

        except Exception as e:
            self._logger.error(
                "save_summary_error",
                channel_id=channel_id,
                error=str(e),
            )
            raise

    def needs_summarization(self, context: ChannelContext) -> bool:
        """Check if context needs summarization.

        Args:
            context: Channel context

        Returns:
            True if summarization is needed
        """
        return context.total_tokens > self.summary_threshold_tokens

    def get_context_for_agent(
        self,
        context: ChannelContext,
        token_budget: int | None = None,
    ) -> list[dict[str, str]]:
        """Get context formatted for agent.

        Args:
            context: Channel context
            token_budget: Maximum tokens to use

        Returns:
            List of message dicts for agent
        """
        budget = TokenBudget(
            max_tokens=token_budget or self.max_history_tokens,
            reserve_for_response=4096,
        )

        messages = []

        # Add summary if available
        if context.summary:
            summary_msg = f"Previous conversation summary:\n{context.summary}"
            if budget.add(summary_msg):
                messages.append({"role": "system", "content": summary_msg})

        # Add recent history (most recent first, then reverse)
        recent_history = []
        for turn in reversed(context.history):
            if budget.fits(turn.content):
                budget.add(turn.content)
                recent_history.append({"role": turn.role, "content": turn.content})
            else:
                break

        # Reverse to get chronological order
        recent_history.reverse()
        messages.extend(recent_history)

        return messages

    async def clear_context(self, channel_id: str) -> bool:
        """Clear context for a channel.

        Args:
            channel_id: Channel identifier

        Returns:
            True if cleared successfully
        """
        try:
            history_path = self._get_channel_path(channel_id)
            summary_path = self._get_summary_path(channel_id)

            if history_path.exists():
                history_path.unlink()

            if summary_path.exists():
                summary_path.unlink()

            if channel_id in self._cache:
                del self._cache[channel_id]

            self._logger.info("context_cleared", channel_id=channel_id)
            return True

        except Exception as e:
            self._logger.error(
                "clear_context_error",
                channel_id=channel_id,
                error=str(e),
            )
            return False

    def list_channels(self) -> list[str]:
        """List all channels with stored context.

        Returns:
            List of channel IDs
        """
        channels = set()

        for path in self.memory_path.glob("*.md"):
            name = path.stem
            if name.endswith("_summary"):
                name = name[:-8]  # Remove _summary suffix
            channels.add(name)

        return list(channels)


# Global context store instance
_context_store: ContextStore | None = None


def get_context_store() -> ContextStore:
    """Get the global context store instance."""
    global _context_store
    if _context_store is None:
        _context_store = ContextStore()
    return _context_store


def set_context_store(store: ContextStore) -> None:
    """Set the global context store instance."""
    global _context_store
    _context_store = store
