"""Typed application settings; the only module allowed to read the environment."""

import re
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator, model_validator
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
    db_migrate_on_startup: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    http_timeout_s: float = Field(default=10.0, gt=0)
    retry_attempts: int = Field(default=3, ge=1)  # total attempts, including the first
    retry_base_delay_s: float = Field(default=0.25, gt=0)
    retry_max_delay_s: float = 4.0
    retry_after_cap_s: float = Field(default=30.0, gt=0)
    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_reset_s: float = Field(default=30.0, gt=0)
    ttl_static_s: float = Field(default=86400.0, gt=0)
    ttl_readings_s: float = Field(default=900.0, gt=0)
    cache_max_entries: int = Field(default=10000, ge=1)
    portal_max_rps: float = Field(default=1.5, gt=0, le=20)  # portal request starts per second
    index_max_age_s: float = Field(default=86400.0, gt=0)  # older index rows are flagged stale
    sync_on_startup: bool = True  # fill an empty index in the background at startup
    sync_readings_on_startup: bool = True
    sync_concurrency: int = Field(default=4, ge=1, le=4)  # per-meter portal calls in flight
    anomaly_voltage_min_v: float = Field(default=207.0, gt=0)  # 230 V - 10%
    anomaly_voltage_max_v: float = Field(default=253.0, gt=0)  # 230 V + 10%
    anomaly_flatline_hours: float = Field(default=6.0, gt=0)  # zero-kWh span that is flagged
    anomaly_spike_sigma: float = Field(default=4.0, gt=0)  # stdevs above the meter's mean
    anomaly_spike_min_points: int = Field(default=24, ge=2)  # intervals needed to judge spikes
    anomaly_inactive_min_kwh: float = Field(default=0.5, ge=0)  # faulty/decommissioned but above

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _max_delay_not_below_base(self) -> Self:
        if self.retry_max_delay_s < self.retry_base_delay_s:
            raise ValueError("retry_max_delay_s must be >= retry_base_delay_s")
        return self

    @model_validator(mode="after")
    def _voltage_band_is_ordered(self) -> Self:
        if self.anomaly_voltage_min_v >= self.anomaly_voltage_max_v:
            raise ValueError("anomaly_voltage_min_v must be < anomaly_voltage_max_v")
        return self


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
            fields = [str(err["loc"][0])] if err["loc"] else _fields_in(str(err["msg"]))
            for field in fields or ["?"]:
                name = f"URJA_{field.upper()}"
                if name not in names:
                    names.append(name)
        raise SystemExit(_message(names)) from None


def _fields_in(text: str) -> list[str]:
    """Setting names mentioned in a model-level validator message (which has no field loc)."""
    return [f for f in Settings.model_fields if re.search(rf"\b{f}\b", text)]


def _message(names: list[str]) -> str:
    return f"Invalid configuration: missing or invalid {', '.join(names)}. See .env.example."
