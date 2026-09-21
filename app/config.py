import os
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


def get_database_url() -> str:
    """Read database configuration independently of Gemini settings."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL must be set.")
    return database_url
