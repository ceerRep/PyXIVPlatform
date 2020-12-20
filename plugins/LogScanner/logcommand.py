#! /usr/bin/env python3

import logging
import asyncio

from .logscanner import XIVLogScanner, XIVLogLine

import PostNamazu


class LogStream:
    def __init__(self, scanner: XIVLogScanner):
        self.queue = asyncio.Queue(0)
        scanner.log_listener(self.on_log_arrival)
        scanner.log_filter(LogStream.log_filter)

    @staticmethod
    def log_filter(log: XIVLogLine) -> bool:
        if log.type == 0x38 and log.fields[1].startswith('[BOT]'):
            return False
        return True

    async def on_log_arrival(self, log: XIVLogLine, process):
        if log.new:
            await self.queue.put(log)

    async def readline(self) -> str:
        while True:
            log: XIVLogLine = await self.queue.get()
            if log.type == 0x38 and log.fields[1][0] == '/':
                return log.fields[1][1:]

    @staticmethod
    def write(msg: str):
        logging.info(msg)
        asyncio.ensure_future(PostNamazu.instance.send_cmd("/e [BOT] {msg}".format(msg=msg)))
        return len(msg)

    @staticmethod
    def flush():
        pass
