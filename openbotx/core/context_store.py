"""Context store for OpenBotX - memory management using .md files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.helpers.tokens import TokenBudget, count_tokens
from openbotx.models.enums import CompactionStrategy

if TYPE_CHECKING:
    from openbotx.core.compaction import MessageCompactor


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
    user_summary: str | None = None
    conversation_summary: str | None = None
    summary_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int = 0
    observations: list[dict[str, str]] = Field(default_factory=list)
    last_observation_count: int = 0

    def get_combined_summary(self) -> str | None:
        """Get combined summary (user profile + conversation context)."""
        if self.user_summary or self.conversation_summary:
            parts = []
            if self.user_summary:
                parts.append(f"USER PROFILE: {self.user_summary}")
            if self.conversation_summary:
                parts.append(f"CONTEXT: {self.conversation_summary}")
            return "\n".join(parts)
        return self.summary


class ContextStore:
    """Store and manage conversation context using markdown files."""

    def __init__(
        self,
        memory_path: str = "./memory",
        max_history_tokens: int = 50000,
        summary_threshold_tokens: int = 30000,
        compaction_strategy: CompactionStrategy = CompactionStrategy.ADAPTIVE,
    ) -> None:
        """Initialize context store.

        Args:
            memory_path: Path to memory directory
            max_history_tokens: Maximum tokens in history
            summary_threshold_tokens: Token count to trigger summarization
            compaction_strategy: Strategy for compacting messages
        """
        self.memory_path = Path(memory_path)
        self.max_history_tokens = max_history_tokens
        self.summary_threshold_tokens = summary_threshold_tokens
        self.compaction_strategy = compaction_strategy
        self._logger = get_logger("context_store")
        self._cache: dict[str, ChannelContext] = {}
        self._compactor: MessageCompactor | None = None

        # Ensure directory exists
        self.memory_path.mkdir(parents=True, exist_ok=True)

    @property
    def compactor(self) -> MessageCompactor:
        """Get or create compactor instance."""
        if self._compactor is None:
            from openbotx.core.compaction import CompactionConfig, MessageCompactor

            config = CompactionConfig(
                strategy=self.compaction_strategy,
                max_context_tokens=self.max_history_tokens,
            )
            self._compactor = MessageCompactor(config)
        return self._compactor

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

        # Load summary (JSON only: user_summary + conversation_summary)
        summary_path = self._get_summary_path(channel_id)
        if summary_path.exists():
            try:
                import json

                content = summary_path.read_text()
                data = json.loads(content)
                if isinstance(data, dict):
                    context.user_summary = data.get("user_summary")
                    context.conversation_summary = data.get("conversation_summary")
                    context.summary = context.get_combined_summary()
                else:
                    self._logger.warning(
                        "load_summary_invalid_format",
                        channel_id=channel_id,
                    )
            except json.JSONDecodeError:
                self._logger.warning(
                    "load_summary_not_json",
                    channel_id=channel_id,
                )
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

    async def save_summary(
        self,
        channel_id: str,
        user_summary: str | None,
        conversation_summary: str | None,
    ) -> None:
        """Save summary for a channel (JSON: user_summary + conversation_summary).

        Args:
            channel_id: Channel identifier
            user_summary: Summary about the user
            conversation_summary: Summary of conversation topics
        """
        import json

        summary_path = self._get_summary_path(channel_id)

        try:
            # Save as JSON for structured data
            data = {
                "user_summary": user_summary,
                "conversation_summary": conversation_summary,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            summary_path.write_text(json.dumps(data, indent=2))

            if channel_id in self._cache:
                self._cache[channel_id].user_summary = user_summary
                self._cache[channel_id].conversation_summary = conversation_summary
                self._cache[channel_id].summary = self._cache[channel_id].get_combined_summary()
                self._cache[channel_id].summary_updated_at = datetime.now(UTC)

            self._logger.info(
                "summary_saved",
                channel_id=channel_id,
                has_user_summary=bool(user_summary),
                has_conversation_summary=bool(conversation_summary),
            )

        except Exception as e:
            self._logger.error(
                "save_summary_error",
                channel_id=channel_id,
                error=str(e),
            )
            raise

    async def trigger_summarization(self, channel_id: str) -> bool:
        """Trigger summarization for a channel using the summarizer agent.

        Args:
            channel_id: Channel identifier

        Returns:
            True if summarization was performed
        """
        context = await self.load_context(channel_id)

        if not self.needs_summarization(context):
            return False

        try:
            from openbotx.agent.summarizer import get_summarizer

            summarizer = get_summarizer()

            # Convert history to message format
            messages = [{"role": t.role, "content": t.content} for t in context.history]

            # Summarize with existing summaries as context
            result = await summarizer.summarize(
                messages=messages,
                existing_user_summary=context.user_summary,
                existing_conversation_summary=context.conversation_summary,
            )

            await self.save_summary(
                channel_id=channel_id,
                user_summary=result.user_summary,
                conversation_summary=result.conversation_summary,
            )

            self._logger.info(
                "summarization_completed",
                channel_id=channel_id,
            )

            return True

        except Exception as e:
            self._logger.error(
                "summarization_error",
                channel_id=channel_id,
                error=str(e),
            )
            return False

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

        # Add dual summaries if available
        summary_parts = []
        if context.user_summary:
            summary_parts.append(f"USER PROFILE: {context.user_summary}")
        if context.conversation_summary:
            summary_parts.append(f"CONVERSATION CONTEXT: {context.conversation_summary}")

        if summary_parts:
            summary_msg = "\n".join(summary_parts)
            if budget.add(summary_msg):
                messages.append({"role": "system", "content": summary_msg})
        elif context.summary:
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

    def get_compacted_context(
        self,
        context: ChannelContext,
        token_budget: int | None = None,
    ) -> tuple[list[dict[str, str]], str | None, bool]:
        """Get compacted context for agent using the configured compaction strategy.

        Args:
            context: Channel context
            token_budget: Maximum tokens to use

        Returns:
            Tuple of (messages, updated_summary, needs_summarization)
        """
        budget = token_budget or self.max_history_tokens

        # Convert history to message dicts
        messages = [{"role": t.role, "content": t.content} for t in context.history]

        # Check if compaction is needed
        if not self.compactor.needs_compaction(messages, budget):
            return messages, context.summary, False

        # Compact messages
        result = self.compactor.compact(messages, budget, context.summary)

        self._logger.info(
            "context_compacted",
            channel_id=context.channel_id,
            tokens_before=result.tokens_before,
            tokens_after=result.tokens_after,
            messages_removed=result.messages_removed,
        )

        return result.messages, result.summary, result.summary_updated

    def get_summarization_prompt(self, context: ChannelContext) -> str | None:
        """Get a prompt for LLM summarization if needed.

        Args:
            context: Channel context

        Returns:
            Summarization prompt or None if not needed
        """
        if not self.needs_summarization(context):
            return None

        from openbotx.core.compaction import create_summarization_prompt

        messages = [{"role": t.role, "content": t.content} for t in context.history]

        return create_summarization_prompt(messages, context.summary)

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
