"""AsyncioTaskRunner: runs background coroutines and keeps them from being garbage-collected."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("urja.tasks")


class AsyncioTaskRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def active(self) -> int:
        """Number of tasks still running."""
        return len(self._tasks)

    def spawn(self, name: str, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)  # the loop keeps only weak references to tasks
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("background task %s failed", task.get_name(), exc_info=exc)

    async def aclose(self, timeout_s: float = 10.0) -> None:
        """Cancel every running task and wait up to `timeout_s` for them to finish."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=timeout_s)
        for task in pending:
            logger.warning(
                "background task %s did not stop within %.1fs", task.get_name(), timeout_s
            )
