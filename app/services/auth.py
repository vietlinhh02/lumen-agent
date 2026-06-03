from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_settings = get_settings()


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain*."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


def create_access_token(username: str) -> str:
    """Create a JWT access token for *username*."""
    expire = datetime.now(UTC) + timedelta(minutes=_settings.jwt_expire_minutes)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, _settings.jwt_secret_key, algorithm=_settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the username encoded in *token*, or None if invalid."""
    try:
        payload = jwt.decode(
            token, _settings.jwt_secret_key, algorithms=[_settings.jwt_algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None
