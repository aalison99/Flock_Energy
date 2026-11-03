"""Typed application settings; the only module allowed to read the environment."""

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """All runtime configuration, read from URJA_* variables and the repo-root .env."""

    model_config = SettingsConfigDict(env_prefix="URJA_", env_file=ENV_FILE, extra="ignore")

    app_name: str = "Urja Meter API"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: LogLevel = "INFO"
    portal_url: HttpUrl
    portal_email: str
    portal_password: SecretStr
    db_url: str = "sqlite:///./urja.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    http_timeout_s: float = Field(default=10.0, gt=0)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


def load_settings() -> Settings:
    """Build Settings from the environment, exiting with a short message when invalid."""
    try:
        return Settings()
    except SettingsError as exc:
        # e.g. a complex field (list) given a non-JSON value: the message names the field.
        match = re.search(r'field "(\w+)"', str(exc))
        setting_names = [f"URJA_{match.group(1).upper()}"] if match else ["a URJA_* variable"]
        raise SystemExit(_message(setting_names)) from None
    except ValidationError as exc:
        names: list[str] = []
        for err in exc.errors():
            name = f"URJA_{str(err['loc'][0]).upper()}" if err["loc"] else "URJA_?"
            if name not in names:
                names.append(name)
        raise SystemExit(_message(names)) from None


def _message(names: list[str]) -> str:
    return f"Invalid configuration: missing or invalid {', '.join(names)}. See .env.example."
