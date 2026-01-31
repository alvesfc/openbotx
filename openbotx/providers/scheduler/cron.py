"""Cron scheduler provider for OpenBotX."""

from datetime import UTC, datetime
from typing import Any

from openbotx.models.enums import JobStatus, ProviderStatus
from openbotx.models.job import CronJob, JobExecution, ScheduledJob
from openbotx.providers.scheduler.base import SchedulerProvider


class CronSchedulerProvider(SchedulerProvider):
    """Cron-based scheduler provider."""

    def __init__(
        self,
        name: str = "cron",
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize cron scheduler.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._cron_jobs: dict[str, CronJob] = {}
        self._scheduled_jobs: dict[str, ScheduledJob] = {}
        self._scheduler: Any = None
        self._running = False

    async def initialize(self) -> None:
        """Initialize the scheduler."""
        self._set_status(ProviderStatus.INITIALIZED)

    async def start(self) -> None:
        """Start the scheduler."""
        self._set_status(ProviderStatus.STARTING)

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler()
            self._scheduler.start()
            self._running = True

            self._set_status(ProviderStatus.RUNNING)
            self._logger.info("cron_scheduler_started")

        except ImportError:
            self._logger.error(
                "apscheduler_not_installed",
                message="Install apscheduler for scheduler support",
            )
            self._set_status(ProviderStatus.ERROR)
        except Exception as e:
            self._logger.error("scheduler_start_error", error=str(e))
            self._set_status(ProviderStatus.ERROR)

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._set_status(ProviderStatus.STOPPING)
        self._running = False

        if self._scheduler:
            self._scheduler.shutdown(wait=False)

        self._set_status(ProviderStatus.STOPPED)
        self._logger.info("cron_scheduler_stopped")

    def _calculate_next_run(self, cron_expression: str, tz: str = "UTC") -> datetime:
        """Calculate next run time from cron expression.

        Args:
            cron_expression: Cron expression (5 parts: min hour day month dow)
            tz: Timezone name

        Returns:
            Next run datetime
        """
        from apscheduler.triggers.cron import CronTrigger

        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=tz,
        )

        next_time = trigger.get_next_fire_time(None, datetime.now(UTC))
        return next_time if next_time else datetime.now(UTC)

    async def _execute_job(self, job: CronJob | ScheduledJob) -> None:
        """Execute a job.

        Args:
            job: Job to execute
        """
        self._logger.info(
            "executing_job",
            job_id=job.id,
            job_type=job.job_type.value,
        )

        # TODO: Send message to orchestrator
        # message = InboundMessage(
        #     channel_id=job.channel_id,
        #     gateway=GatewayType.SCHEDULER,
        #     message_type=MessageType.TEXT,
        #     text=job.message,
        #     metadata={
        #         "job_id": job.id,
        #         "job_type": job.job_type.value,
        #         "job_name": job.name,
        #     },
        # )

        # Update job stats
        if isinstance(job, CronJob):
            job.last_run = datetime.now(UTC)
            job.run_count += 1
            job.next_run = self._calculate_next_run(job.cron_expression, job.timezone)

            # Check if max runs reached
            if job.max_runs and job.run_count >= job.max_runs:
                job.status = JobStatus.COMPLETED
                if self._scheduler:
                    self._scheduler.remove_job(job.id)

        elif isinstance(job, ScheduledJob):
            job.executed_at = datetime.now(UTC)
            job.status = JobStatus.COMPLETED

        # Trigger callback
        if self._job_callback:
            self._job_callback(job)

    async def add_cron_job(self, job: CronJob) -> bool:
        """Add a cron job.

        Args:
            job: Cron job to add

        Returns:
            True if added successfully
        """
        if not self._scheduler:
            return False

        try:
            from apscheduler.triggers.cron import CronTrigger

            # Parse cron expression
            parts = job.cron_expression.split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron expression: {job.cron_expression}")

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone=job.timezone,
            )

            self._scheduler.add_job(
                self._execute_job,
                trigger,
                id=job.id,
                args=[job],
            )

            job.next_run = self._calculate_next_run(job.cron_expression, job.timezone)
            self._cron_jobs[job.id] = job

            self._logger.info(
                "cron_job_added",
                job_id=job.id,
                name=job.name,
                cron=job.cron_expression,
                next_run=job.next_run.isoformat() if job.next_run else None,
            )

            return True

        except Exception as e:
            self._logger.error(
                "add_cron_job_error",
                job_id=job.id,
                error=str(e),
            )
            return False

    async def add_scheduled_job(self, job: ScheduledJob) -> bool:
        """Add a scheduled job.

        Args:
            job: Scheduled job to add

        Returns:
            True if added successfully
        """
        if not self._scheduler:
            return False

        try:
            from apscheduler.triggers.date import DateTrigger

            trigger = DateTrigger(
                run_date=job.scheduled_at,
                timezone=job.timezone,
            )

            self._scheduler.add_job(
                self._execute_job,
                trigger,
                id=job.id,
                args=[job],
            )

            self._scheduled_jobs[job.id] = job

            self._logger.info(
                "scheduled_job_added",
                job_id=job.id,
                name=job.name,
                scheduled_at=job.scheduled_at.isoformat(),
            )

            return True

        except Exception as e:
            self._logger.error(
                "add_scheduled_job_error",
                job_id=job.id,
                error=str(e),
            )
            return False

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job.

        Args:
            job_id: Job ID

        Returns:
            True if removed successfully
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.remove_job(job_id)
            self._cron_jobs.pop(job_id, None)
            self._scheduled_jobs.pop(job_id, None)

            self._logger.info("job_removed", job_id=job_id)
            return True

        except Exception as e:
            self._logger.error(
                "remove_job_error",
                job_id=job_id,
                error=str(e),
            )
            return False

    async def pause_job(self, job_id: str) -> bool:
        """Pause a job.

        Args:
            job_id: Job ID

        Returns:
            True if paused successfully
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.pause_job(job_id)

            if job_id in self._cron_jobs:
                self._cron_jobs[job_id].status = JobStatus.PAUSED
            if job_id in self._scheduled_jobs:
                self._scheduled_jobs[job_id].status = JobStatus.PAUSED

            self._logger.info("job_paused", job_id=job_id)
            return True

        except Exception as e:
            self._logger.error("pause_job_error", job_id=job_id, error=str(e))
            return False

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.

        Args:
            job_id: Job ID

        Returns:
            True if resumed successfully
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.resume_job(job_id)

            if job_id in self._cron_jobs:
                self._cron_jobs[job_id].status = JobStatus.ACTIVE
            if job_id in self._scheduled_jobs:
                self._scheduled_jobs[job_id].status = JobStatus.ACTIVE

            self._logger.info("job_resumed", job_id=job_id)
            return True

        except Exception as e:
            self._logger.error("resume_job_error", job_id=job_id, error=str(e))
            return False

    async def get_job(self, job_id: str) -> CronJob | ScheduledJob | None:
        """Get a job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job or None
        """
        return self._cron_jobs.get(job_id) or self._scheduled_jobs.get(job_id)

    async def list_jobs(self) -> list[CronJob | ScheduledJob]:
        """List all jobs.

        Returns:
            List of all jobs
        """
        jobs: list[CronJob | ScheduledJob] = []
        jobs.extend(self._cron_jobs.values())
        jobs.extend(self._scheduled_jobs.values())
        return jobs

    async def run_job_now(self, job_id: str) -> JobExecution | None:
        """Run a job immediately.

        Args:
            job_id: Job ID

        Returns:
            Job execution record
        """
        job = await self.get_job(job_id)
        if not job:
            return None

        execution = JobExecution(
            job_id=job_id,
            job_type=job.job_type,
        )

        try:
            await self._execute_job(job)
            execution.success = True
            execution.completed_at = datetime.now(UTC)

            self._logger.info("job_run_manually", job_id=job_id)

        except Exception as e:
            execution.success = False
            execution.error = str(e)
            execution.completed_at = datetime.now(UTC)

            self._logger.error("manual_job_run_error", job_id=job_id, error=str(e))

        return execution
