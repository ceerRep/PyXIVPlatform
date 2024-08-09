#! /usr/bin/env python3

import logging
import re
import ast
import asyncio

from typing import *

import player

from .config import config
from .winapi import Winapi
from .keysequence import parse_key


class XIVProcess:
    def __init__(self, signatures: Mapping[str, str]) -> None:
        self.hwnd = Winapi.find_window("FFXIVGAME", None)
        self.signatures: Mapping[str, bytes] = signatures
        self.signature_offsets: Dict[str, int] = {}
        self.inited = False

        if not config["find_xiv_by_player_name"]:
            self.hwnd = Winapi.find_window("FFXIVGAME", None)
            self.pid = Winapi.get_window_pid(self.hwnd)
            self.handle = Winapi.open_process(self.pid)
            self.base_address, self.base_size = Winapi.get_module_info(
                self.handle, "ffxiv_dx11.exe")
            self.base_image: bytes = Winapi.read_process_memory(
                self.handle, self.base_address, self.base_size)
            self.inited = True
        else:
            self.hwnd = Winapi.find_window_ex(None, None, "FFXIVGAME", None)

            while self.hwnd:
                self.pid = Winapi.get_window_pid(self.hwnd)
                self.handle = Winapi.open_process(self.pid)
                self.base_address, self.base_size = Winapi.get_module_info(
                    self.handle, "ffxiv_dx11.exe")
                self.base_image: bytes = Winapi.read_process_memory(
                    self.handle, self.base_address, self.base_size)

                # address = self.follow_pointer_path(
                #     [*map(ast.literal_eval,
                #           config['player_name_path'])],
                #     self.find_signature('player_name')
                # )
                # buffer = Winapi.read_process_memory(self.handle, address, 64)
                Winapi.close_handle(self.handle)
                # buffer = buffer[:buffer.find(b'\x00')]

                if (player.config["name"].encode('utf-8') + b'\0') in self.base_image:
                    break

                # if player.config["name"] == buffer.decode('utf-8'):
                #     break

                self.hwnd = Winapi.find_window_ex(
                    None, self.hwnd, "FFXIVGAME", None)
            else:
                self.pid = 0
                self.handle = 0
                self.base_address, self.base_size = 0, 0
                self.base_image = b''

            if self.hwnd:
                self.inited = True

                # print log
                # self.find_signature('player_name')

    def __enter__(self) -> 'XIVProcess':
        self.handle = Winapi.open_process(self.pid)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        Winapi.close_handle(self.handle)

    def find_signature(self, name: str) -> int:
        if name in self.signature_offsets:
            return self.signature_offsets[name]
        
        signature_bytes = self.signatures[name]

        match = re.search(signature_bytes, self.base_image)

        if match is None:
            if self.inited:
                logging.info(f"Signature resolve failed: {name}, pattern {signature_bytes}")
            self.signature_offsets[name] = 0
        else:
            addr = match.span(0)[0]
            if self.inited:
                logging.info(f"Signature resolved: {name} at {addr:08x}")
            self.signature_offsets[name] = addr

        return self.signature_offsets[name]

    def is_valid(self) -> bool:
        return Winapi.is_process_handle_valid(self.handle)

    def get_base_address(self):
        return self.base_address

    def follow_pointer_path(self, address: List[int], inst_pos: int = 0) -> int:
        base = address[0] + self.get_base_address()

        for offset in address[1:]:
            if inst_pos == 0:
                base = int.from_bytes(
                    self.read_memory(base, 8),
                    "little",
                    signed=False
                )
            else:
                base = base + inst_pos
                base = base + 4 + int.from_bytes(
                    self.read_memory(base, 4),
                    "little",
                    signed=True
                )
                inst_pos = 0
            if base == 0:
                return 0
            base += offset

        return base

    def read_memory(self, address: int, size: int) -> bytearray:
        return Winapi.read_process_memory(self.handle, address, size)

    def write_memory(self, address: int, buffer: bytes) -> bool:
        return Winapi.write_process_memory(self.handle, address, buffer)

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
