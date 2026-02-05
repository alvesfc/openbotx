"""Agent brain for OpenBotX using PydanticAI."""

from typing import Any

from pydantic_ai import Agent

from openbotx.agent.prompt_builder import build_prompt, create_prompt_builder
from openbotx.agent.prompts import get_system_context
from openbotx.core.skills_registry import SkillsRegistry
from openbotx.core.tools_registry import ToolsRegistry
from openbotx.helpers.config import get_config
from openbotx.helpers.logger import get_logger
from openbotx.models.message import InboundMessage, MessageContext
from openbotx.models.response import AgentResponse
from openbotx.models.skill import SkillDefinition


class AgentBrain:
    """Brain for processing messages with PydanticAI."""

    def __init__(
        self,
        skills_registry: SkillsRegistry | None = None,
        tools_registry: ToolsRegistry | None = None,
    ) -> None:
        """Initialize agent brain.

        Args:
            skills_registry: Skills registry
            tools_registry: Tools registry
        """
        self._skills_registry = skills_registry
        self._tools_registry = tools_registry
        self._config = get_config().llm
        self._logger = get_logger("agent_brain")
        self._agent: Any = None

    async def initialize(self) -> None:
        """Initialize the PydanticAI agent."""
        from openbotx.helpers.llm_model import (
            create_model_settings,
            create_pydantic_model,
        )

        # Create PydanticAI model string
        pydantic_model = create_pydantic_model(self._config)

        # Create model settings from config (max_tokens, temperature, etc)
        model_settings = create_model_settings(self._config)

        # Build tool functions from registry
        tools = []
        if self._tools_registry:
            for tool_def in self._tools_registry.list_tools():
                tool = self._tools_registry.get(tool_def.name)
                if tool and tool.callable:
                    tools.append(tool.callable)

        # Build base system prompt using the prompt builder
        system_prompt = build_prompt(
            context=get_system_context(),
        )

        # Create agent with model and settings
        self._agent = Agent(
            model=pydantic_model,
            system_prompt=system_prompt,
            tools=tools,
            model_settings=model_settings,
        )

        self._logger.info(
            "agent_initialized",
            model=f"{self._config.provider}:{self._config.model}",
            tools_count=len(tools),
            settings=model_settings,
        )

    def _build_context_prompt(
        self,
        context: MessageContext,
        matching_skills: list[SkillDefinition],
    ) -> str:
        """Build context prompt for the agent.

        Uses the modular prompt builder with directive awareness.
        Supports dual summaries (user profile + conversation context).

        Args:
            context: Message context
            matching_skills: Skills that match the request

        Returns:
            Context prompt string
        """
        builder = create_prompt_builder()

        # Set prompt mode from context
        builder.with_mode(context.prompt_mode)

        # Add system context
        builder.set_context(get_system_context())

        # Add memory context if available (single format: user_summary + conversation_summary from JSON)
        if context.history or context.summary:
            builder.set_memory(
                summary=context.summary,
                history=context.history,
                user_summary=context.user_summary,
                conversation_summary=context.conversation_summary,
            )

        # Add skills context if available - inject full skill content
        if matching_skills:
            skills_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "triggers": s.triggers.keywords if s.triggers else [],
                }
                for s in matching_skills
            ]

            # Get detailed skill content (full SKILL.md content)
            detailed_skills = []
            for skill in matching_skills:
                if skill.content:
                    detailed_skills.append((skill.name, skill.get_context()))

            builder.set_skills(skills_data, detailed_skills if detailed_skills else None)

        # Add available tools
        if context.available_tools:
            tools_data = []
            if self._tools_registry:
                for name in context.available_tools:
                    tool = self._tools_registry.get(name)
                    if tool:
                        tools_data.append(
                            {
                                "name": tool.definition.name,
                                "description": tool.definition.description,
                            }
                        )
            else:
                tools_data = [{"name": t, "description": ""} for t in context.available_tools]

            builder.set_tools(tools_data)

        # Enable reasoning if requested
        if context.show_reasoning:
            builder.enable_reasoning()

        return builder.build()

    def _extract_tool_outputs(self, result: Any) -> AgentResponse:
        """Extract tool outputs and convert to structured AgentResponse.

        Tools return ToolResult objects (guaranteed by type hints).
        We just aggregate the contents into AgentResponse.

        Args:
            result: PydanticAI agent result

        Returns:
            Structured agent response with proper content types
        """
        from pydantic_ai.messages import ToolReturnPart

        from openbotx.models.response import ResponseContent
        from openbotx.models.tool_result import ToolResult

        response = AgentResponse()

        # Get new messages from this run
        new_messages = result.new_messages()

        # Track which tools were called
        tools_called = []

        # Process each message looking for tool returns
        for msg in new_messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        tool_name = part.tool_name
                        tools_called.append(tool_name)

                        # Get the content returned by the tool (guaranteed ToolResult by type hints)
                        content: ToolResult = part.content

                        # Aggregate ToolResult contents into AgentResponse
                        for tool_content in content.contents:
                            response.contents.append(
                                ResponseContent(
                                    type=tool_content.type,
                                    text=tool_content.text,
                                    url=tool_content.url,
                                    path=tool_content.path,
                                    metadata=tool_content.metadata,
                                )
                            )

                        self._logger.info(
                            "tool_result_aggregated",
                            tool=tool_name,
                            success=content.success,
                            contents_count=len(content.contents),
                        )

        # Set tools_called for tracking
        response.tools_called = tools_called

        # Add the final text output from the agent
        if result.output:
            output_text = str(result.output)
            if output_text.strip():
                response.add_text(output_text)

        return response

    async def process(
        self,
        message: InboundMessage,
        context: MessageContext,
    ) -> AgentResponse:
        """Process a message and generate a response.

        Args:
            message: Inbound message
            context: Message context

        Returns:
            Agent response
        """
        self._logger.info(
            "processing_message",
            message_id=message.id,
            channel_id=message.channel_id,
        )

        # Find matching skills
        matching_skills = []
        if self._skills_registry and message.text:
            matching_skills = self._skills_registry.find_matching_skills(
                message.text,
                limit=3,
            )

        # Build context prompt
        context_prompt = self._build_context_prompt(context, matching_skills)

        # Process with PydanticAI agent
        if not self._agent:
            raise RuntimeError("Agent not initialized")

        result = await self._agent.run(
            f"{context_prompt}\n\nUser message: {message.text}",
        )

        # Intelligently extract and structure the response
        return self._extract_tool_outputs(result)

    async def learn_skill(
        self,
        topic: str,
        context: MessageContext,
    ) -> SkillDefinition | None:
        """Learn and create a new skill using the skill generator.

        Args:
            topic: Topic to learn about
            context: Message context

        Returns:
            Created skill or None
        """
        if not self._skills_registry:
            return None

        self._logger.info("learning_skill", topic=topic)

        try:
            from openbotx.core.skill_generator import (
                SkillGenerationRequest,
                SkillGenerator,
            )

            if not self._config.api_key:
                self._logger.warning("learn_skill_no_api_key")
                return None

            generator = SkillGenerator(
                api_key=self._config.api_key,
                model=self._config.model,
                provider=self._config.provider,
                base_url=self._config.base_url,
            )

            # Build context for generation
            context_str = ""
            if context.history:
                recent = context.history[-5:]
                context_str = "\n".join(
                    f"{m.get('role', 'user')}: {m.get('content', '')[:200]}" for m in recent
                )

            # Generate skill
            request = SkillGenerationRequest(
                topic=topic,
                context=context_str,
                channel_id=context.message.channel_id,
                user_id=context.message.user_id,
                required_tools=(context.available_tools[:5] if context.available_tools else []),
            )

            result = await generator.generate(request)

            if not result.success or not result.skill:
                self._logger.warning(
                    "skill_generation_failed",
                    topic=topic,
                    error=result.error,
                )
                return None

            # Save the generated skill
            skill = await self._skills_registry.create_skill(
                skill_id=result.skill.id,
                name=result.skill.name,
                description=result.skill.description,
                triggers=(
                    result.skill.triggers.keywords if result.skill.triggers else [topic.lower()]
                ),
                tools=result.skill.tools,
                steps=result.skill.steps,
                guidelines=result.skill.guidelines,
            )

            self._logger.info(
                "skill_learned",
                skill_id=skill.id,
                name=skill.name,
            )

            return skill

        except Exception as e:
            self._logger.error("learn_skill_error", error=str(e))
            return None


# Global agent brain instance
_agent_brain: AgentBrain | None = None


def get_agent_brain() -> AgentBrain:
    """Get the global agent brain instance."""
    global _agent_brain
    if _agent_brain is None:
        _agent_brain = AgentBrain()
    return _agent_brain


def set_agent_brain(brain: AgentBrain) -> None:
    """Set the global agent brain instance."""
    global _agent_brain
    _agent_brain = brain
