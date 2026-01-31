# Tools Documentation

Tools are Python functions that the AI agent can call to perform actions.

## Creating Tools

### Using the Decorator

```python
from openbotx.core.tools_registry import tool

@tool(
    name="my_tool",
    description="Does something useful",
)
def tool_my_tool(param1: str, param2: int = 10) -> str:
    """Tool docstring.

    Args:
        param1: First parameter
        param2: Second parameter with default

    Returns:
        Result string
    """
    return f"Result: {param1}, {param2}"
```

### Using Naming Convention

Functions starting with `tool_` are automatically registered:

```python
def tool_calculate(expression: str) -> str:
    """Calculate a math expression."""
    return str(eval(expression))
```

### Manual Registration

```python
from openbotx.core.tools_registry import get_tools_registry

registry = get_tools_registry()
registry.register(
    name="my_tool",
    func=my_function,
    description="What it does",
)
```

## Tool Parameters

Parameters are extracted from the function signature:

```python
@tool(name="example")
def tool_example(
    required_param: str,           # Required
    optional_param: int = 10,      # Optional with default
    flag: bool = False,            # Boolean flag
) -> str:
    ...
```

Supported types:
- `str`: String
- `int`: Integer
- `float`: Float
- `bool`: Boolean
- `list`: List/array
- `dict`: Dictionary/object

## Async Tools

Tools can be async:

```python
@tool(name="async_tool")
async def tool_async_example(url: str) -> str:
    """Fetch data from URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
```

## Tool Security

Mark sensitive tools:

```python
@tool(
    name="dangerous_tool",
    security={"approval_required": True, "dangerous": True},
)
def tool_dangerous(cmd: str) -> str:
    """Execute a command (requires approval)."""
    ...
```

Security options:
- `approval_required`: User must approve before execution
- `admin_only`: Only admins can use
- `dangerous`: Marked as potentially dangerous
- `rate_limit`: Maximum calls per minute

## Tool Location

Place tools in `openbotx/tools/`:

```
openbotx/tools/
├── __init__.py
├── example_tool.py
├── file_tools.py
├── web_tools.py
└── custom_tools.py
```

All tools are loaded automatically on startup.

## API Access

### List Tools

```bash
curl http://localhost:8000/api/tools
```

### Get Tool Details

```bash
curl http://localhost:8000/api/tools/my_tool
```

## Example Tools

### File Operations

```python
@tool(name="read_file")
async def tool_read_file(path: str) -> str:
    """Read contents of a file."""
    from openbotx.providers.filesystem.local import LocalFilesystemProvider

    fs = LocalFilesystemProvider()
    return await fs.read(path)

@tool(name="write_file")
async def tool_write_file(path: str, content: str) -> str:
    """Write content to a file."""
    from openbotx.providers.filesystem.local import LocalFilesystemProvider

    fs = LocalFilesystemProvider()
    await fs.write(path, content)
    return f"Written to {path}"
```

### Web Operations

```python
@tool(name="fetch_url")
async def tool_fetch_url(url: str) -> str:
    """Fetch content from a URL."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text[:5000]  # Limit response size
```

### Data Operations

```python
@tool(name="json_parse")
def tool_json_parse(json_string: str) -> dict:
    """Parse a JSON string."""
    import json
    return json.loads(json_string)

@tool(name="format_date")
def tool_format_date(date_str: str, format: str = "%Y-%m-%d") -> str:
    """Format a date string."""
    from datetime import datetime
    dt = datetime.fromisoformat(date_str)
    return dt.strftime(format)
```

## Best Practices

1. **Clear Names**: Use descriptive, action-oriented names
2. **Docstrings**: Always include detailed docstrings
3. **Type Hints**: Use type hints for all parameters
4. **Error Handling**: Handle errors gracefully
5. **Size Limits**: Limit output size to avoid context overflow
6. **Security**: Mark dangerous tools appropriately
7. **Async**: Use async for I/O operations
