from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Return service status for local development and deployment checks."""
    settings = get_settings()
    return HealthCheck(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )
