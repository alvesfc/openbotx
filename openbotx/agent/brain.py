"""Agent brain for OpenBotX using PydanticAI."""

from typing import Any

from pydantic_ai import Agent

from openbotx.agent.prompts import (
    build_memory_context,
    build_system_prompt,
    format_skills_for_prompt,
    format_tools_for_prompt,
)
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

        # Create agent with model and settings
        self._agent = Agent(
            model=pydantic_model,
            system_prompt=build_system_prompt(),
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

        Args:
            context: Message context
            matching_skills: Skills that match the request

        Returns:
            Context prompt string
        """
        parts = []

        # Add memory context
        if context.history or context.summary:
            memory_context = build_memory_context(
                summary=context.summary,
                history=context.history,
            )
            parts.append(memory_context)

        # Add skills context
        if matching_skills:
            skills_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "triggers": s.triggers.keywords,
                }
                for s in matching_skills
            ]
            skills_context = format_skills_for_prompt(skills_data)
            parts.append(f"## Relevant Skills\n\n{skills_context}")

            # Add detailed skill content
            for skill in matching_skills:
                if skill.content:
                    parts.append(f"### Skill: {skill.name}\n\n{skill.get_context()}")

        # Add available tools
        if context.available_tools:
            tools_data = [{"name": t, "description": ""} for t in context.available_tools]
            if self._tools_registry:
                tools_data = []
                for name in context.available_tools:
                    tool = self._tools_registry.get(name)
                    if tool:
                        tools_data.append(
                            {
                                "name": tool.definition.name,
                                "description": tool.definition.description,
                            }
                        )
            tools_context = format_tools_for_prompt(tools_data)
            parts.append(f"## Available Tools\n\n{tools_context}")

        return "\n\n".join(parts)

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
        """Learn and create a new skill.

        Args:
            topic: Topic to learn about
            context: Message context

        Returns:
            Created skill or None
        """
        if not self._skills_registry:
            return None

        self._logger.info("learning_skill", topic=topic)

        # Use LLM to generate skill content
        try:
            from anthropic import AsyncAnthropic

            if not self._config.api_key:
                self._logger.warning("learn_skill_no_api_key")
                return None

            client = AsyncAnthropic(api_key=self._config.api_key)

            prompt = f"""Create a skill definition for the following topic: {topic}

            Provide:
            1. A clear, concise name
            2. A description of what the skill does
            3. Step-by-step instructions
            4. Guidelines for when to use it
            5. Example usage

            Format your response as:
            NAME: <skill name>
            DESCRIPTION: <description>
            STEPS:
            - Step 1
            - Step 2
            ...
            GUIDELINES:
            - Guideline 1
            - Guideline 2
            ...
            """

            response = await client.messages.create(
                model=self._config.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            # Extract components
            lines = text.split("\n")
            name = topic
            description = ""
            steps = []
            guidelines = []
            current_section = None

            for line in lines:
                line = line.strip()
                if line.startswith("NAME:"):
                    name = line[5:].strip()
                elif line.startswith("DESCRIPTION:"):
                    description = line[12:].strip()
                elif line.startswith("STEPS:"):
                    current_section = "steps"
                elif line.startswith("GUIDELINES:"):
                    current_section = "guidelines"
                elif line.startswith("- ") and current_section:
                    if current_section == "steps":
                        steps.append(line[2:])
                    elif current_section == "guidelines":
                        guidelines.append(line[2:])

            # Create skill
            skill_id = name.lower().replace(" ", "-")
            skill = await self._skills_registry.create_skill(
                skill_id=skill_id,
                name=name,
                description=description or f"Skill for {topic}",
                triggers=[topic.lower()],
                steps=steps,
                guidelines=guidelines,
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
