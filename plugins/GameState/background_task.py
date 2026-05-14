#! /usr/bin/env python3

import asyncio
from asyncio import Task
from typing import Callable, Coroutine, Optional


class BackgroundTask:
    def __init__(self):
        self._task: Optional[Task] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, coro: Coroutine) -> Task:
        self.cancel()
        self._task = asyncio.create_task(coro)
        return self._task

    def cancel(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def restart_after(self, delay: float, coro_factory: Callable[[], Coroutine]):
        async def _delayed():
            await asyncio.sleep(delay)
            await coro_factory()
        self.start(_delayed())
