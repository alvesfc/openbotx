"""Structured logging for OpenBotX."""

import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.types import Processor

from openbotx.models.enums import LogFormat, LogLevel


def _add_timestamp(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add timestamp to log event."""
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def _add_log_level(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def setup_logging(
    level: LogLevel = LogLevel.INFO,
    log_format: LogFormat = LogFormat.JSON,
    log_file: str | None = None,
    max_size_mb: int = 100,
    backup_count: int = 5,
) -> None:
    """Setup structured logging.

    Args:
        level: Log level
        log_format: Log format (json or text)
        log_file: Path to log file (optional)
        max_size_mb: Max log file size in MB
        backup_count: Number of backup files to keep
    """
    # Configure standard logging
    log_level = getattr(logging, level.value)

    # Define processors based on format
    shared_processors: list[Processor] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_timestamp,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == LogFormat.JSON:
        final_processor: Processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer(colors=True)

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Create formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=final_processor,
        foreign_pre_chain=shared_processors,
    )

    # Configure handlers
    handlers: list[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger.

    Args:
        name: Logger name (optional)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding context to logs."""

    def __init__(self, **context: Any) -> None:
        """Initialize log context.

        Args:
            **context: Context key-value pairs to add
        """
        self.context = context
        self._token: Any = None

    def __enter__(self) -> "LogContext":
        """Enter context."""
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context."""
        if self._token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def log_operation(
    operation: str,
    correlation_id: str | None = None,
    **kwargs: Any,
) -> LogContext:
    """Create a log context for an operation.

    Args:
        operation: Name of the operation
        correlation_id: Correlation ID for tracing
        **kwargs: Additional context

    Returns:
        LogContext instance
    """
    context = {"operation": operation, **kwargs}
    if correlation_id:
        context["correlation_id"] = correlation_id
    return LogContext(**context)
