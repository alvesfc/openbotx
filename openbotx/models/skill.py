"""Skill models for OpenBotX."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SkillTrigger(BaseModel):
    """Trigger definition for a skill."""

    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)


class SkillSecurity(BaseModel):
    """Security settings for a skill."""

    approval_required: bool = False
    admin_only: bool = False
    allowed_channels: list[str] = Field(default_factory=list)
    denied_channels: list[str] = Field(default_factory=list)


class SkillDefinition(BaseModel):
    """Skill definition parsed from SKILL.md files."""

    id: str
    name: str
    description: str
    version: str = "1.0.0"
    triggers: SkillTrigger = Field(default_factory=SkillTrigger)
    required_providers: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    security: SkillSecurity = Field(default_factory=SkillSecurity)
    steps: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    guidelines: list[str] = Field(default_factory=list)
    content: str = ""
    file_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def matches_input(self, text: str) -> bool:
        """Check if skill matches given input text."""
        text_lower = text.lower()

        # Check keywords
        for keyword in self.triggers.keywords:
            if keyword.lower() in text_lower:
                return True

        # Check patterns (simple contains for now)
        for pattern in self.triggers.patterns:
            if pattern.lower() in text_lower:
                return True

        return False

    def get_context(self) -> str:
        """Get skill context for agent prompt."""
        lines = [
            f"# Skill: {self.name}",
            f"Description: {self.description}",
        ]

        if self.steps:
            lines.append("\n## Steps:")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"{i}. {step}")

        if self.guidelines:
            lines.append("\n## Guidelines:")
            for guideline in self.guidelines:
                lines.append(f"- {guideline}")

        if self.examples:
            lines.append("\n## Examples:")
            for example in self.examples:
                lines.append(f"- {example}")

        return "\n".join(lines)


class SkillExecutionRequest(BaseModel):
    """Request to execute a skill."""

    skill_id: str
    input_text: str
    channel_id: str
    user_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SkillExecutionResult(BaseModel):
    """Result of skill execution."""

    skill_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    tools_called: list[str] = Field(default_factory=list)
    execution_time_ms: int = 0
