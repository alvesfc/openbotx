"""Job models for OpenBotX scheduler."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from openbotx.models.enums import JobStatus, JobType


class JobBase(BaseModel):
    """Base model for scheduled jobs."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    message: str
    channel_id: str
    status: JobStatus = JobStatus.ACTIVE
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CronJob(JobBase):
    """Cron job definition - runs on schedule like cron."""

    job_type: JobType = JobType.CRON
    cron_expression: str
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None
    timezone: str = "UTC"

    def is_active(self) -> bool:
        """Check if job should be active."""
        if self.status != JobStatus.ACTIVE:
            return False
        if self.max_runs and self.run_count >= self.max_runs:
            return False
        return True


class ScheduledJob(JobBase):
    """Scheduled job definition - runs once at specific time."""

    job_type: JobType = JobType.SCHEDULED
    scheduled_at: datetime
    executed_at: datetime | None = None
    timezone: str = "UTC"

    def is_due(self, now: datetime | None = None) -> bool:
        """Check if job is due for execution."""
        if self.status != JobStatus.ACTIVE:
            return False
        if self.executed_at is not None:
            return False
        now = now or datetime.now(UTC)
        return now >= self.scheduled_at


class JobExecution(BaseModel):
    """Record of a job execution."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str
    job_type: JobType
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    success: bool = False
    error: str | None = None
    message_id: str | None = None


class JobCreateRequest(BaseModel):
    """Request to create a job."""

    name: str
    message: str
    channel_id: str
    job_type: JobType
    cron_expression: str | None = None
    scheduled_at: datetime | None = None
    timezone: str = "UTC"
    max_runs: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class JobUpdateRequest(BaseModel):
    """Request to update a job."""

    name: str | None = None
    message: str | None = None
    status: JobStatus | None = None
    cron_expression: str | None = None
    scheduled_at: datetime | None = None
    timezone: str | None = None
    max_runs: int | None = None
    metadata: dict[str, str] | None = None
