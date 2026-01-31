"""Telemetry module for OpenBotX - logging and token tracking."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.models.tool import ToolCall


class TokenUsage(BaseModel):
    """Token usage for a request."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str
    channel_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_tokens: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OperationMetrics(BaseModel):
    """Metrics for an operation."""

    operation: str
    correlation_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int = 0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Telemetry:
    """Telemetry for tracking operations, tokens, and metrics."""

    def __init__(self, database_provider: Any = None) -> None:
        """Initialize telemetry.

        Args:
            database_provider: Optional database provider for persistence
        """
        self._database = database_provider
        self._logger = get_logger("telemetry")

        # In-memory stats
        self._token_usage: list[TokenUsage] = []
        self._tool_calls: list[ToolCall] = []
        self._operations: list[OperationMetrics] = []

        # Aggregate stats
        self._stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tool_calls": 0,
            "total_operations": 0,
            "failed_operations": 0,
        }

    async def log_token_usage(
        self,
        correlation_id: str,
        channel_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_tokens: int = 0,
    ) -> TokenUsage:
        """Log token usage for a request.

        Args:
            correlation_id: Correlation ID
            channel_id: Channel ID
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            estimated_tokens: Estimated tokens before request

        Returns:
            TokenUsage record
        """
        usage = TokenUsage(
            correlation_id=correlation_id,
            channel_id=channel_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_tokens=estimated_tokens,
        )

        self._token_usage.append(usage)
        self._stats["total_input_tokens"] += input_tokens
        self._stats["total_output_tokens"] += output_tokens

        self._logger.info(
            "token_usage",
            correlation_id=correlation_id,
            channel_id=channel_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # Persist to database if available
        if self._database:
            await self._database.insert(
                "token_usage",
                usage.model_dump(exclude={"timestamp"}),
            )

        return usage

    async def log_tool_call(
        self,
        correlation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> ToolCall:
        """Log a tool call.

        Args:
            correlation_id: Correlation ID
            tool_name: Tool name
            arguments: Tool arguments
            result: Tool result
            error: Error message if failed
            duration_ms: Execution duration in ms

        Returns:
            ToolCall record
        """
        call = ToolCall(
            id=str(uuid4()),
            correlation_id=correlation_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            error=error,
            success=error is None,
            duration_ms=duration_ms,
        )

        self._tool_calls.append(call)
        self._stats["total_tool_calls"] += 1

        log_method = self._logger.info if call.success else self._logger.error
        log_method(
            "tool_call",
            correlation_id=correlation_id,
            tool_name=tool_name,
            success=call.success,
            duration_ms=duration_ms,
            error=error,
        )

        # Persist to database if available
        if self._database:
            await self._database.insert(
                "tool_audit",
                {
                    "id": call.id,
                    "correlation_id": correlation_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": str(result) if result else None,
                    "success": call.success,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )

        return call

    def start_operation(
        self,
        operation: str,
        correlation_id: str,
        **metadata: Any,
    ) -> OperationMetrics:
        """Start tracking an operation.

        Args:
            operation: Operation name
            correlation_id: Correlation ID
            **metadata: Additional metadata

        Returns:
            OperationMetrics for tracking
        """
        metrics = OperationMetrics(
            operation=operation,
            correlation_id=correlation_id,
            metadata=metadata,
        )

        self._operations.append(metrics)
        self._stats["total_operations"] += 1

        self._logger.info(
            "operation_started",
            operation=operation,
            correlation_id=correlation_id,
            **metadata,
        )

        return metrics

    def end_operation(
        self,
        metrics: OperationMetrics,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """End an operation.

        Args:
            metrics: Operation metrics
            success: Whether operation succeeded
            error: Error message if failed
        """
        metrics.completed_at = datetime.now(UTC)
        metrics.duration_ms = int(
            (metrics.completed_at - metrics.started_at).total_seconds() * 1000
        )
        metrics.success = success
        metrics.error = error

        if not success:
            self._stats["failed_operations"] += 1

        log_method = self._logger.info if success else self._logger.error
        log_method(
            "operation_ended",
            operation=metrics.operation,
            correlation_id=metrics.correlation_id,
            duration_ms=metrics.duration_ms,
            success=success,
            error=error,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self._stats,
            "token_usage_count": len(self._token_usage),
            "tool_calls_count": len(self._tool_calls),
            "operations_count": len(self._operations),
        }

    def get_token_usage(
        self,
        channel_id: str | None = None,
        limit: int = 100,
    ) -> list[TokenUsage]:
        """Get token usage records.

        Args:
            channel_id: Filter by channel ID
            limit: Maximum records to return

        Returns:
            List of token usage records
        """
        records = self._token_usage

        if channel_id:
            records = [r for r in records if r.channel_id == channel_id]

        return records[-limit:]

    def get_tool_calls(
        self,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[ToolCall]:
        """Get tool call records.

        Args:
            correlation_id: Filter by correlation ID
            limit: Maximum records to return

        Returns:
            List of tool call records
        """
        records = self._tool_calls

        if correlation_id:
            records = [r for r in records if r.correlation_id == correlation_id]

        return records[-limit:]

    def clear_history(self, older_than_hours: int = 24) -> int:
        """Clear old telemetry data from memory.

        Args:
            older_than_hours: Clear data older than this many hours

        Returns:
            Number of records cleared
        """
        cutoff = datetime.now(UTC)
        from datetime import timedelta

        cutoff = cutoff - timedelta(hours=older_than_hours)

        # Clear token usage
        original_count = len(self._token_usage)
        self._token_usage = [t for t in self._token_usage if t.timestamp > cutoff]
        token_cleared = original_count - len(self._token_usage)

        # Clear tool calls
        original_count = len(self._tool_calls)
        self._tool_calls = [t for t in self._tool_calls if t.timestamp > cutoff]
        tool_cleared = original_count - len(self._tool_calls)

        # Clear operations
        original_count = len(self._operations)
        self._operations = [o for o in self._operations if o.started_at > cutoff]
        ops_cleared = original_count - len(self._operations)

        total_cleared = token_cleared + tool_cleared + ops_cleared

        self._logger.info(
            "telemetry_cleared",
            token_usage=token_cleared,
            tool_calls=tool_cleared,
            operations=ops_cleared,
            total=total_cleared,
        )

        return total_cleared


# Global telemetry instance
_telemetry: Telemetry | None = None


def get_telemetry() -> Telemetry:
    """Get the global telemetry instance."""
    global _telemetry
    if _telemetry is None:
        _telemetry = Telemetry()
    return _telemetry


def set_telemetry(telemetry: Telemetry) -> None:
    """Set the global telemetry instance."""
    global _telemetry
    _telemetry = telemetry
