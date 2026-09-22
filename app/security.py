import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import ConfigurationError, get_webhook_api_key

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    """Authenticate trusted callers without exposing either key."""
    try:
        expected = get_webhook_api_key()
    except ConfigurationError as exc:
        raise HTTPException(503, "Webhook authentication is not configured.") from exc
    if not key or not secrets.compare_digest(key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Invalid or missing API key.")
