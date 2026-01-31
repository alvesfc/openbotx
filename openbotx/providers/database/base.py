"""Base database provider for OpenBotX."""

from abc import abstractmethod
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.sql import func

from openbotx.models.enums import DatabaseType, ProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth

# Define metadata for all tables
metadata = MetaData()

# Messages table
messages_table = Table(
    "messages",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("channel_id", String(255), nullable=False, index=True),
    Column("user_id", String(255), nullable=True),
    Column("gateway", String(50), nullable=False),
    Column("message_type", String(50), nullable=False),
    Column("content", Text, nullable=True),
    Column("attachments", JSON, nullable=True),
    Column("status", String(50), nullable=False),
    Column("correlation_id", String(36), nullable=True, index=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("processed_at", DateTime, nullable=True),
)

# Cron jobs table
jobs_cron_table = Table(
    "jobs_cron",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("cron_expression", String(100), nullable=False),
    Column("message", Text, nullable=False),
    Column("channel_id", String(255), nullable=False),
    Column("status", String(50), default="active"),
    Column("timezone", String(50), default="UTC"),
    Column("last_run", DateTime, nullable=True),
    Column("next_run", DateTime, nullable=True),
    Column("run_count", Integer, default=0),
    Column("max_runs", Integer, nullable=True),
    Column("metadata", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
)

# Scheduled jobs table
jobs_schedule_table = Table(
    "jobs_schedule",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("scheduled_at", DateTime, nullable=False),
    Column("message", Text, nullable=False),
    Column("channel_id", String(255), nullable=False),
    Column("status", String(50), default="active"),
    Column("timezone", String(50), default="UTC"),
    Column("executed_at", DateTime, nullable=True),
    Column("metadata", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
)

# Tool audit table
tool_audit_table = Table(
    "tool_audit",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("correlation_id", String(36), nullable=False, index=True),
    Column("tool_name", String(255), nullable=False, index=True),
    Column("arguments", JSON, nullable=True),
    Column("result", JSON, nullable=True),
    Column("success", Boolean, default=True),
    Column("duration_ms", Integer, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)

# Token usage table
token_usage_table = Table(
    "token_usage",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("correlation_id", String(36), nullable=False, index=True),
    Column("channel_id", String(255), nullable=False, index=True),
    Column("model", String(100), nullable=False),
    Column("input_tokens", Integer, default=0),
    Column("output_tokens", Integer, default=0),
    Column("estimated_tokens", Integer, default=0),
    Column("created_at", DateTime, server_default=func.now()),
)


class DatabaseProvider(ProviderBase):
    """Base class for database providers."""

    provider_type = ProviderType.DATABASE
    database_type: DatabaseType

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize database provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._engine: Any = None
        self._metadata = metadata

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a query and return results.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of result rows as dicts
        """
        pass

    @abstractmethod
    async def execute_many(
        self,
        query: str,
        params_list: list[dict[str, Any]],
    ) -> int:
        """Execute a query with multiple parameter sets.

        Args:
            query: SQL query
            params_list: List of parameter dicts

        Returns:
            Number of affected rows
        """
        pass

    @abstractmethod
    async def insert(
        self,
        table: str,
        data: dict[str, Any],
    ) -> str | None:
        """Insert a row and return the ID.

        Args:
            table: Table name
            data: Row data

        Returns:
            Inserted row ID
        """
        pass

    @abstractmethod
    async def update(
        self,
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> int:
        """Update rows.

        Args:
            table: Table name
            data: Update data
            where: Where conditions

        Returns:
            Number of affected rows
        """
        pass

    @abstractmethod
    async def delete(
        self,
        table: str,
        where: dict[str, Any],
    ) -> int:
        """Delete rows.

        Args:
            table: Table name
            where: Where conditions

        Returns:
            Number of deleted rows
        """
        pass

    @abstractmethod
    async def find_one(
        self,
        table: str,
        where: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find a single row.

        Args:
            table: Table name
            where: Where conditions

        Returns:
            Row data or None
        """
        pass

    @abstractmethod
    async def find_many(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Find multiple rows.

        Args:
            table: Table name
            where: Where conditions
            order_by: Order by clause
            limit: Maximum rows to return
            offset: Number of rows to skip

        Returns:
            List of rows
        """
        pass

    @abstractmethod
    async def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        pass

    async def health_check(self) -> ProviderHealth:
        """Check database provider health.

        Returns:
            ProviderHealth status
        """
        try:
            await self.execute("SELECT 1")
            return ProviderHealth(
                healthy=True,
                status=self.status,
                message="Database is connected",
                details={
                    "database_type": self.database_type.value,
                },
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message=f"Database error: {e}",
                details={
                    "database_type": self.database_type.value,
                    "error": str(e),
                },
            )
