#! /usr/bin/env python3

import asyncio
from asyncio.log import logger
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
        self.signatures: Dict[str, bytes] = {}
        self.add_signature('player_name', config['player_name_signature'])

    def add_callback(self, callback: Callable[[XIVProcess], Awaitable]):
        self.callbacks.append(callback)
    
    def add_signature(self, name: str, value: str):
        self.signatures[name] = b''.join(
            [
                (b'(' if mark else b'') +
                b'|'.join(map(lambda x: rb'\x' + x, part2s)) +
                (b')' if mark else b'')
                for part1 in value.encode().split()
                if [
                    part2s := part1.split(b'|'),
                    mark := len(part2s) > 1
                ]
            ]
        ).replace(rb'\x??', b'.')

    def start_scan(self):
        if not self.scanning:
            self.scanning = True
            asyncio.create_task(self.scan())

    async def scan(self):
        while self.scanning:
            try:
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
            except Exception as e:
                logging.info(traceback.format_exception(e))
                await asyncio.sleep(5)
            
