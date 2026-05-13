#! /usr/bin/env python3
"""
XIVProcess — thin wrapper around a running ffxiv_dx11.exe process.

Player-name identification (find_xiv_by_player_name=True)
----------------------------------------------------------
We use the FFXIVClientStructs `PlayerState::Instance()` signature to locate
the logged-in character name without scanning the entire image for a raw
string.

Decoding (verified by attaching to the live process):
  hit + 3       -> start of a 4-byte RIP-relative disp32 operand
  base          = hit + 3 + 4 + disp32   (PlayerState instance, embedded in .data;
                                          NOT a pointer to a heap-allocated instance)
  player_name   = UTF-8 char[] at base+0x01, NUL-terminated
                  (zeros until the player has logged in)

The follow_pointer_path() call uses path [sig_offset, 0x1] with inst_pos=3:
  step 1 (RIP):   base = sig_addr+3 + 4 + read32(sig_addr+3)
  final:          base += 0x1 -> &player_name[0]

Fallback: if the signature is absent or the field at +0x1 is empty (player
not yet logged in, or signature went stale across a patch), we fall back to
a raw-string scan of base_image so the caller still works.
"""

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

                matched = False

                # --- Primary path: resolve player name via PlayerState::Instance() sig ---
                sig_offset = self.find_signature('player_name')
                if sig_offset:
                    try:
                        address = self.follow_pointer_path(
                            [*map(ast.literal_eval, config['player_name_path'])],
                            sig_offset
                        )
                        if address:
                            buffer = Winapi.read_process_memory(self.handle, address, 64)
                            nul = buffer.find(b'\x00')
                            name_from_mem = buffer[:nul].decode('utf-8') if nul != -1 else buffer.decode('utf-8', errors='replace')
                            if name_from_mem == player.config["name"]:
                                logging.info("Player name matched via PlayerState sig in process %d", self.pid)
                                matched = True
                        else:
                            # PlayerState pointer was NULL — player not logged in yet
                            logging.info("PlayerState pointer is NULL (not logged in?) in process %d; falling back", self.pid)
                    except Exception as e:
                        logging.info("PlayerState sig path failed for process %d: %s; falling back", self.pid, e)

                # --- Fallback: scan raw base_image for the player name string ---
                if not matched:
                    if (player.config["name"].encode('utf-8') + b'\0') in self.base_image:
                        logging.info("Player name matched via base_image scan (fallback) in process %d", self.pid)
                        matched = True

                Winapi.close_handle(self.handle)

                if matched:
                    break

                self.hwnd = Winapi.find_window_ex(
                    None, self.hwnd, "FFXIVGAME", None)
            else:
                self.pid = 0
                self.handle = 0
                self.base_address, self.base_size = 0, 0
                self.base_image = b''

            if self.hwnd:
                self.inited = True

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
        """Resolve a chain of pointer/RIP-relative steps.

        address[0]  — initial offset added to base_address (NOT a deref step).
        address[1:] — one step per element:
            inst_pos != 0  (first step only):
                RIP-relative decode:
                    base += inst_pos          # skip to the disp32 field
                    base  = base + 4 + read32(base, signed=True)  # follow disp32
                    inst_pos is cleared to 0 after this step.
            inst_pos == 0:
                Pointer dereference:
                    base = read64(base)       # follow the pointer
            Then in both cases:  base += offset  (the current element's value).

        A zero base at any step causes an early return of 0 (NULL guard).
        """
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
