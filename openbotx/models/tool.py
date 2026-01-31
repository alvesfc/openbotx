"""Tool models for OpenBotX."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Parameter definition for a tool."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


class ToolSecurity(BaseModel):
    """Security settings for a tool."""

    approval_required: bool = False
    admin_only: bool = False
    dangerous: bool = False
    rate_limit: int | None = None


class ToolDefinition(BaseModel):
    """Tool definition for the agent."""

    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    returns: str = "str"
    security: ToolSecurity = Field(default_factory=ToolSecurity)
    module_path: str | None = None
    function_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


class RegisteredTool(BaseModel):
    """A tool registered with its callable."""

    definition: ToolDefinition
    callable: Callable[..., Any] | None = None

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class ToolCall(BaseModel):
    """Record of a tool call."""

    id: str
    correlation_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None
    success: bool = True
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_by: str | None = None


class ToolApprovalRequest(BaseModel):
    """Request for tool approval."""

    tool_name: str
    arguments: dict[str, Any]
    reason: str
    channel_id: str
    user_id: str | None = None
    correlation_id: str
    expires_at: datetime | None = None
