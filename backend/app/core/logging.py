"""Logging setup: one place that configures the root logger level and format."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def make_formatter() -> logging.Formatter:
    """The formatter used for all application log output."""
    return logging.Formatter(LOG_FORMAT)


def configure_logging(level: str) -> None:
    """Configure root logging at the given level name (idempotent)."""
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT)
    logging.getLogger().setLevel(level.upper())
