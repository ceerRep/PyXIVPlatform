#! /usr/bin/env python3

import asyncio
import CommandHelper

from .logscanner import XIVLogScanner, XIVLogLine

class LogStream:
    def __init__(self, scanner: XIVLogScanner):
        self.queue = asyncio.Queue(0)
        scanner.log_listener(self.on_log_arrival)

    async def on_log_arrival(self, log: XIVLogLine, process):
        if log.new:
            await self.queue.put(log)
    
    async def readline(self) -> str:
        while True:
            log: XIVLogLine = await self.queue.get()
            if log.type == 0x38 and log.fields[1][0] == '/':
                return log.fields[1][1:]
    
    def write(self, *args, **kwargs):
        return
    
    def flush(self):
        pass


