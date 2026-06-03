from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Credentials submitted by the user."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token returned on successful login."""

    access_token: str
    token_type: str = "bearer"
