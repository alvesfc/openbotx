"""Tool policy system for OpenBotX.

Implements tool profiles and groups:
- Profiles: minimal, coding, messaging, full
- Groups: fs, web, memory, sessions, ui, automation, messaging, etc.
- Allowlists and denylists for fine-grained control
"""

from dataclasses import dataclass, field
from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import ToolGroup, ToolProfile

logger = get_logger("tool_policy")


# Default tool groups for each profile
PROFILE_GROUPS: dict[ToolProfile, set[ToolGroup]] = {
    ToolProfile.MINIMAL: {
        ToolGroup.SYSTEM,
    },
    ToolProfile.CODING: {
        ToolGroup.SYSTEM,
        ToolGroup.FS,
        ToolGroup.DATABASE,
    },
    ToolProfile.MESSAGING: {
        ToolGroup.SYSTEM,
        ToolGroup.MESSAGING,
        ToolGroup.WEB,
    },
    ToolProfile.FULL: {
        ToolGroup.SYSTEM,
        ToolGroup.FS,
        ToolGroup.WEB,
        ToolGroup.MEMORY,
        ToolGroup.SESSIONS,
        ToolGroup.UI,
        ToolGroup.AUTOMATION,
        ToolGroup.MESSAGING,
        ToolGroup.DATABASE,
        ToolGroup.STORAGE,
        ToolGroup.SCHEDULER,
    },
}


@dataclass
class ToolPolicyConfig:
    """Configuration for tool policy."""

    default_profile: ToolProfile = ToolProfile.FULL
    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)
    group_overrides: dict[ToolGroup, bool] = field(default_factory=dict)
    approval_required_tools: list[str] = field(default_factory=list)
    dangerous_tools: list[str] = field(default_factory=list)


@dataclass
class ToolInfo:
    """Information about a tool for policy evaluation."""

    name: str
    group: ToolGroup | None = None
    groups: list[ToolGroup] = field(default_factory=list)
    approval_required: bool = False
    dangerous: bool = False
    admin_only: bool = False


@dataclass
class ToolPolicyResult:
    """Result of tool policy evaluation."""

    allowed: bool
    reason: str
    requires_approval: bool = False
    requires_elevation: bool = False


