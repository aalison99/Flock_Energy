"""A TaskRunner that holds coroutines until a test runs them, so tests control the timing."""

from collections.abc import Coroutine
from typing import Any


class ManualTaskRunner:
    def __init__(self) -> None:
        self.pending: list[tuple[str, Coroutine[Any, Any, None]]] = []
        self.names: list[str] = []

    def spawn(self, name: str, coro: Coroutine[Any, Any, None]) -> None:
        self.names.append(name)
        self.pending.append((name, coro))

    async def run_all(self) -> None:
        while self.pending:
            _, coro = self.pending.pop(0)
            await coro

    async def aclose(self) -> None:
        self.discard()

    def discard(self) -> None:
        """Close coroutines that a test chose not to run (avoids 'never awaited' warnings)."""
        while self.pending:
            self.pending.pop()[1].close()
