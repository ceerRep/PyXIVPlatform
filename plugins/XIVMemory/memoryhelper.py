#! /usr/bin/env python3

import struct
from typing import *


def cast_int(x): return int.from_bytes(x, "little", signed=True)
def cast_uint(x): return int.from_bytes(x, "little", signed=False)


def split_into(buffer: List, size: int):
    return [buffer[i:i + size] for i in range(0, len(buffer), size)]
