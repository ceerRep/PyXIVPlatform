#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform

from .memoryscanner import *

__all__ = ["meta", "instance"]

meta = {
    'name': 'XIVMemory',
    'requirements': [
        "CommandHelper"
    ]
}


def init(platform: PyXIVPlatform.XIVPlatform):
    scanner = MemoryScanner()
    scanner.start_scan()

    logging.info(__package__)
    return scanner

instance: MemoryScanner = init(PyXIVPlatform.instance)