from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Response returned by the health endpoint."""

    status: str
    service: str
    version: str
