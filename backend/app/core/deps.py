"""Composition root: the only place concrete classes are wired into the app.

Tests swap implementations through `app.dependency_overrides`.
"""

from fastapi import FastAPI, Request

from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.interfaces import Clock


def wire(app: FastAPI, settings: Settings) -> None:
    """Attach settings and concrete collaborators to the app state."""
    app.state.settings = settings
    app.state.clock = SystemClock()


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock
