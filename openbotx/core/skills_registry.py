"""Skills registry for OpenBotX - index and manage skills from .md files."""

import re
from pathlib import Path
from typing import Any

import yaml

from openbotx.helpers.logger import get_logger
from openbotx.models.skill import SkillDefinition, SkillSecurity, SkillTrigger


class SkillsRegistry:
    """Registry for managing skills from markdown files."""

    def __init__(self, skills_path: str = "./skills") -> None:
        """Initialize skills registry.

        Args:
            skills_path: Path to user skills directory
        """
        self.skills_path = Path(skills_path)
        self._skills: dict[str, SkillDefinition] = {}
        self._logger = get_logger("skills_registry")

        # Path to built-in/native skills (inside openbotx package)
        self._native_skills_path = Path(__file__).parent.parent / "skills"

        # Ensure user directory exists
        self.skills_path.mkdir(parents=True, exist_ok=True)

    async def load_skills(self) -> int:
        """Load all skills from native and user directories.

        Native skills are loaded first, then user skills can override them.

        Returns:
            Number of skills loaded
        """
        self._skills.clear()
        count = 0

        # Load native/built-in skills first
        if self._native_skills_path.exists():
            native_count = await self._load_skills_from_path(
                self._native_skills_path,
                source="native",
            )
            count += native_count

        # Load user skills (can override native skills)
        user_count = await self._load_skills_from_path(
            self.skills_path,
            source="user",
        )
        count += user_count

        self._logger.info("skills_loaded", count=count)
        return count

    async def _load_skills_from_path(
        self,
        path: Path,
        source: str = "user",
    ) -> int:
        """Load skills from a specific path.

        Args:
            path: Path to scan for skills
            source: Source identifier (native/user)

        Returns:
            Number of skills loaded from this path
        """
        count = 0

        # Find all SKILL.md files (case insensitive)
        for skill_file in path.rglob("*"):
            if skill_file.is_file() and skill_file.name.lower() in (
                "skill.md",
                "skill.yaml",
                "skill.yml",
            ):
                try:
                    skill = await self._load_skill_file(skill_file)
                    if skill:
                        # Check if overriding native skill
                        is_override = skill.id in self._skills and source == "user"

                        self._skills[skill.id] = skill
                        count += 1

                        self._logger.info(
                            "skill_loaded",
                            skill_id=skill.id,
                            name=skill.name,
                            path=str(skill_file),
                            source=source,
                            override=is_override,
                        )
                except Exception as e:
                    self._logger.error(
                        "skill_load_error",
                        path=str(skill_file),
                        error=str(e),
                    )

        return count

    async def _load_skill_file(self, path: Path) -> SkillDefinition | None:
        """Load a skill from a file.

        Args:
            path: Path to skill file

        Returns:
            SkillDefinition or None
        """
        content = path.read_text()

        # Check if it's a YAML file or Markdown with frontmatter
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
            return self._parse_skill_data(data, path)

        # Parse Markdown with YAML frontmatter
        return self._parse_markdown_skill(content, path)

    def _parse_markdown_skill(
        self,
        content: str,
        path: Path,
    ) -> SkillDefinition | None:
        """Parse a markdown skill file with YAML frontmatter.

        Args:
            content: File content
            path: File path

        Returns:
            SkillDefinition or None
        """
        # Extract YAML frontmatter
        frontmatter_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n(.*)$",
            content,
            re.DOTALL,
        )

        if not frontmatter_match:
            self._logger.warning(
                "no_frontmatter",
                path=str(path),
            )
            return None

        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
            body = frontmatter_match.group(2)
        except yaml.YAMLError as e:
            self._logger.error(
                "frontmatter_parse_error",
                path=str(path),
                error=str(e),
            )
            return None

        # Parse body for additional sections
        sections = self._parse_markdown_sections(body)

        # Merge frontmatter with sections
        data = {**frontmatter}

        if "steps" not in data and "Steps" in sections:
            data["steps"] = self._parse_list_section(sections["Steps"])

        if "examples" not in data and "Examples" in sections:
            data["examples"] = self._parse_list_section(sections["Examples"])

        if "guidelines" not in data and "Guidelines" in sections:
            data["guidelines"] = self._parse_list_section(sections["Guidelines"])

        return self._parse_skill_data(data, path, body)

    def _parse_markdown_sections(self, content: str) -> dict[str, str]:
        """Parse markdown sections from content.

        Args:
            content: Markdown content

        Returns:
            Dict of section name to content
        """
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_list_section(self, content: str) -> list[str]:
        """Parse a list from markdown content.

        Args:
            content: Section content

        Returns:
            List of items
        """
        items = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
            elif re.match(r"^\d+\.\s+", line):
                items.append(re.sub(r"^\d+\.\s+", "", line).strip())
        return items

    def _parse_skill_data(
        self,
        data: dict[str, Any],
        path: Path,
        body: str = "",
    ) -> SkillDefinition:
        """Parse skill data into SkillDefinition.

        Args:
            data: Parsed data
            path: File path
            body: Markdown body content

        Returns:
            SkillDefinition
        """
        # Generate ID from name if not provided
        skill_id = data.get("id") or data.get("name", path.parent.name)
        skill_id = skill_id.lower().replace(" ", "-")

        # Parse triggers
        triggers_data = data.get("triggers", {})
        if isinstance(triggers_data, list):
            triggers = SkillTrigger(keywords=triggers_data)
        else:
            triggers = SkillTrigger(
                keywords=triggers_data.get("keywords", []),
                patterns=triggers_data.get("patterns", []),
                intents=triggers_data.get("intents", []),
            )

        # Parse security
        security_data = data.get("security", {})
        security = SkillSecurity(
            approval_required=security_data.get("approval_required", False),
            admin_only=security_data.get("admin_only", False),
            allowed_channels=security_data.get("allowed_channels", []),
            denied_channels=security_data.get("denied_channels", []),
        )

        return SkillDefinition(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            triggers=triggers,
            required_providers=data.get("required_providers", []),
            tools=data.get("tools", []),
            security=security,
            steps=data.get("steps", []),
            examples=data.get("examples", []),
            guidelines=data.get("guidelines", []),
            content=body,
            file_path=str(path),
            metadata=data.get("metadata", {}),
        )

    def get(self, skill_id: str) -> SkillDefinition | None:
        """Get a skill by ID.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillDefinition or None
        """
        return self._skills.get(skill_id)

    def list_skills(self) -> list[SkillDefinition]:
        """List all registered skills.

        Returns:
            List of skills
        """
        return list(self._skills.values())

    def find_matching_skills(
        self,
        text: str,
        limit: int = 5,
    ) -> list[SkillDefinition]:
        """Find skills matching input text.

        Args:
            text: Input text to match
            limit: Maximum number of skills to return

        Returns:
            List of matching skills
        """
        matches = []

        for skill in self._skills.values():
            if skill.matches_input(text):
                matches.append(skill)
                if len(matches) >= limit:
                    break

        return matches

    async def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        triggers: list[str] | None = None,
        tools: list[str] | None = None,
        steps: list[str] | None = None,
        guidelines: list[str] | None = None,
    ) -> SkillDefinition:
        """Create a new skill.

        This is used by the "learn mode" to create new skills.

        Args:
            skill_id: Unique skill ID
            name: Skill name
            description: Skill description
            triggers: Trigger keywords
            tools: Tools used by skill
            steps: Execution steps
            guidelines: Usage guidelines

        Returns:
            Created SkillDefinition
        """
        # Create skill directory
        skill_dir = self.skills_path / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Build YAML frontmatter
        frontmatter = {
            "name": name,
            "description": description,
            "version": "1.0.0",
            "triggers": triggers or [],
            "tools": tools or [],
        }

        # Build content
        content_parts = [
            "---",
            yaml.dump(frontmatter, default_flow_style=False).strip(),
            "---",
            "",
            f"# {name}",
            "",
            "## Overview",
            description,
            "",
        ]

        if steps:
            content_parts.extend(["## Steps", ""])
            for i, step in enumerate(steps, 1):
                content_parts.append(f"{i}. {step}")
            content_parts.append("")

        if guidelines:
            content_parts.extend(["## Guidelines", ""])
            for guideline in guidelines:
                content_parts.append(f"- {guideline}")
            content_parts.append("")

        # Write skill file
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("\n".join(content_parts))

        # Load and register the skill
        skill = await self._load_skill_file(skill_file)
        if skill:
            self._skills[skill.id] = skill
            self._logger.info(
                "skill_created",
                skill_id=skill.id,
                name=skill.name,
                path=str(skill_file),
            )
            return skill

        raise RuntimeError(f"Failed to create skill: {skill_id}")

    def reload(self) -> None:
        """Reload all skills."""
        import asyncio

        asyncio.create_task(self.load_skills())

    @property
    def skill_count(self) -> int:
        """Get number of registered skills."""
        return len(self._skills)


# Global skills registry instance
_skills_registry: SkillsRegistry | None = None


def get_skills_registry() -> SkillsRegistry:
    """Get the global skills registry instance."""
    global _skills_registry
    if _skills_registry is None:
        _skills_registry = SkillsRegistry()
    return _skills_registry


def set_skills_registry(registry: SkillsRegistry) -> None:
    """Set the global skills registry instance."""
    global _skills_registry
    _skills_registry = registry
