"""Conversation summarizer agent for OpenBotX.

Implements dual-summary pattern:
- user_summary: Brief summary about the user (who they are, what they want)
- conversation_summary: Brief summary of conversation context and topics
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from openbotx.helpers.config import get_config
from openbotx.helpers.logger import get_logger

logger = get_logger("summarizer")


class ConversationSummary(BaseModel):
    """Dual summary of user profile and conversation context."""

    user_summary: str = Field(
        default="",
        description="Brief summary about the user (who they are, what they want).",
    )

    conversation_summary: str = Field(
        default="",
        description="Brief summary of the conversation context and main topics.",
    )


class MemoryContext(BaseModel):
    """Memory context for prompts with user data and summaries."""

    user_name: str | None = None
    user_email: str | None = None
    user_phone: str | None = None
    user_summary: str | None = None
    conversation_summary: str | None = None
    recent_observations: list[dict[str, str]] = Field(default_factory=list)
    observation_count: int = 0
    last_summarized_count: int = 0


SUMMARIZATION_SYSTEM_PROMPT = """You are a CONVERSATION SUMMARIZATION agent.

Your function is to create a SHORT and USEFUL summary about the user and the conversation.

RULES:
1. Be concise and objective
2. DO NOT invent data
3. Use only information present in the provided text
4. DO NOT explain or comment
5. DO NOT write text outside the JSON
6. Maximum 2-3 sentences per summary

Create two summaries:
- user_summary: who is the user, what they want, main interest
- conversation_summary: conversation context, main topics discussed

Return ONLY a valid JSON according to the provided schema."""


class ConversationSummarizer:
    """Agent responsible for summarizing conversations.

    Uses dual summaries:
    - user_summary: Profile and intent of the user
    - conversation_summary: Context and topics discussed
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str = "openai",
    ) -> None:
        """Initialize summarizer.

        Args:
            api_key: LLM API key
            model: Model to use
            provider: LLM provider (openai, anthropic)
        """
        config = get_config().llm
        self.api_key = api_key or config.api_key
        self.model = model or config.model
        self.provider = provider or config.provider
        self._agent: Agent | None = None

    def _build_agent(self) -> Agent:
        """Build PydanticAI agent for summarization."""
        from openbotx.helpers.llm_model import create_pydantic_model

        # Use a smaller/faster model for summarization if available
        pydantic_model = create_pydantic_model(get_config().llm)

        return Agent(
            model=pydantic_model,
            output_type=ConversationSummary,
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
        )

    def get_agent(self) -> Agent:
        """Get or create the summarization agent."""
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    async def summarize(
        self,
        messages: list[dict[str, str]],
        existing_user_summary: str | None = None,
        existing_conversation_summary: str | None = None,
    ) -> ConversationSummary:
        """Create summary from conversation messages.

        Args:
            messages: List of message dicts with role and content
            existing_user_summary: Previous user summary to incorporate
            existing_conversation_summary: Previous conversation summary

        Returns:
            ConversationSummary with user_summary and conversation_summary
        """
        agent = self.get_agent()

        # Build input text
        parts = []

        if existing_user_summary:
            parts.append(f"Previous user summary: {existing_user_summary}")

        if existing_conversation_summary:
            parts.append(f"Previous conversation summary: {existing_conversation_summary}")

        parts.append("\nConversation to summarize:")

        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")

        input_text = "\n".join(parts)

        try:
            result = await agent.run(input_text)
            return result.output
        except Exception as e:
            logger.error("summarization_error", error=str(e))
            return ConversationSummary()

    async def summarize_observations(
        self,
        observations: list[dict[str, str]],
        existing_user_summary: str | None = None,
    ) -> ConversationSummary:
        """Create summary from observation list.

        Args:
            observations: List of observation dicts with type and text
            existing_user_summary: Previous user summary

        Returns:
            ConversationSummary
        """
        agent = self.get_agent()

        # Format observations as text
        lines = []
        if existing_user_summary:
            lines.append(f"Previous summary: {existing_user_summary}")

        lines.append("\nObservations:")
        for obs in observations:
            obs_type = obs.get("type", "general")
            obs_text = obs.get("text", "")
            lines.append(f"{obs_type}: {obs_text}")

        input_text = "\n".join(lines)

        try:
            result = await agent.run(input_text)
            return result.output
        except Exception as e:
            logger.error("summarization_error", error=str(e))
            return ConversationSummary()


def format_memory_context(
    memory: MemoryContext,
    max_recent_observations: int = 10,
) -> str:
    """Format memory context for use in prompts.

    Args:
        memory: Memory context with user data and summaries
        max_recent_observations: Number of recent observations to include

    Returns:
        Formatted context string
    """
    lines = []

    # Add user data section
    user_data = []
    if memory.user_name:
        user_data.append(f"Name: {memory.user_name}")
    if memory.user_email:
        user_data.append(f"Email: {memory.user_email}")
    if memory.user_phone:
        user_data.append(f"Phone: {memory.user_phone}")

    if user_data:
        lines.append("USER DATA:")
        lines.extend(user_data)
        lines.append("")

    # Add summaries
    if memory.user_summary:
        lines.append(f"USER PROFILE: {memory.user_summary}")

    if memory.conversation_summary:
        lines.append(f"CONVERSATION CONTEXT: {memory.conversation_summary}")

    # Add recent observations
    if memory.recent_observations:
        recent = memory.recent_observations[-max_recent_observations:]
        if recent:
            lines.append("\nRECENT OBSERVATIONS:")
            for obs in recent:
                obs_type = obs.get("type", "general")
                obs_text = obs.get("text", "")
                lines.append(f"- [{obs_type}] {obs_text}")

    return "\n".join(lines)


# Global summarizer instance
_summarizer: ConversationSummarizer | None = None


def get_summarizer() -> ConversationSummarizer:
    """Get the global summarizer instance."""
    global _summarizer
    if _summarizer is None:
        _summarizer = ConversationSummarizer()
    return _summarizer


def set_summarizer(summarizer: ConversationSummarizer) -> None:
    """Set the global summarizer instance."""
    global _summarizer
    _summarizer = summarizer
