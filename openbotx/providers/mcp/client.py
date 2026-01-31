"""MCP client provider for OpenBotX."""

import asyncio
import subprocess
from typing import Any

from openbotx.models.enums import ProviderStatus
from openbotx.providers.base import ProviderHealth
from openbotx.providers.mcp.base import MCPProvider, MCPResource, MCPTool


class MCPClientProvider(MCPProvider):
    """MCP client provider for connecting to MCP servers."""

    def __init__(
        self,
        name: str = "mcp",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize MCP client.

        Args:
            name: Provider name
            config: Provider configuration with server details
        """
        super().__init__(name, config)
        self.server_command = config.get("command", "") if config else ""
        self.server_args = config.get("args", []) if config else []
        self.server_env = config.get("env", {}) if config else {}

        self._process: subprocess.Popen[bytes] | None = None
        self._client: Any = None
        self._connected = False

    async def initialize(self) -> None:
        """Initialize the MCP client."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the MCP client and connect to server."""
        if not self.server_command:
            self._logger.warning("mcp_no_server_command")
            self._set_status(ProviderStatus.ERROR)
            return

        self._set_status(ProviderStatus.STARTING)

        try:
            # Try to import mcp
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Create server parameters
            server_params = StdioServerParameters(
                command=self.server_command,
                args=self.server_args,
                env=self.server_env if self.server_env else None,
            )

            # Connect to server
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    self._client = session
                    await self._initialize_session()

                    self._connected = True
                    self._set_status(ProviderStatus.RUNNING)
                    self._logger.info(
                        "mcp_client_started",
                        command=self.server_command,
                        tools=len(self._tools),
                        resources=len(self._resources),
                    )

                    # Keep connection alive
                    while self._connected:
                        await asyncio.sleep(1)

        except ImportError:
            self._logger.error(
                "mcp_not_installed",
                message="Install mcp package for MCP support",
            )
            self._set_status(ProviderStatus.ERROR)
        except Exception as e:
            self._logger.error("mcp_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)

    async def _initialize_session(self) -> None:
        """Initialize the MCP session."""
        if not self._client:
            return

        # Initialize the session
        await self._client.initialize()

        # Refresh tools and resources
        await self.list_tools()
        await self.list_resources()

    async def stop(self) -> None:
        """Stop the MCP client."""
        self._set_status(ProviderStatus.STOPPING)
        self._connected = False

        if self._process:
            self._process.terminate()
            self._process = None

        self._client = None
        self._tools.clear()
        self._resources.clear()

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("mcp_client_stopped")

    async def connect(self) -> bool:
        """Connect to the MCP server.

        Returns:
            True if connected successfully
        """
        if self._connected:
            return True

        await self.start()
        return self._connected

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        await self.stop()

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call an MCP tool.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if not self._client:
            raise RuntimeError("MCP client not connected")

        self._logger.info(
            "mcp_calling_tool",
            tool_name=tool_name,
            args=list(arguments.keys()),
        )

        result = await self._client.call_tool(tool_name, arguments)

        self._logger.info(
            "mcp_tool_result",
            tool_name=tool_name,
            success=True,
        )

        return result

    async def read_resource(self, uri: str) -> str:
        """Read an MCP resource.

        Args:
            uri: Resource URI

        Returns:
            Resource contents
        """
        if not self._client:
            raise RuntimeError("MCP client not connected")

        self._logger.info("mcp_reading_resource", uri=uri)

        result = await self._client.read_resource(uri)

        return result.contents[0].text if result.contents else ""

    async def list_tools(self) -> list[MCPTool]:
        """List available tools from the MCP server.

        Returns:
            List of available tools
        """
        if not self._client:
            return []

        result = await self._client.list_tools()

        self._tools = [
            MCPTool(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            )
            for tool in result.tools
        ]

        self._logger.info("mcp_tools_listed", count=len(self._tools))

        return self._tools

    async def list_resources(self) -> list[MCPResource]:
        """List available resources from the MCP server.

        Returns:
            List of available resources
        """
        if not self._client:
            return []

        result = await self._client.list_resources()

        self._resources = [
            MCPResource(
                uri=resource.uri,
                name=resource.name,
                description=resource.description,
                mime_type=resource.mimeType,
            )
            for resource in result.resources
        ]

        self._logger.info("mcp_resources_listed", count=len(self._resources))

        return self._resources

    async def health_check(self) -> ProviderHealth:
        """Check MCP provider health."""
        return ProviderHealth(
            healthy=self._connected,
            status=self.status,
            message="MCP connected" if self._connected else "MCP not connected",
            details={
                "connected": self._connected,
                "tools_count": len(self._tools),
                "resources_count": len(self._resources),
                "server_command": self.server_command,
            },
        )
