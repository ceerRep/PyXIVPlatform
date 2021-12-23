#! /usr/bin/env python3

import io
import asyncio
import inspect
import traceback
from io import TextIOBase

from typing import *


class CommandHelper:
    def __init__(self):
        self.queue = asyncio.Queue(0)
        self.callbacks: Dict[str, Callable[[List[str]], Awaitable[str]]] = {}
        asyncio.create_task(self.cmd_loop())

    async def read_loop(self, input_stream: io.TextIOBase, output_stream: io.TextIOBase):
        while True:
            if inspect.iscoroutinefunction(input_stream.readline):
                line = await input_stream.readline()
            else:
                line = await asyncio.get_event_loop().run_in_executor(None, input_stream.readline)

            if not line:
                break

            await self.queue.put((line, output_stream))

    def add_stream(self, input_stream: io.TextIOBase, output_stream: io.TextIOBase):
        asyncio.create_task(self.read_loop(input_stream, output_stream))

    def add_command(self, name: str, callback: Callable[[List[str]], Awaitable[str]]):
        self.callbacks[name] = callback

    async def emit(self, line: str) -> str:
        params = line.split()

        if params:
            if params[0] not in self.callbacks:
                return "%s is not a command" % params[0]

            try:
                ret = self.callbacks[params[0]](params)
                if isinstance(ret, Awaitable):
                    ret = await ret
                return ret or ""
            except Exception as e:
                return "Exception occured: %s %s" % (e,
                                                     traceback.format_exc())

        return ""

    async def cmd_loop(self):
        while True:
            line, output = await self.queue.get()
            line: str
            output: TextIOBase

            task = asyncio.create_task(self.emit(line))
            task.add_done_callback(lambda x: x.result() and (
                output.write(x.result()),
                output.flush()))
