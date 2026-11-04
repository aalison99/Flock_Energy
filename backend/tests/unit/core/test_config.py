from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings, load_settings

REQUIRED = ("URJA_PORTAL_URL", "URJA_PORTAL_EMAIL", "URJA_PORTAL_PASSWORD")


@pytest.fixture
def clean_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> pytest.MonkeyPatch:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    monkeypatch.setitem(Settings.model_config, "env_file", "/nonexistent/.env")
    return monkeypatch


def test_missing_required_fields_exit_with_names(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        load_settings()
    msg = str(exc.value)
    assert msg.startswith("Invalid configuration: missing or invalid ")
    for name in REQUIRED:
        assert name in msg
    assert msg.endswith("See .env.example.")


def test_env_vars_load(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("URJA_PORTAL_URL", "https://p.example.test")
    clean_env.setenv("URJA_PORTAL_EMAIL", "a@b.test")
    clean_env.setenv("URJA_PORTAL_PASSWORD", "pw")
    clean_env.setenv("URJA_LOG_LEVEL", "DEBUG")
    s = load_settings()
    assert str(s.portal_url).startswith("https://p.example.test")
    assert s.portal_email == "a@b.test"
    assert s.portal_password.get_secret_value() == "pw"
    assert s.log_level == "DEBUG"
    assert s.app_name == "Urja Meter API"
    assert s.environment == "dev"
    assert s.db_url == "sqlite:///./urja.db"
    assert s.cors_origins == ["http://localhost:5173"]
    assert s.http_timeout_s == 10.0


def test_password_not_in_repr(settings: Settings) -> None:
    assert "s3cret-value" not in repr(settings)
    assert "s3cret-value" not in str(settings)


@pytest.mark.parametrize("bad", [0, -1.5])
def test_non_positive_timeout_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        Settings(
            portal_url="https://x.example.test",  # type: ignore[arg-type]
            portal_email="a@b.test",
            portal_password="pw",  # type: ignore[arg-type]
            http_timeout_s=bad,
            _env_file=None,
        )


def test_env_file_is_repo_root_dotenv() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    assert repo_root / ".env" == config.ENV_FILE


def test_unparseable_complex_value_exits_cleanly(clean_env: pytest.MonkeyPatch) -> None:
    for name, val in (
        ("URJA_PORTAL_URL", "https://p.example.test"),
        ("URJA_PORTAL_EMAIL", "a@b.test"),
        ("URJA_PORTAL_PASSWORD", "pw"),
        ("URJA_CORS_ORIGINS", "http://x"),
    ):
        clean_env.setenv(name, val)
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "URJA_CORS_ORIGINS" in str(exc.value)


def test_invalid_log_level_exits_cleanly(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("URJA_PORTAL_URL", "https://p.example.test")
    clean_env.setenv("URJA_PORTAL_EMAIL", "a@b.test")
    clean_env.setenv("URJA_PORTAL_PASSWORD", "pw")
    clean_env.setenv("URJA_LOG_LEVEL", "loud")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "URJA_LOG_LEVEL" in str(exc.value)


@pytest.mark.parametrize(("raw", "norm"), [("debug", "DEBUG"), ("Warning", "WARNING")])
def test_log_level_normalised(raw: str, norm: str) -> None:
    s = Settings(
        portal_url="https://x.example.test",
        portal_email="a@b.test",
        portal_password="pw",
        log_level=raw,
        _env_file=None,
    )
    assert s.log_level == norm


def _build(**overrides: object) -> Settings:
    return Settings(
        portal_url="https://x.example.test",  # type: ignore[arg-type]
        portal_email="a@b.test",
        portal_password="pw",  # type: ignore[arg-type]
        _env_file=None,
        **overrides,  # type: ignore[arg-type]
    )


def test_robustness_defaults(settings: Settings) -> None:
    assert (settings.retry_attempts, settings.retry_base_delay_s) == (3, 0.25)
    assert (settings.retry_max_delay_s, settings.retry_after_cap_s) == (4.0, 30.0)
    assert (settings.breaker_failure_threshold, settings.breaker_reset_s) == (5, 30.0)
    assert (settings.ttl_static_s, settings.ttl_readings_s) == (86400.0, 900.0)
    assert settings.cache_max_entries == 10000


@pytest.mark.parametrize(
    "bad",
    [
        {"retry_attempts": 0},
        {"retry_base_delay_s": 0},
        {"retry_max_delay_s": 0.1},  # below the default base of 0.25
        {"retry_base_delay_s": 5.0},  # above the default max of 4.0
        {"retry_after_cap_s": 0},
        {"breaker_failure_threshold": 0},
        {"breaker_reset_s": 0},
        {"ttl_static_s": 0},
        {"ttl_readings_s": -1},
        {"cache_max_entries": 0},
    ],
)
def test_robustness_constraints(bad: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        _build(**bad)


def test_max_delay_equal_to_base_allowed() -> None:
    assert _build(retry_base_delay_s=1.0, retry_max_delay_s=1.0).retry_max_delay_s == 1.0


def test_model_level_error_names_the_fields(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("URJA_PORTAL_URL", "https://p.example.test")
    clean_env.setenv("URJA_PORTAL_EMAIL", "a@b.test")
    clean_env.setenv("URJA_PORTAL_PASSWORD", "pw")
    clean_env.setenv("URJA_RETRY_BASE_DELAY_S", "9")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    msg = str(exc.value)
    assert "URJA_RETRY_MAX_DELAY_S" in msg and "URJA_RETRY_BASE_DELAY_S" in msg
    assert "URJA_?" not in msg


def _required(**extra: object) -> Settings:
    return Settings(
        portal_url="https://p.example.test",  # type: ignore[arg-type]
        portal_email="a@b.test",
        portal_password="pw",  # type: ignore[arg-type]
        _env_file=None,
        **extra,  # type: ignore[arg-type]
    )


def test_sync_settings_defaults() -> None:
    s = _required()
    assert (s.sync_on_startup, s.sync_readings_on_startup, s.sync_concurrency) == (True, True, 4)


@pytest.mark.parametrize("value", [0, 5])
def test_sync_concurrency_is_limited_to_1_to_4(value: int) -> None:
    with pytest.raises(ValidationError):
        _required(sync_concurrency=value)


def test_portal_max_rps_default_and_bounds() -> None:
    assert _required().portal_max_rps == 1.5
    for bad in (0, -1, 20.5):
        with pytest.raises(ValidationError):
            _required(portal_max_rps=bad)


def test_anomaly_threshold_defaults(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings(
        portal_url="https://p.example.test",  # type: ignore[arg-type]
        portal_email="a@b.test",
        portal_password="pw",  # type: ignore[arg-type]
        _env_file=None,
    )
    assert (s.anomaly_voltage_min_v, s.anomaly_voltage_max_v) == (207.0, 253.0)
    assert s.anomaly_flatline_hours == 6.0
    assert s.anomaly_spike_sigma == 4.0
    assert s.anomaly_spike_min_points == 24
    assert s.anomaly_inactive_min_kwh == 0.5


def test_anomaly_voltage_min_must_be_below_max(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("URJA_PORTAL_URL", "https://p.example.test")
    clean_env.setenv("URJA_PORTAL_EMAIL", "a@b.test")
    clean_env.setenv("URJA_PORTAL_PASSWORD", "pw")
    clean_env.setenv("URJA_ANOMALY_VOLTAGE_MIN_V", "250")
    clean_env.setenv("URJA_ANOMALY_VOLTAGE_MAX_V", "250")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "URJA_ANOMALY_VOLTAGE_MIN_V" in str(exc.value)
    assert "URJA_ANOMALY_VOLTAGE_MAX_V" in str(exc.value)


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("anomaly_flatline_hours", 0),
        ("anomaly_spike_sigma", 0),
        ("anomaly_spike_min_points", 1),
        ("anomaly_inactive_min_kwh", -1),
    ],
)
def test_anomaly_thresholds_are_validated(name: str, bad: float) -> None:
    with pytest.raises(ValidationError):
        Settings(
            portal_url="https://p.example.test",  # type: ignore[arg-type]
            portal_email="a@b.test",
            portal_password="pw",  # type: ignore[arg-type]
            _env_file=None,
            **{name: bad},
        )
