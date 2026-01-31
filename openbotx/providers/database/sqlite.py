"""SQLite database provider for OpenBotX."""

import json
from pathlib import Path
from typing import Any

import aiosqlite

from openbotx.models.enums import DatabaseType, ProviderStatus
from openbotx.providers.base import ProviderHealth
from openbotx.providers.database.base import DatabaseProvider


class SQLiteProvider(DatabaseProvider):
    """SQLite database provider."""

    database_type = DatabaseType.SQLITE

    def __init__(
        self,
        name: str = "sqlite",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize SQLite provider.

        Args:
            name: Provider name
            config: Provider configuration with 'path' key
        """
        super().__init__(name, config)
        self.db_path = config.get("path", "./db/openbotx.db") if config else "./db/openbotx.db"
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Initialize the SQLite provider."""
        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the SQLite provider."""
        self._set_status(ProviderStatus.STARTING)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self.create_tables()
        self._set_status(ProviderStatus.RUNNING)
        self._logger.info("sqlite_started", path=self.db_path)

    async def stop(self) -> None:
        """Stop the SQLite provider."""
        self._set_status(ProviderStatus.STOPPING)
        if self._connection:
            await self._connection.close()
            self._connection = None
        self._set_status(ProviderStatus.STOPPED)

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get database connection."""
        if not self._connection:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row
        return self._connection

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a query and return results."""
        conn = await self._get_connection()

        # Convert dict params to tuple for SQLite
        if params:
            # Replace :name with ? and collect values
            param_values = []
            for key, value in params.items():
                query = query.replace(f":{key}", "?")
                if isinstance(value, (dict, list)):
                    param_values.append(json.dumps(value))
                else:
                    param_values.append(value)
            cursor = await conn.execute(query, tuple(param_values))
        else:
            cursor = await conn.execute(query)

        rows = await cursor.fetchall()
        await conn.commit()

        return [dict(row) for row in rows]

    async def execute_many(
        self,
        query: str,
        params_list: list[dict[str, Any]],
    ) -> int:
        """Execute a query with multiple parameter sets."""
        conn = await self._get_connection()

        # Convert each param dict to tuple
        param_tuples = []
        for params in params_list:
            values = []
            for value in params.values():
                if isinstance(value, (dict, list)):
                    values.append(json.dumps(value))
                else:
                    values.append(value)
            param_tuples.append(tuple(values))

        # Replace :name with ?
        for key in params_list[0].keys() if params_list else []:
            query = query.replace(f":{key}", "?")

        cursor = await conn.executemany(query, param_tuples)
        await conn.commit()
        return cursor.rowcount

    async def insert(
        self,
        table: str,
        data: dict[str, Any],
    ) -> str | None:
        """Insert a row and return the ID."""
        columns = list(data.keys())
        placeholders = ["?" for _ in columns]
        values = []
        for v in data.values():
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)

        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

        conn = await self._get_connection()
        cursor = await conn.execute(query, tuple(values))
        await conn.commit()

        return data.get("id") or str(cursor.lastrowid)

    async def update(
        self,
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> int:
        """Update rows."""
        set_parts = []
        values = []
        for key, value in data.items():
            set_parts.append(f"{key} = ?")
            if isinstance(value, (dict, list)):
                values.append(json.dumps(value))
            else:
                values.append(value)

        where_parts = []
        for key, value in where.items():
            where_parts.append(f"{key} = ?")
            values.append(value)

        query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

        conn = await self._get_connection()
        cursor = await conn.execute(query, tuple(values))
        await conn.commit()

        return cursor.rowcount

    async def delete(
        self,
        table: str,
        where: dict[str, Any],
    ) -> int:
        """Delete rows."""
        where_parts = []
        values = []
        for key, value in where.items():
            where_parts.append(f"{key} = ?")
            values.append(value)

        query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"

        conn = await self._get_connection()
        cursor = await conn.execute(query, tuple(values))
        await conn.commit()

        return cursor.rowcount

    async def find_one(
        self,
        table: str,
        where: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find a single row."""
        where_parts = []
        values = []
        for key, value in where.items():
            where_parts.append(f"{key} = ?")
            values.append(value)

        query = f"SELECT * FROM {table} WHERE {' AND '.join(where_parts)} LIMIT 1"

        conn = await self._get_connection()
        cursor = await conn.execute(query, tuple(values))
        row = await cursor.fetchone()

        if row:
            result = dict(row)
            # Parse JSON fields
            for key, value in result.items():
                if isinstance(value, str) and value.startswith(("{", "[")):
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            return result
        return None

    async def find_many(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """Find multiple rows."""
        query = f"SELECT * FROM {table}"
        values: list[Any] = []

        if where:
            where_parts = []
            for key, value in where.items():
                where_parts.append(f"{key} = ?")
                values.append(value)
            query += f" WHERE {' AND '.join(where_parts)}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        if offset:
            query += f" OFFSET {offset}"

        conn = await self._get_connection()
        cursor = await conn.execute(query, tuple(values))
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            result = dict(row)
            # Parse JSON fields
            for key, value in result.items():
                if isinstance(value, str) and value.startswith(("{", "[")):
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            results.append(result)

        return results

    async def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        conn = await self._get_connection()

        # Messages table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                user_id TEXT,
                gateway TEXT NOT NULL,
                message_type TEXT NOT NULL,
                content TEXT,
                attachments TEXT,
                status TEXT NOT NULL,
                correlation_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """
        )

        # Create indexes
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_correlation ON messages(correlation_id)"
        )

        # Cron jobs table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs_cron (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                message TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                timezone TEXT DEFAULT 'UTC',
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                run_count INTEGER DEFAULT 0,
                max_runs INTEGER,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Scheduled jobs table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs_schedule (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scheduled_at TIMESTAMP NOT NULL,
                message TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                timezone TEXT DEFAULT 'UTC',
                executed_at TIMESTAMP,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Tool audit table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_audit (
                id TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT,
                result TEXT,
                success INTEGER DEFAULT 1,
                duration_ms INTEGER,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_audit_correlation ON tool_audit(correlation_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_audit_tool ON tool_audit(tool_name)"
        )

        # Token usage table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_tokens INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_correlation ON token_usage(correlation_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_channel ON token_usage(channel_id)"
        )

        await conn.commit()
        self._logger.info("database_tables_created")

    async def health_check(self) -> ProviderHealth:
        """Check SQLite provider health."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute("SELECT 1")
            await cursor.fetchone()
            return ProviderHealth(
                healthy=True,
                status=self.status,
                message="SQLite database is connected",
                details={
                    "database_type": self.database_type.value,
                    "path": self.db_path,
                },
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                status=self.status,
                message=f"SQLite error: {e}",
                details={
                    "database_type": self.database_type.value,
                    "path": self.db_path,
                    "error": str(e),
                },
            )
