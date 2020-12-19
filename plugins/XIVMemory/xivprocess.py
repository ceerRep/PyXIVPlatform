#! /usr/bin/env python3

import asyncio

from typing import *

from .config import get_config
from .winapi import Winapi
from .keysequence import parse_key


class XIVProcess:
    def __init__(self) -> None:
        self.hwnd = Winapi.find_window("FFXIVGAME", None)
        self.pid = Winapi.get_window_pid(self.hwnd)

    def __enter__(self) -> 'XIVProcess':
        self.handle = Winapi.open_process(self.pid)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        Winapi.close_handle(self.handle)

    def get_base_address(self):
        return Winapi.get_module_base_address(self.handle, "ffxiv_dx11.exe")

    def follow_pointer_path(self, address: List[int]) -> int:
        base = address[0] + self.get_base_address()

        for offset in address[1:]:
            base = int.from_bytes(
                self.read_memory(base, 8),
                "little",
                signed=False
            )
            if base == 0:
                return 0
            base += offset

        return base

    def read_memory(self, address: int, size: int) -> bytearray:
        return Winapi.read_process_memory(self.handle, address, size)

    async def send_key(self, sequence: str):
        delay = get_config()["key_press_delay"]
        sequence = parse_key(sequence)

        for key in sequence:
            Winapi.send_message(self.hwnd,
                                0x0100,  # WM_KEYDOWN
                                key,
                                0)
            await asyncio.sleep(delay)

        for key in sequence[::-1]:
            Winapi.send_message(self.hwnd,
                                0x0101,  # WM_UP
                                key,
                                0)
            await asyncio.sleep(delay)
