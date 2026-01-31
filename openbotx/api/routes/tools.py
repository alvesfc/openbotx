"""Tools API routes for OpenBotX."""

from fastapi import APIRouter, HTTPException

from openbotx.api.schemas import ToolListResponse, ToolResponse
from openbotx.core.tools_registry import get_tools_registry

router = APIRouter()


@router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """List all registered tools.

    Returns:
        List of tools
    """
    registry = get_tools_registry()
    tools = registry.list_tools()

    return ToolListResponse(
        tools=[
            ToolResponse(
                name=t.name,
                description=t.description,
                parameters=[p.model_dump() for p in t.parameters],
                enabled=t.enabled,
            )
            for t in tools
        ],
        total=len(tools),
    )


@router.get("/{tool_name}", response_model=ToolResponse)
async def get_tool(tool_name: str) -> ToolResponse:
    """Get a tool by name.

    Args:
        tool_name: Tool name

    Returns:
        Tool details
    """
    registry = get_tools_registry()
    tool = registry.get(tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return ToolResponse(
        name=tool.definition.name,
        description=tool.definition.description,
        parameters=[p.model_dump() for p in tool.definition.parameters],
        enabled=tool.definition.enabled,
    )
