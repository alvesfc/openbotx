"""Base MCP provider for OpenBotX."""

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from openbotx.models.enums import ProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth


class MCPTool(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPResource(BaseModel):
    """MCP resource definition."""

    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = None


class MCPProvider(ProviderBase):
    """Base class for MCP providers."""

    provider_type = ProviderType.MCP

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize MCP provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []

    @property
    def tools(self) -> list[MCPTool]:
        """Get available MCP tools."""
        return self._tools

    @property
    def resources(self) -> list[MCPResource]:
        """Get available MCP resources."""
        return self._resources

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the MCP server.

        Returns:
            True if connected successfully
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        pass

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        pass

    @abstractmethod
    async def read_resource(self, uri: str) -> str:
        """Read an MCP resource.

        Args:
            uri: Resource URI

        Returns:
            Resource contents
        """
        pass

    @abstractmethod
    async def list_tools(self) -> list[MCPTool]:
        """List available tools from the MCP server.

        Returns:
            List of available tools
        """
        pass

    @abstractmethod
    async def list_resources(self) -> list[MCPResource]:
        """List available resources from the MCP server.

        Returns:
            List of available resources
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check MCP provider health.

        Returns:
            ProviderHealth status
        """
        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="MCP provider is available",
            details={
                "tools_count": len(self._tools),
                "resources_count": len(self._resources),
            },
        )
