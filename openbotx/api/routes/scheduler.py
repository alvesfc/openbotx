"""Scheduler API routes for OpenBotX."""

from fastapi import APIRouter, HTTPException

from openbotx.api.schemas import (
    CronJobCreate,
    JobListResponse,
    JobResponse,
    ScheduledJobCreate,
    SuccessResponse,
)
from openbotx.models.enums import ProviderType
from openbotx.models.job import CronJob, ScheduledJob
from openbotx.providers.base import get_provider_registry
from openbotx.providers.scheduler.base import SchedulerProvider

router = APIRouter()


def _get_scheduler() -> SchedulerProvider:
    """Get scheduler provider."""
    registry = get_provider_registry()
    provider = registry.get(ProviderType.SCHEDULER)
    if not isinstance(provider, SchedulerProvider):
        raise HTTPException(status_code=503, detail="Scheduler not available")
    return provider


@router.get("/cron", response_model=JobListResponse)
async def list_cron_jobs() -> JobListResponse:
    """List all cron jobs.

    Returns:
        List of cron jobs
    """
    scheduler = _get_scheduler()
    all_jobs = await scheduler.list_jobs()
    cron_jobs = [j for j in all_jobs if isinstance(j, CronJob)]

    return JobListResponse(
        jobs=[
            JobResponse(
                id=j.id,
                name=j.name,
                job_type=j.job_type.value,
                message=j.message,
                channel_id=j.channel_id,
                status=j.status.value,
                cron_expression=j.cron_expression,
                last_run=j.last_run,
                next_run=j.next_run,
                run_count=j.run_count,
                created_at=j.created_at,
            )
            for j in cron_jobs
        ],
        total=len(cron_jobs),
    )


@router.post("/cron", response_model=JobResponse)
async def create_cron_job(request: CronJobCreate) -> JobResponse:
    """Create a new cron job.

    Args:
        request: Job creation request

    Returns:
        Created job
    """
    scheduler = _get_scheduler()

    job = CronJob(
        name=request.name,
        cron_expression=request.cron_expression,
        message=request.message,
        channel_id=request.channel_id,
        timezone=request.timezone,
        max_runs=request.max_runs,
        metadata=request.metadata,
    )

    success = await scheduler.add_cron_job(job)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to create cron job")

    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        message=job.message,
        channel_id=job.channel_id,
        status=job.status.value,
        cron_expression=job.cron_expression,
        next_run=job.next_run,
        run_count=job.run_count,
        created_at=job.created_at,
    )


@router.get("/schedule", response_model=JobListResponse)
async def list_scheduled_jobs() -> JobListResponse:
    """List all scheduled jobs.

    Returns:
        List of scheduled jobs
    """
    scheduler = _get_scheduler()
    all_jobs = await scheduler.list_jobs()
    scheduled_jobs = [j for j in all_jobs if isinstance(j, ScheduledJob)]

    return JobListResponse(
        jobs=[
            JobResponse(
                id=j.id,
                name=j.name,
                job_type=j.job_type.value,
                message=j.message,
                channel_id=j.channel_id,
                status=j.status.value,
                scheduled_at=j.scheduled_at,
                created_at=j.created_at,
            )
            for j in scheduled_jobs
        ],
        total=len(scheduled_jobs),
    )


@router.post("/schedule", response_model=JobResponse)
async def create_scheduled_job(request: ScheduledJobCreate) -> JobResponse:
    """Create a new scheduled job.

    Args:
        request: Job creation request

    Returns:
        Created job
    """
    scheduler = _get_scheduler()

    job = ScheduledJob(
        name=request.name,
        scheduled_at=request.scheduled_at,
        message=request.message,
        channel_id=request.channel_id,
        timezone=request.timezone,
        metadata=request.metadata,
    )

    success = await scheduler.add_scheduled_job(job)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to create scheduled job")

    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        message=job.message,
        channel_id=job.channel_id,
        status=job.status.value,
        scheduled_at=job.scheduled_at,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Get a job by ID.

    Args:
        job_id: Job ID

    Returns:
        Job details
    """
    scheduler = _get_scheduler()
    job = await scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return JobResponse(
        id=job.id,
        name=job.name,
        job_type=job.job_type.value,
        message=job.message,
        channel_id=job.channel_id,
        status=job.status.value,
        cron_expression=job.cron_expression if isinstance(job, CronJob) else None,
        scheduled_at=job.scheduled_at if isinstance(job, ScheduledJob) else None,
        last_run=job.last_run if isinstance(job, CronJob) else None,
        next_run=job.next_run if isinstance(job, CronJob) else None,
        run_count=job.run_count if isinstance(job, CronJob) else 0,
        created_at=job.created_at,
    )


@router.delete("/{job_id}", response_model=SuccessResponse)
async def delete_job(job_id: str) -> SuccessResponse:
    """Delete a job.

    Args:
        job_id: Job ID

    Returns:
        Success response
    """
    scheduler = _get_scheduler()
    success = await scheduler.remove_job(job_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return SuccessResponse(message=f"Job {job_id} deleted")


@router.post("/{job_id}/pause", response_model=SuccessResponse)
async def pause_job(job_id: str) -> SuccessResponse:
    """Pause a job.

    Args:
        job_id: Job ID

    Returns:
        Success response
    """
    scheduler = _get_scheduler()
    success = await scheduler.pause_job(job_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return SuccessResponse(message=f"Job {job_id} paused")


@router.post("/{job_id}/resume", response_model=SuccessResponse)
async def resume_job(job_id: str) -> SuccessResponse:
    """Resume a paused job.

    Args:
        job_id: Job ID

    Returns:
        Success response
    """
    scheduler = _get_scheduler()
    success = await scheduler.resume_job(job_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return SuccessResponse(message=f"Job {job_id} resumed")


@router.post("/{job_id}/run", response_model=SuccessResponse)
async def run_job_now(job_id: str) -> SuccessResponse:
    """Run a job immediately.

    Args:
        job_id: Job ID

    Returns:
        Success response
    """
    scheduler = _get_scheduler()
    execution = await scheduler.run_job_now(job_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if not execution.success:
        raise HTTPException(
            status_code=500,
            detail=f"Job execution failed: {execution.error}",
        )

    return SuccessResponse(message=f"Job {job_id} executed")
