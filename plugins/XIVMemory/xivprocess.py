#! /usr/bin/env python3

import ast
import asyncio

from typing import *

import player

from .config import config
from .winapi import Winapi
from .keysequence import parse_key


class XIVProcess:
    def __init__(self) -> None:
        self.hwnd = Winapi.find_window("FFXIVGAME", None)

        if not config["find_xiv_by_player_name"]:
            self.hwnd = Winapi.find_window("FFXIVGAME", None)
        else:
            name_offset = ast.literal_eval(config["player_name_offset"])
            now_hwnd = Winapi.find_window_ex(None, None, "FFXIVGAME", None)

            while now_hwnd:
                now_pid = Winapi.get_window_pid(now_hwnd)
                now_handle = Winapi.open_process(now_pid)
                address = Winapi.get_module_base_address(now_handle, "ffxiv_dx11.exe") + name_offset

                buffer = Winapi.read_process_memory(now_handle, address, 64)
                Winapi.close_handle(now_handle)
                buffer = buffer[:buffer.find(b'\x00')]

                if player.config["name"] == buffer.decode('utf-8'):
                    break
            
                now_hwnd = Winapi.find_window_ex(None, now_hwnd, "FFXIVGAME", None)
            
            self.hwnd = now_hwnd
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

    async def send_key(self, sequence: str, press: bool = True, release: bool = True):
        delay = config["key_press_delay"]
        sequence = parse_key(sequence)

        if press:
            for key in sequence:
                Winapi.send_message(self.hwnd,
                                    0x0100,  # WM_KEYDOWN
                                    key,
                                    0)
                await asyncio.sleep(delay)

        if release:
            for key in sequence[::-1]:
                Winapi.send_message(self.hwnd,
                                    0x0101,  # WM_UP
                                    key,
                                    0)
                await asyncio.sleep(delay)