class ToolPolicy:
    """Manages tool access policies.

    Evaluates which tools are available based on:
    - Current tool profile
    - Tool groups
    - Allowlists and denylists
    - Security requirements
    """

    def __init__(self, config: ToolPolicyConfig | None = None) -> None:
        """Initialize tool policy.

        Args:
            config: Policy configuration
        """
        self.config = config or ToolPolicyConfig()
        self._logger = get_logger("tool_policy")

    def get_allowed_groups(self, profile: ToolProfile) -> set[ToolGroup]:
        """Get allowed tool groups for a profile.

        Args:
            profile: Tool profile

        Returns:
            Set of allowed tool groups
        """
        groups = PROFILE_GROUPS.get(profile, set()).copy()

        # Apply group overrides
        for group, allowed in self.config.group_overrides.items():
            if allowed:
                groups.add(group)
            elif group in groups:
                groups.remove(group)

        return groups

    def evaluate(
        self,
        tool: ToolInfo,
        profile: ToolProfile,
        elevated: bool = False,
    ) -> ToolPolicyResult:
        """Evaluate if a tool is allowed under current policy.

        Args:
            tool: Tool information
            profile: Current tool profile
            elevated: Whether elevated permissions are active

        Returns:
            Policy evaluation result
        """
        # Check explicit denylist first
        if tool.name in self.config.denylist:
            return ToolPolicyResult(
                allowed=False,
                reason=f"Tool '{tool.name}' is in denylist",
            )

        # Check explicit allowlist
        if tool.name in self.config.allowlist:
            return ToolPolicyResult(
                allowed=True,
                reason=f"Tool '{tool.name}' is in allowlist",
                requires_approval=tool.approval_required,
            )

        # Check admin-only tools
        if tool.admin_only and not elevated:
            return ToolPolicyResult(
                allowed=False,
                reason=f"Tool '{tool.name}' requires admin privileges",
                requires_elevation=True,
            )

        # Check dangerous tools
        if tool.dangerous or tool.name in self.config.dangerous_tools:
            if not elevated:
                return ToolPolicyResult(
                    allowed=False,
                    reason=f"Tool '{tool.name}' is marked as dangerous",
                    requires_elevation=True,
                )

        # Check tool groups
        allowed_groups = self.get_allowed_groups(profile)

        # If tool has no group, allow it if profile is FULL
        if tool.group is None and not tool.groups:
            if profile == ToolProfile.FULL:
                return ToolPolicyResult(
                    allowed=True,
                    reason="Tool has no group, allowed in FULL profile",
                    requires_approval=tool.approval_required,
                )
            else:
                return ToolPolicyResult(
                    allowed=False,
                    reason=f"Tool '{tool.name}' has no group and profile is not FULL",
                )

        # Check if tool's group is allowed
        if tool.group and tool.group in allowed_groups:
            return ToolPolicyResult(
                allowed=True,
                reason=f"Tool group '{tool.group.value}' is allowed in profile '{profile.value}'",
                requires_approval=tool.approval_required,
            )

        # Check if any of tool's groups are allowed
        for group in tool.groups:
            if group in allowed_groups:
                return ToolPolicyResult(
                    allowed=True,
                    reason=f"Tool group '{group.value}' is allowed in profile '{profile.value}'",
                    requires_approval=tool.approval_required,
                )

        # Default: not allowed
        return ToolPolicyResult(
            allowed=False,
            reason=f"Tool '{tool.name}' is not allowed in profile '{profile.value}'",
        )

    def filter_tools(
        self,
        tools: list[ToolInfo],
        profile: ToolProfile,
        elevated: bool = False,
    ) -> list[ToolInfo]:
        """Filter tools based on current policy.

        Args:
            tools: List of tools to filter
            profile: Current tool profile
            elevated: Whether elevated permissions are active

        Returns:
            List of allowed tools
        """
        allowed_tools = []

        for tool in tools:
            result = self.evaluate(tool, profile, elevated)
            if result.allowed:
                allowed_tools.append(tool)
            else:
                self._logger.debug(
                    "tool_filtered",
                    tool=tool.name,
                    reason=result.reason,
                )

        self._logger.info(
            "tools_filtered",
            profile=profile.value,
            total=len(tools),
            allowed=len(allowed_tools),
        )

        return allowed_tools

    def get_tool_names(
        self,
        tools: list[ToolInfo],
        profile: ToolProfile,
        elevated: bool = False,
    ) -> list[str]:
        """Get names of allowed tools.

        Args:
            tools: List of tools
            profile: Current tool profile
            elevated: Whether elevated permissions are active

        Returns:
            List of allowed tool names
        """
        allowed = self.filter_tools(tools, profile, elevated)
        return [t.name for t in allowed]


def create_tool_info_from_definition(definition: Any) -> ToolInfo:
    """Create ToolInfo from a tool definition.

    Args:
        definition: Tool definition object

    Returns:
        ToolInfo instance
    """
    group = None
    groups: list[ToolGroup] = []

    if hasattr(definition, "group") and definition.group:
        group = definition.group

    if hasattr(definition, "groups") and definition.groups:
        groups = definition.groups

    approval_required = False
    dangerous = False
    admin_only = False

    if hasattr(definition, "security") and definition.security:
        approval_required = getattr(definition.security, "approval_required", False)
        dangerous = getattr(definition.security, "dangerous", False)
        admin_only = getattr(definition.security, "admin_only", False)

    return ToolInfo(
        name=definition.name,
        group=group,
        groups=groups,
        approval_required=approval_required,
        dangerous=dangerous,
        admin_only=admin_only,
    )


# Global tool policy instance
_tool_policy: ToolPolicy | None = None


def get_tool_policy() -> ToolPolicy:
    """Get the global tool policy instance."""
    global _tool_policy
    if _tool_policy is None:
        _tool_policy = ToolPolicy()
    return _tool_policy


def set_tool_policy(policy: ToolPolicy) -> None:
    """Set the global tool policy instance."""
    global _tool_policy
    _tool_policy = policy
