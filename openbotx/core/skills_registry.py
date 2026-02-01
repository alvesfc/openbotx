"""Skills registry for OpenBotX - index and manage skills from .md files.

Implements skill loading with source precedence (extra < bundled < managed < workspace)
and eligibility checks (OS, binaries, config flags).
"""

import platform
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import SkillEligibilityReason, SkillSource
from openbotx.models.skill import (
    SkillDefinition,
    SkillEligibility,
    SkillEligibilityResult,
    SkillSecurity,
    SkillTrigger,
)


class SkillsRegistry:
    """Registry for managing skills from markdown files.

    Skills are loaded with precedence: extra < bundled < managed < workspace.
    Higher precedence sources override lower ones.
    """

    # Source precedence (lower number = lower priority)
    SOURCE_PRECEDENCE: dict[SkillSource, int] = {
        SkillSource.EXTRA: 0,
        SkillSource.BUNDLED: 1,
        SkillSource.MANAGED: 2,
        SkillSource.WORKSPACE: 3,
    }

    def __init__(
        self,
        skills_path: str = "./skills",
        managed_skills_path: str | None = None,
        extra_skills_paths: list[str] | None = None,
        check_eligibility: bool = True,
        available_providers: list[str] | None = None,
        config_flags: dict[str, bool] | None = None,
    ) -> None:
        """Initialize skills registry.

        Args:
            skills_path: Path to workspace skills directory
            managed_skills_path: Path to managed skills directory
            extra_skills_paths: Additional paths for extra skills
            check_eligibility: Whether to check skill eligibility
            available_providers: List of available provider names
            config_flags: Configuration flags for skill eligibility
        """
        self.skills_path = Path(skills_path)
        self.managed_skills_path = Path(managed_skills_path) if managed_skills_path else None
        self.extra_skills_paths = [Path(p) for p in (extra_skills_paths or [])]
        self.check_eligibility = check_eligibility
        self.available_providers = set(available_providers or [])
        self.config_flags = config_flags or {}

        self._skills: dict[str, SkillDefinition] = {}
        self._ineligible_skills: dict[str, SkillEligibilityResult] = {}
        self._logger = get_logger("skills_registry")

        # Path to built-in/bundled skills (inside openbotx package)
        self._bundled_skills_path = Path(__file__).parent.parent / "skills"

        # Ensure workspace directory exists
        self.skills_path.mkdir(parents=True, exist_ok=True)

    async def load_skills(self) -> int:
        """Load all skills with source precedence.

        Loading order (lower to higher precedence):
        1. Extra skills (extra_skills_paths)
        2. Bundled skills (inside openbotx package)
        3. Managed skills (managed_skills_path)
        4. Workspace skills (skills_path)

        Higher precedence sources override lower ones.

        Returns:
            Number of unique skills loaded
        """
        self._skills.clear()
        self._ineligible_skills.clear()

        # Load in order of precedence (lowest first)

        # 1. Extra skills
        for extra_path in self.extra_skills_paths:
            if extra_path.exists():
                await self._load_skills_from_path(
                    extra_path,
                    source=SkillSource.EXTRA,
                )

        # 2. Bundled skills
        if self._bundled_skills_path.exists():
            await self._load_skills_from_path(
                self._bundled_skills_path,
                source=SkillSource.BUNDLED,
            )

        # 3. Managed skills
        if self.managed_skills_path and self.managed_skills_path.exists():
            await self._load_skills_from_path(
                self.managed_skills_path,
                source=SkillSource.MANAGED,
            )

        # 4. Workspace skills (highest precedence)
        if self.skills_path.exists():
            await self._load_skills_from_path(
                self.skills_path,
                source=SkillSource.WORKSPACE,
            )

        self._logger.info(
            "skills_loaded",
            count=len(self._skills),
            ineligible=len(self._ineligible_skills),
        )
        return len(self._skills)

    async def _load_skills_from_path(
        self,
        path: Path,
        source: SkillSource,
    ) -> int:
        """Load skills from a specific path.

        Args:
            path: Path to scan for skills
            source: Source identifier

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
                    skill = await self._load_skill_file(skill_file, source)
                    if skill:
                        # Check eligibility
                        if self.check_eligibility:
                            eligibility = self._check_skill_eligibility(skill)
                            if not eligibility.eligible:
                                self._ineligible_skills[skill.id] = eligibility
                                self._logger.debug(
                                    "skill_ineligible",
                                    skill_id=skill.id,
                                    reason=eligibility.reason.value
                                    if eligibility.reason
                                    else "unknown",
                                    message=eligibility.message,
                                )
                                continue

                        # Check if overriding existing skill
                        existing = self._skills.get(skill.id)
                        if existing:
                            # Only override if new source has higher precedence
                            existing_precedence = self.SOURCE_PRECEDENCE.get(existing.source, 0)
                            new_precedence = self.SOURCE_PRECEDENCE.get(source, 0)

                            if new_precedence < existing_precedence:
                                self._logger.debug(
                                    "skill_override_skipped",
                                    skill_id=skill.id,
                                    existing_source=existing.source.value,
                                    new_source=source.value,
                                )
                                continue

                        self._skills[skill.id] = skill
                        count += 1

                        self._logger.info(
                            "skill_loaded",
                            skill_id=skill.id,
                            name=skill.name,
                            path=str(skill_file),
                            source=source.value,
                            override=existing is not None,
                        )
                except Exception as e:
                    self._logger.error(
                        "skill_load_error",
                        path=str(skill_file),
                        error=str(e),
                    )

        return count

    def _check_skill_eligibility(self, skill: SkillDefinition) -> SkillEligibilityResult:
        """Check if a skill is eligible to run.

        Args:
            skill: Skill to check

        Returns:
            Eligibility result
        """
        eligibility = skill.eligibility

        # Check OS compatibility
        if eligibility.os:
            current_os = platform.system().lower()
            os_aliases = {
                "darwin": ["darwin", "macos", "mac"],
                "linux": ["linux"],
                "windows": ["windows", "win"],
            }
            allowed_os = []
            for os_name in eligibility.os:
                allowed_os.extend(os_aliases.get(os_name.lower(), [os_name.lower()]))

            if current_os not in allowed_os:
                return SkillEligibilityResult(
                    eligible=False,
                    reason=SkillEligibilityReason.OS_INCOMPATIBLE,
                    message=f"Skill requires OS: {', '.join(eligibility.os)} (current: {current_os})",
                )

        # Check required binaries
        for binary in eligibility.binaries:
            if not shutil.which(binary):
                return SkillEligibilityResult(
                    eligible=False,
                    reason=SkillEligibilityReason.MISSING_BINARY,
                    missing_binary=binary,
                    message=f"Required binary not found: {binary}",
                )

        # Check config flags
        for flag in eligibility.config_flags:
            if not self.config_flags.get(flag, False):
                return SkillEligibilityResult(
                    eligible=False,
                    reason=SkillEligibilityReason.CONFIG_DISABLED,
                    message=f"Config flag not enabled: {flag}",
                )

        # Check required providers
        for provider in eligibility.required_providers:
            if provider not in self.available_providers:
                return SkillEligibilityResult(
                    eligible=False,
                    reason=SkillEligibilityReason.MISSING_PROVIDER,
                    missing_provider=provider,
                    message=f"Required provider not available: {provider}",
                )

        return SkillEligibilityResult(eligible=True)

    async def _load_skill_file(
        self,
        path: Path,
        source: SkillSource = SkillSource.WORKSPACE,
    ) -> SkillDefinition | None:
        """Load a skill from a file.

        Args:
            path: Path to skill file
            source: Source of the skill

        Returns:
            SkillDefinition or None
        """
        content = path.read_text()

        # Check if it's a YAML file or Markdown with frontmatter
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
            return self._parse_skill_data(data, path, source=source)

        # Parse Markdown with YAML frontmatter
        return self._parse_markdown_skill(content, path, source=source)

    def _parse_markdown_skill(
        self,
        content: str,
        path: Path,
        source: SkillSource = SkillSource.WORKSPACE,
    ) -> SkillDefinition | None:
        """Parse a markdown skill file with YAML frontmatter.

        Args:
            content: File content
            path: File path
            source: Source of the skill

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

        return self._parse_skill_data(data, path, body, source)

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
        source: SkillSource = SkillSource.WORKSPACE,
    ) -> SkillDefinition:
        """Parse skill data into SkillDefinition.

        Args:
            data: Parsed data
            path: File path
            body: Markdown body content
            source: Source of the skill

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

        # Parse eligibility requirements
        eligibility_data = data.get("eligibility", {})
        eligibility = SkillEligibility(
            os=eligibility_data.get("os", []),
            binaries=eligibility_data.get("binaries", []),
            config_flags=eligibility_data.get("config_flags", []),
            required_providers=eligibility_data.get("required_providers", [])
            or data.get("required_providers", []),
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
            eligibility=eligibility,
            source=source,
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

    def list_by_source(self, source: SkillSource) -> list[SkillDefinition]:
        """List skills from a specific source.

        Args:
            source: Source to filter by

        Returns:
            List of skills from that source
        """
        return [s for s in self._skills.values() if s.source == source]

    def list_ineligible_skills(self) -> dict[str, SkillEligibilityResult]:
        """List skills that failed eligibility checks.

        Returns:
            Dict of skill_id to eligibility result
        """
        return self._ineligible_skills.copy()

    def get_skill_for_prompt(self, skill_id: str) -> dict[str, Any] | None:
        """Get skill data formatted for prompt injection.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill data dict or None
        """
        skill = self.get(skill_id)
        if not skill:
            return None

        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers.keywords if skill.triggers else [],
            "steps": skill.steps,
            "guidelines": skill.guidelines,
            "content": skill.get_context(),
        }

    def get_skills_for_prompt(
        self,
        skill_ids: list[str] | None = None,
        matching_text: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get skills formatted for prompt injection.

        Args:
            skill_ids: Specific skill IDs to include
            matching_text: Text to match against triggers
            limit: Maximum number of skills

        Returns:
            List of skill data dicts
        """
        skills_to_include = []

        if skill_ids:
            for skill_id in skill_ids[:limit]:
                skill = self.get(skill_id)
                if skill:
                    skills_to_include.append(skill)
        elif matching_text:
            skills_to_include = self.find_matching_skills(matching_text, limit)
        else:
            skills_to_include = list(self._skills.values())[:limit]

        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers.keywords if s.triggers else [],
            }
            for s in skills_to_include
        ]

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
