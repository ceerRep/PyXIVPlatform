#! /usr/bin/env python3

import io
import ast
import sys
import time
import traceback
import asyncio
import logging
from typing import *

from XIVMemory.xivprocess import XIVProcess
from XIVMemory.memoryhelper import *


async def safe_call(func, *args, **kwargs):
    try:
        await func(*args, **kwargs)
    except Exception as e:
        print('[Error] ', e)
        traceback.print_exc()


class XIVRawLogLine:
    def __init__(self, data: bytes, time: float, new: bool):
        self.time = time
        buffer = io.BytesIO(data)
        buffer.seek(0, io.SEEK_END)
        buffer.write(b"\x1F")
        buffer.seek(0)
        self.type = int.from_bytes(buffer.read(4), "little")
        buffer.read(1)
        self.fields: List[bytes] = []
        self.new = new

        field = bytearray()
        while True:
            now = buffer.read(1)
            if len(now) == 0:
                break
            ch = now[0]
            if ch == 0x02:
                now = now + buffer.read(2)
                now = now + buffer.read(now[2])
            elif ch == 0x1F:
                now = b""
                self.fields.append(bytes(field))
                field = bytearray()
            field.extend(now)


class XIVLogLine:
    def __init__(self, data: bytes, time: float, new: bool):
        self.time = time
        buffer = io.BytesIO(data)
        buffer.seek(0, io.SEEK_END)
        buffer.write(b"\x1F")
        buffer.seek(0)
        self.type = int.from_bytes(buffer.read(4), "little")
        buffer.read(1)
        self.fields: List[str] = []
        self.new = new

        field = bytearray()
        while True:
            now = buffer.read(1)
            if len(now) == 0:
                break

            ch = now[0]

            if (ch & 0b11100000) == 0b11000000:
                now = now + buffer.read(1)
            elif (ch & 0b11110000) == 0b11100000:
                now = now + buffer.read(2)
            elif (ch & 0b11111000) == 0b11110000:
                now = now + buffer.read(3)
            else:
                if ch == 0x02:
                    now = now + buffer.read(2)
                    now = now + buffer.read(now[2])
                    if now == b'\x02\x12\x02Y\x03':
                        now = b"@"
                    else:
                        now = b""
                elif ch == 0x1F:
                    now = b""
                    self.fields.append(field.decode("utf-8", errors='ignore'))
                    field = bytearray()
            field.extend(now)


class XIVLogScanner:
    def __init__(self, config: Dict[str, Any]):
        self.first_scan = True
        self.last_log_end = 0

        self._log_listeners: List[Callable[[
            XIVLogLine, XIVProcess],
            Awaitable]] = []
        self._raw_listeners: List[Callable[[
            XIVRawLogLine, XIVProcess],
            Awaitable]] = []
        self._config = config
        self._offset = list(
            map(lambda x: ast.literal_eval(x), config["offset"]))

    async def __process_log(self, ffxiv: XIVProcess, offsets: List[int], buffer: bytes):
        loop = asyncio.get_event_loop()
        for start, end in zip(offsets[:-1], offsets[1:]):
            start -= offsets[0]
            end -= offsets[0]
            if self.first_scan:
                timestamp = float(int.from_bytes(
                    buffer[start:start + 4], "little"))
            else:
                timestamp = time.time()
            raw_line = buffer[start + 4:end]

            raw_log_line = XIVRawLogLine(raw_line, timestamp, not self.first_scan)
            log_line = XIVLogLine(raw_line, timestamp, not self.first_scan)

            for listener in self._raw_listeners:
                loop.create_task(safe_call(listener, raw_log_line, ffxiv))

            for listener in self._log_listeners:
                loop.create_task(safe_call(listener, log_line, ffxiv))

    async def __process_address(self,
                                ffxiv: XIVProcess,
                                first_force_zero: bool,
                                offset_array_start: int,
                                offset_array_end: int,
                                buffer_start: int):
        if (offset_array_end - offset_array_start) // 4 == 0:
            return

        log_offsets_raw = ffxiv.read_memory(
            offset_array_start,
            offset_array_end - offset_array_start)

        if not log_offsets_raw:
            raise RuntimeError("Error reading memory")

        log_offsets = list(map(lambda x: int.from_bytes(x, "little", signed=False),
                               split_into(log_offsets_raw, 4)))

        if first_force_zero:
            log_offsets[0] = 0

        while log_offsets and log_offsets[-1] < log_offsets[0]:
            log_offsets.pop()

        if len(log_offsets) <= 1:
            return

        buffer = ffxiv.read_memory(buffer_start + log_offsets[0],
                                   log_offsets[-1] - log_offsets[0])

        if not buffer:
            raise RuntimeError(
                "Error reading memory {address} {length}".format(
                    address=hex(buffer_start + log_offsets[0]),
                    length=hex(log_offsets[-1] - log_offsets[0])
                ))

        await self.__process_log(ffxiv, log_offsets, buffer)

    async def scan(self, xiv: XIVProcess):
        try:
            base_address = xiv.follow_pointer_path(self._offset)

            if base_address > 20:
                memory = xiv.read_memory(base_address, 100)
                if not memory:
                    raise RuntimeError("Error reading memory")

                lines = int.from_bytes(memory[:4], "little")
                offset_array_start, \
                    offset_array_next, \
                    offset_array_end, \
                    log_start, \
                    log_next, \
                    log_end = map(
                        lambda x: int.from_bytes(
                            x, "little", signed=False),
                        split_into(memory[52:], 8))

                if lines == self.last_log_end:
                    return

                if self.last_log_end > lines:
                    self.last_log_end = 0

                offset = lines - (offset_array_next -
                                  offset_array_start) // 4

                # if lines != self.last_log_end:
                #     print(offset, self.last_log_end, lines)

                if offset > self.last_log_end:
                    self.last_log_end = offset
                    if not self.first_scan:
                        await self.__process_address(xiv,
                                                     False,
                                                     self._last_offset_array_next - 4,
                                                     self._last_offset_array_start + 1000 * 4,
                                                     self._last_log_start
                                                     )

                self._last_offset_array_start = offset_array_start
                self._last_offset_array_next = offset_array_next
                self._last_offset_array_end = offset_array_end
                self._last_log_start = log_start

                await self.__process_address(xiv,
                                             self.last_log_end == offset,
                                             offset_array_start + 4 *
                                             (self.last_log_end -
                                                 offset - 1),
                                             offset_array_start +
                                             (lines - offset) * 4,
                                             log_start)
                self.first_scan = False
                self.last_log_end = lines
        except RuntimeError as e:
            trace_back = sys.exc_info()[2]
            line = trace_back.tb_lineno
            print("%s [%s]" % (e, line))
        except Exception as e:
            print(e)
            traceback.print_exc()

    def raw_listener(self, func):
        self._raw_listeners.append(func)
        return func

    def log_listener(self, func):
        self._log_listeners.append(func)
        return func
