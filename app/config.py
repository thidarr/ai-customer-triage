import os
from urllib.parse import urlsplit
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Required application settings are missing."""


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str


def get_settings() -> Settings:
    # Existing environment variables take precedence over the local file.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not api_key or not model:
        raise ConfigurationError("GEMINI_API_KEY and GEMINI_MODEL must be set.")
    return Settings(gemini_api_key=api_key, gemini_model=model)


def get_demo_settings() -> tuple[bool, int]:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    enabled = os.getenv("PUBLIC_DEMO_ENABLED", "false").strip().lower()
    if enabled not in ("true", "false"):
        raise ConfigurationError("Invalid public demo settings.")
    if enabled == "false":
        return False, 20
    try:
        budget = int(os.getenv("PUBLIC_DEMO_MAX_REQUESTS", "20"))
    except ValueError as exc:
        raise ConfigurationError("Invalid public demo settings.") from exc
    if budget < 1:
        raise ConfigurationError("Invalid public demo settings.")
    return True, budget


def get_webhook_api_key() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    key = os.getenv("WEBHOOK_API_KEY", "").strip()
    if not key:
        raise ConfigurationError("WEBHOOK_API_KEY must be set.")
    return key


def get_database_url() -> str:
    """Read database configuration independently of Gemini settings."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL must be set.")
    return database_url


def get_slack_webhook_url() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname == "hooks.slack.com"
                 and parts.path.startswith("/services/") and not parts.username
                 and not parts.password and parts.port in (None, 443)
                 and not parts.query and not parts.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError("Slack webhook is missing or invalid.")
    return url
