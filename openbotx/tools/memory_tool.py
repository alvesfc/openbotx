"""Memory tools for OpenBotX - search and access memory."""

from openbotx.core.memory_index import get_memory_index
from openbotx.core.tools_registry import tool
from openbotx.models.memory import MemorySource
from openbotx.models.tool_result import ToolResult


@tool(
    name="memory_search",
    description="Search the agent's memory for relevant information. Uses hybrid search combining semantic and keyword matching.",
)
async def tool_memory_search(
    query: str,
    max_results: int = 5,
    source: str | None = None,
) -> ToolResult:
    """Search the agent's memory for information relevant to the query.

    Args:
        query: Search query describing what information to find
        max_results: Maximum number of results to return (default: 5)
        source: Filter by source type (memory, sessions, extra)

    Returns:
        Structured tool result with search results
    """
    result = ToolResult()

    try:
        memory_index = get_memory_index()
        if not memory_index:
            result.add_warning("Memory index not configured")
            return result

        if not memory_index.is_initialized:
            result.add_warning("Memory index not initialized")
            return result

        # parse source filter
        sources = None
        if source:
            try:
                sources = [MemorySource(source)]
            except ValueError:
                result.add_warning(f"Invalid source: {source}")

        # perform search
        results = await memory_index.search(
            query=query,
            max_results=max_results,
            sources=sources,
        )

        if not results:
            result.add_text("No relevant information found in memory.")
            return result

        # format results
        output_lines = [f"Found {len(results)} relevant result(s):\n"]

        for i, r in enumerate(results, 1):
            output_lines.append(f"## Result {i}: {r.path}")
            output_lines.append(f"**Lines {r.start_line}-{r.end_line}** | Score: {r.score:.2f}")
            output_lines.append("")
            output_lines.append(r.snippet)
            output_lines.append("")
            output_lines.append("---")
            output_lines.append("")

        result.add_text("\n".join(output_lines))
        return result

    except Exception as e:
        result.add_error(f"Memory search failed: {e}")
        return result


@tool(
    name="memory_get",
    description="Get the complete content of a specific memory file by path.",
)
async def tool_memory_get(path: str) -> ToolResult:
    """Get the complete content of a specific memory file.

    Args:
        path: Path to the memory file to retrieve

    Returns:
        Structured tool result with file content
    """
    result = ToolResult()

    try:
        memory_index = get_memory_index()
        if not memory_index:
            result.add_warning("Memory index not configured")
            return result

        content = await memory_index.get(path)
        if content:
            result.add_text(f"# Content of {path}\n\n{content}")
        else:
            result.add_error(f"File not found: {path}")

        return result

    except Exception as e:
        result.add_error(f"Memory get failed: {e}")
        return result


@tool(
    name="memory_stats",
    description="Get statistics about the memory index including file counts and sources.",
)
async def tool_memory_stats() -> ToolResult:
    """Get statistics about the memory index.

    Returns:
        Structured tool result with memory statistics
    """
    result = ToolResult()

    try:
        memory_index = get_memory_index()
        if not memory_index:
            result.add_warning("Memory index not configured")
            return result

        stats = memory_index.get_stats()

        output = [
            "# Memory Index Statistics",
            "",
            f"- **Total Files**: {stats.total_files}",
            f"- **Total Chunks**: {stats.total_chunks}",
            f"- **Index Size**: {stats.index_size_bytes / 1024:.1f} KB",
        ]

        if stats.sources:
            output.append("")
            output.append("## Sources")
            for source, count in stats.sources.items():
                output.append(f"- {source}: {count} files")

        if stats.last_sync:
            output.append("")
            output.append(f"**Last Sync**: {stats.last_sync.isoformat()}")

        result.add_text("\n".join(output))
        return result

    except Exception as e:
        result.add_error(f"Failed to get memory stats: {e}")
        return result
