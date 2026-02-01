"""Skill generation for OpenBotX.

Provides LLM-based skill generation capabilities for the "learn mode".
"""

from dataclasses import dataclass, field
from typing import Any

import yaml

from openbotx.helpers.logger import get_logger
from openbotx.models.skill import SkillDefinition

logger = get_logger("skill_generator")


SKILL_GENERATION_PROMPT = """Create a skill definition for the following topic: {topic}

You are creating a skill that will help an AI assistant. The skill should be practical and reusable.

Provide a structured response in the following YAML format:

```yaml
name: <short skill name>
description: <brief description of what the skill does>
triggers:
  - <keyword1>
  - <keyword2>
  - <keyword3>
steps:
  - <step 1>
  - <step 2>
  - <step 3>
guidelines:
  - <guideline 1>
  - <guideline 2>
examples:
  - <example usage 1>
  - <example usage 2>
tools:
  - <tool name if needed>
```

Context about the request:
{context}

Generate a complete and useful skill definition."""


@dataclass
class SkillGenerationRequest:
    """Request to generate a new skill."""

    topic: str
    context: str = ""
    channel_id: str | None = None
    user_id: str | None = None
    examples: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)


@dataclass
class SkillGenerationResult:
    """Result of skill generation."""

    success: bool
    skill: SkillDefinition | None = None
    error: str | None = None
    raw_response: str | None = None


class SkillGenerator:
    """Generates skills using LLM."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        provider: str = "anthropic",
    ) -> None:
        """Initialize skill generator.

        Args:
            api_key: API key for LLM provider
            model: Model to use for generation
            provider: LLM provider (anthropic, openai)
        """
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self._logger = get_logger("skill_generator")

    async def generate(self, request: SkillGenerationRequest) -> SkillGenerationResult:
        """Generate a skill from a request.

        Args:
            request: Skill generation request

        Returns:
            Skill generation result
        """
        if not self.api_key:
            return SkillGenerationResult(
                success=False,
                error="API key not configured for skill generation",
            )

        try:
            # Build context for the prompt
            context_parts = []
            if request.context:
                context_parts.append(f"User context: {request.context}")
            if request.examples:
                context_parts.append(f"Examples: {', '.join(request.examples)}")
            if request.required_tools:
                context_parts.append(f"Required tools: {', '.join(request.required_tools)}")

            context = "\n".join(context_parts) if context_parts else "No additional context."

            # Generate prompt
            prompt = SKILL_GENERATION_PROMPT.format(
                topic=request.topic,
                context=context,
            )

            # Call LLM
            raw_response = await self._call_llm(prompt)

            # Parse response
            skill_data = self._parse_response(raw_response)
            if not skill_data:
                return SkillGenerationResult(
                    success=False,
                    error="Failed to parse LLM response",
                    raw_response=raw_response,
                )

            # Create skill definition
            skill_id = skill_data.get("name", request.topic).lower().replace(" ", "-")

            skill = SkillDefinition(
                id=skill_id,
                name=skill_data.get("name", request.topic),
                description=skill_data.get("description", f"Skill for {request.topic}"),
                triggers=self._parse_triggers(skill_data.get("triggers", [request.topic.lower()])),
                steps=skill_data.get("steps", []),
                guidelines=skill_data.get("guidelines", []),
                examples=skill_data.get("examples", []),
                tools=skill_data.get("tools", request.required_tools),
            )

            self._logger.info(
                "skill_generated",
                skill_id=skill.id,
                name=skill.name,
                topic=request.topic,
            )

            return SkillGenerationResult(
                success=True,
                skill=skill,
                raw_response=raw_response,
            )

        except Exception as e:
            self._logger.error(
                "skill_generation_error",
                topic=request.topic,
                error=str(e),
            )
            return SkillGenerationResult(
                success=False,
                error=str(e),
            )

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM to generate skill content.

        Args:
            prompt: Generation prompt

        Returns:
            Raw response text
        """
        if self.provider == "anthropic":
            return await self._call_anthropic(prompt)
        elif self.provider == "openai":
            return await self._call_openai(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API.

        Args:
            prompt: Generation prompt

        Returns:
            Response text
        """
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key)

        response = await client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        return text

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API.

        Args:
            prompt: Generation prompt

        Returns:
            Response text
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)

        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content or ""

    def _parse_response(self, response: str) -> dict[str, Any] | None:
        """Parse LLM response to extract skill data.

        Args:
            response: Raw response text

        Returns:
            Parsed skill data or None
        """
        # Try to extract YAML block
        import re

        yaml_match = re.search(r"```yaml\s*(.*?)\s*```", response, re.DOTALL)
        if yaml_match:
            try:
                return yaml.safe_load(yaml_match.group(1))
            except yaml.YAMLError:
                pass

        # Try to parse the whole response as YAML
        try:
            return yaml.safe_load(response)
        except yaml.YAMLError:
            pass

        # Try to extract key-value pairs
        data: dict[str, Any] = {}
        lines = response.split("\n")
        current_key = None
        current_list: list[str] = []

        for line in lines:
            line = line.strip()
            if line.endswith(":") and not line.startswith("-"):
                if current_key and current_list:
                    data[current_key] = current_list
                current_key = line[:-1].lower()
                current_list = []
            elif line.startswith("- ") and current_key:
                current_list.append(line[2:])
            elif line.startswith("NAME:"):
                data["name"] = line[5:].strip()
            elif line.startswith("DESCRIPTION:"):
                data["description"] = line[12:].strip()

        if current_key and current_list:
            data[current_key] = current_list

        return data if data else None

    def _parse_triggers(self, triggers: list[str] | dict[str, Any]) -> Any:
        """Parse triggers into proper format.

        Args:
            triggers: Raw triggers data

        Returns:
            SkillTrigger object
        """
        from openbotx.models.skill import SkillTrigger

        if isinstance(triggers, list):
            return SkillTrigger(keywords=triggers)
        elif isinstance(triggers, dict):
            return SkillTrigger(
                keywords=triggers.get("keywords", []),
                patterns=triggers.get("patterns", []),
                intents=triggers.get("intents", []),
            )
        return SkillTrigger(keywords=[str(triggers)])


# Global skill generator instance
_skill_generator: SkillGenerator | None = None


def get_skill_generator() -> SkillGenerator:
    """Get the global skill generator instance."""
    global _skill_generator
    if _skill_generator is None:
        _skill_generator = SkillGenerator()
    return _skill_generator


def set_skill_generator(generator: SkillGenerator) -> None:
    """Set the global skill generator instance."""
    global _skill_generator
    _skill_generator = generator
