#! /usr/bin/env python3

import asyncio
import logging
import traceback
from typing import *

from .config import get_config
from .memoryhelper import *
from .xivprocess import XIVProcess


class MemoryScanner:
    def __init__(self):
        self.scanning = False
        self.config = get_config()
        self.callbacks: List[Callable[[XIVProcess], Awaitable]] = []

    def add_callback(self, callback: Callable[[XIVProcess], Awaitable]):
        self.callbacks.append(callback)

    def start_scan(self):
        if not self.scanning:
            self.scanning = True
            asyncio.get_event_loop().create_task(self.scan())

    async def scan(self):
        while self.scanning:
            with XIVProcess() as xiv:
                for callback in self.callbacks:
                    try:
                        await callback(xiv)
                    except Exception as e:
                        logging.error("Exception occured: %s %s",
                                      e,
                                      traceback.format_exc())

                await asyncio.sleep(self.config['scan_interval'])
