"""Tools registry for OpenBotX - register and manage tools for the agent."""

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_type_hints

from openbotx.helpers.logger import get_logger
from openbotx.models.tool import (
    RegisteredTool,
    ToolDefinition,
    ToolParameter,
    ToolSecurity,
)


class ToolsRegistry:
    """Registry for managing tools available to the agent."""

    def __init__(self, tools_path: str | None = None) -> None:
        """Initialize tools registry.

        Args:
            tools_path: Path to user tools directory (optional, for future use)
        """
        self.tools_path = tools_path
        self._tools: dict[str, RegisteredTool] = {}
        self._logger = get_logger("tools_registry")

        # Path to built-in tools (inside openbotx package)
        self._builtin_tools_path = Path(__file__).parent.parent / "tools"

    async def load_tools(self) -> int:
        """Load all tools from built-in tools directory.

        Returns:
            Number of tools loaded
        """
        count = 0
        tools_dir = self._builtin_tools_path

        if not tools_dir.exists():
            self._logger.warning("tools_directory_not_found", path=str(tools_dir))
            return 0

        # Import each Python file in the tools directory
        for py_file in tools_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                module_name = f"openbotx.tools.{py_file.stem}"
                module = importlib.import_module(module_name)

                # Find all tool functions (decorated or annotated)
                for name, obj in inspect.getmembers(module):
                    if callable(obj) and hasattr(obj, "_openbotx_tool"):
                        self._register_decorated_tool(obj)
                        count += 1
                    elif callable(obj) and name.startswith("tool_"):
                        # Convention: functions starting with tool_ are tools
                        self._register_function_tool(obj, name[5:])
                        count += 1

            except Exception as e:
                self._logger.error(
                    "tool_module_load_error",
                    module=py_file.name,
                    error=str(e),
                )

        self._logger.info("tools_loaded", count=count)
        return count

    def _register_decorated_tool(self, func: Callable[..., Any]) -> None:
        """Register a tool that was decorated with @tool.

        Args:
            func: Decorated function
        """
        tool_meta = getattr(func, "_openbotx_tool", {})

        definition = ToolDefinition(
            name=tool_meta.get("name", func.__name__),
            description=tool_meta.get("description", func.__doc__ or ""),
            parameters=tool_meta.get("parameters", []),
            returns=tool_meta.get("returns", "str"),
            security=ToolSecurity(**tool_meta.get("security", {})),
            module_path=func.__module__,
            function_name=func.__name__,
        )

        self._tools[definition.name] = RegisteredTool(
            definition=definition,
            callable=func,
        )

        self._logger.info(
            "tool_registered",
            name=definition.name,
            description=definition.description[:50],
        )

    def _register_function_tool(
        self,
        func: Callable[..., Any],
        name: str,
    ) -> None:
        """Register a tool from a function.

        Args:
            func: Function to register
            name: Tool name
        """
        # Extract parameters from signature
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = hints.get(param_name, str)
            type_name = getattr(param_type, "__name__", "string")

            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=type_name,
                    description=f"Parameter {param_name}",
                    required=param.default == inspect.Parameter.empty,
                    default=(None if param.default == inspect.Parameter.empty else param.default),
                )
            )

        definition = ToolDefinition(
            name=name,
            description=func.__doc__ or f"Tool: {name}",
            parameters=parameters,
            module_path=func.__module__,
            function_name=func.__name__,
        )

        self._tools[name] = RegisteredTool(
            definition=definition,
            callable=func,
        )

        self._logger.info(
            "tool_registered",
            name=name,
            params=len(parameters),
        )

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str = "",
        parameters: list[ToolParameter] | None = None,
        security: ToolSecurity | None = None,
    ) -> None:
        """Manually register a tool.

        Args:
            name: Tool name
            func: Tool function
            description: Tool description
            parameters: Parameter definitions
            security: Security settings
        """
        definition = ToolDefinition(
            name=name,
            description=description or func.__doc__ or "",
            parameters=parameters or [],
            security=security or ToolSecurity(),
        )

        self._tools[name] = RegisteredTool(
            definition=definition,
            callable=func,
        )

        self._logger.info("tool_registered_manual", name=name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was unregistered
        """
        if name in self._tools:
            del self._tools[name]
            self._logger.info("tool_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> RegisteredTool | None:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            RegisteredTool or None
        """
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools.

        Returns:
            List of tool definitions
        """
        return [t.definition for t in self._tools.values()]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get JSON schemas for all tools.

        Returns:
            List of tool schemas
        """
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "name": tool.definition.name,
                    "description": tool.definition.description,
                    "parameters": tool.definition.get_schema(),
                }
            )
        return schemas

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
            Exception: If tool execution fails
        """
        tool = self._tools.get(name)
        if not tool or not tool.callable:
            raise ValueError(f"Tool not found: {name}")

        self._logger.info(
            "tool_calling",
            name=name,
            args=list(arguments.keys()),
        )

        # Call the tool
        result = tool.callable(**arguments)

        # Handle async tools
        if inspect.iscoroutine(result):
            result = await result

        return result

    @property
    def tool_count(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)


def tool(
    name: str | None = None,
    description: str | None = None,
    security: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a function as a tool.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        security: Security settings

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Extract parameters from signature
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = hints.get(param_name, str)
            type_name = getattr(param_type, "__name__", "string")

            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=type_name,
                    description=f"Parameter {param_name}",
                    required=param.default == inspect.Parameter.empty,
                    default=(None if param.default == inspect.Parameter.empty else param.default),
                )
            )

        # Store metadata on function
        func._openbotx_tool = {  # type: ignore
            "name": name or func.__name__,
            "description": description or func.__doc__ or "",
            "parameters": parameters,
            "security": security or {},
        }

        return func

    return decorator


# Global tools registry instance
_tools_registry: ToolsRegistry | None = None


def get_tools_registry() -> ToolsRegistry:
    """Get the global tools registry instance."""
    global _tools_registry
    if _tools_registry is None:
        _tools_registry = ToolsRegistry()
    return _tools_registry


def set_tools_registry(registry: ToolsRegistry) -> None:
    """Set the global tools registry instance."""
    global _tools_registry
    _tools_registry = registry
