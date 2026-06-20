"""Health and readiness endpoints."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe.

    Returns:
        Service name, environment, and status.
    """
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "status": "ok",
    }
