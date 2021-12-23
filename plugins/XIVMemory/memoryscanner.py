#! /usr/bin/env python3

import asyncio
import logging
import traceback
from typing import *

from .config import config
from .memoryhelper import *
from .xivprocess import XIVProcess

class MemoryScanner:
    def __init__(self):
        self.scanning = False
        self.config = config
        self.callbacks: List[Callable[[XIVProcess], Awaitable]] = []
        self.signatures: Dict[str, str] = {
            'player_name': config['player_name_signature']
        }

    def add_callback(self, callback: Callable[[XIVProcess], Awaitable]):
        self.callbacks.append(callback)
    
    def add_signature(self, name: str, value: str):
        self.signatures[name] = value

    def start_scan(self):
        if not self.scanning:
            self.scanning = True
            asyncio.create_task(self.scan())

    async def scan(self):
        while self.scanning:
            with XIVProcess(self.signatures) as xiv:
                new_handle = False
                while xiv.is_valid():
                    if not new_handle:
                        new_handle = True
                        logging.info("New XIV handle")
                    for callback in self.callbacks:
                        try:
                            await callback(xiv)
                        except Exception as e:
                            logging.error("Exception occured: %s %s",
                                        e,
                                        traceback.format_exc())

                    await asyncio.sleep(self.config['scan_interval'])

                await asyncio.sleep(self.config['scan_interval'])
