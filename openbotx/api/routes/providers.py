"""Providers API routes for OpenBotX."""

from fastapi import APIRouter

from openbotx.api.schemas import ProviderHealthResponse, ProvidersListResponse
from openbotx.providers.base import get_provider_registry

router = APIRouter()


@router.get("", response_model=ProvidersListResponse)
async def list_providers() -> ProvidersListResponse:
    """List all registered providers.

    Returns:
        List of providers with health status
    """
    registry = get_provider_registry()
    providers = registry.get_all()

    responses = []
    for provider in providers:
        health = await provider.health_check()
        responses.append(
            ProviderHealthResponse(
                name=provider.name,
                type=provider.provider_type.value,
                status=provider.status.value,
                healthy=health.healthy,
                message=health.message,
                details=health.details,
            )
        )

    return ProvidersListResponse(
        providers=responses,
        total=len(responses),
    )


@router.get("/health")
async def providers_health() -> dict[str, dict[str, bool]]:
    """Get health status of all providers.

    Returns:
        Health status by provider
    """
    registry = get_provider_registry()
    health_status = await registry.health_check_all()

    return {
        key: {"healthy": health.healthy, "status": health.status.value}
        for key, health in health_status.items()
    }
