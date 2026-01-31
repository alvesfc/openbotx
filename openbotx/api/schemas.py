"""API schemas for OpenBotX."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from openbotx.models.enums import (
    GatewayType,
    JobStatus,
    MessageType,
)


# Message schemas
class MessageCreate(BaseModel):
    """Request to create/enqueue a message."""

    channel_id: str
    text: str
    user_id: str | None = None
    gateway: GatewayType = GatewayType.HTTP
    message_type: MessageType = MessageType.TEXT
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """Response for a message."""

    id: str
    channel_id: str
    user_id: str | None
    gateway: str
    message_type: str
    text: str | None
    status: str
    correlation_id: str
    timestamp: datetime


class MessageHistoryResponse(BaseModel):
    """Response for message history."""

    channel_id: str
    messages: list[MessageResponse]
    total: int


# Skill schemas
class SkillResponse(BaseModel):
    """Response for a skill."""

    id: str
    name: str
    description: str
    version: str
    triggers: list[str]
    tools: list[str]
    file_path: str


class SkillCreate(BaseModel):
    """Request to create a skill."""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    guidelines: list[str] = Field(default_factory=list)


class SkillListResponse(BaseModel):
    """Response for skill list."""

    skills: list[SkillResponse]
    total: int


# Tool schemas
class ToolResponse(BaseModel):
    """Response for a tool."""

    name: str
    description: str
    parameters: list[dict[str, Any]]
    enabled: bool


class ToolListResponse(BaseModel):
    """Response for tool list."""

    tools: list[ToolResponse]
    total: int


# Provider schemas
class ProviderHealthResponse(BaseModel):
    """Health response for a provider."""

    name: str
    type: str
    status: str
    healthy: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ProvidersListResponse(BaseModel):
    """Response for providers list."""

    providers: list[ProviderHealthResponse]
    total: int


# Job schemas
class CronJobCreate(BaseModel):
    """Request to create a cron job."""

    name: str
    cron_expression: str
    message: str
    channel_id: str
    timezone: str = "UTC"
    max_runs: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ScheduledJobCreate(BaseModel):
    """Request to create a scheduled job."""

    name: str
    scheduled_at: datetime
    message: str
    channel_id: str
    timezone: str = "UTC"
    metadata: dict[str, str] = Field(default_factory=dict)


class JobResponse(BaseModel):
    """Response for a job."""

    id: str
    name: str
    job_type: str
    message: str
    channel_id: str
    status: str
    cron_expression: str | None = None
    scheduled_at: datetime | None = None
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    created_at: datetime


class JobListResponse(BaseModel):
    """Response for job list."""

    jobs: list[JobResponse]
    total: int


class JobUpdateRequest(BaseModel):
    """Request to update a job."""

    name: str | None = None
    message: str | None = None
    status: JobStatus | None = None
    cron_expression: str | None = None
    scheduled_at: datetime | None = None


# Memory schemas
class MemoryResponse(BaseModel):
    """Response for channel memory."""

    channel_id: str
    history_count: int
    summary: str | None
    total_tokens: int


class MemoryWriteRequest(BaseModel):
    """Request to write to memory."""

    role: str
    content: str


# Media schemas
class MediaResponse(BaseModel):
    """Response for a media file."""

    id: str
    filename: str
    content_type: str
    size: int
    path: str
    url: str | None
    created_at: datetime


class MediaListResponse(BaseModel):
    """Response for media list."""

    files: list[MediaResponse]
    total: int


# System schemas
class SystemHealthResponse(BaseModel):
    """System health response."""

    status: str
    version: str
    uptime_seconds: float
    providers: dict[str, bool]
    stats: dict[str, Any]


class SystemVersionResponse(BaseModel):
    """System version response."""

    version: str
    python_version: str
    config_version: str


# Log schemas
class LogEntry(BaseModel):
    """Log entry."""

    timestamp: datetime
    level: str
    message: str
    correlation_id: str | None
    details: dict[str, Any] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    """Response for logs query."""

    logs: list[LogEntry]
    total: int


class LogsQueryRequest(BaseModel):
    """Request to query logs."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    level: str | None = None
    correlation_id: str | None = None
    limit: int = 100
    offset: int = 0


# Generic response
class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    """Generic error response."""

    success: bool = False
    error: str
    details: dict[str, Any] = Field(default_factory=dict)
