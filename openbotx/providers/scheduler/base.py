"""Base scheduler provider for OpenBotX."""

from abc import abstractmethod
from collections.abc import Callable
from typing import Any

from openbotx.models.enums import ProviderType
from openbotx.models.job import CronJob, JobExecution, ScheduledJob
from openbotx.providers.base import ProviderBase, ProviderHealth

# Type for job execution callback
JobCallback = Callable[[CronJob | ScheduledJob], None]


class SchedulerProvider(ProviderBase):
    """Base class for scheduler providers."""

    provider_type = ProviderType.SCHEDULER

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize scheduler provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._job_callback: JobCallback | None = None

    def set_job_callback(self, callback: JobCallback) -> None:
        """Set the callback for when a job is triggered.

        Args:
            callback: Callback function
        """
        self._job_callback = callback

    @abstractmethod
    async def add_cron_job(self, job: CronJob) -> bool:
        """Add a cron job to the scheduler.

        Args:
            job: Cron job to add

        Returns:
            True if added successfully
        """
        pass

    @abstractmethod
    async def add_scheduled_job(self, job: ScheduledJob) -> bool:
        """Add a scheduled job to the scheduler.

        Args:
            job: Scheduled job to add

        Returns:
            True if added successfully
        """
        pass

    @abstractmethod
    async def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler.

        Args:
            job_id: Job ID to remove

        Returns:
            True if removed successfully
        """
        pass

    @abstractmethod
    async def pause_job(self, job_id: str) -> bool:
        """Pause a job.

        Args:
            job_id: Job ID to pause

        Returns:
            True if paused successfully
        """
        pass

    @abstractmethod
    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.

        Args:
            job_id: Job ID to resume

        Returns:
            True if resumed successfully
        """
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> CronJob | ScheduledJob | None:
        """Get a job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job or None if not found
        """
        pass

    @abstractmethod
    async def list_jobs(self) -> list[CronJob | ScheduledJob]:
        """List all jobs.

        Returns:
            List of all jobs
        """
        pass

    @abstractmethod
    async def run_job_now(self, job_id: str) -> JobExecution | None:
        """Manually trigger a job to run now.

        Args:
            job_id: Job ID to run

        Returns:
            JobExecution record or None if job not found
        """
        pass

    async def health_check(self) -> ProviderHealth:
        """Check scheduler provider health.

        Returns:
            ProviderHealth status
        """
        jobs = await self.list_jobs()
        active_jobs = [j for j in jobs if j.status.value == "active"]

        return ProviderHealth(
            healthy=True,
            status=self.status,
            message="Scheduler is running",
            details={
                "total_jobs": len(jobs),
                "active_jobs": len(active_jobs),
            },
        )
