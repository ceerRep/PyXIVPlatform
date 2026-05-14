#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform

from .memoryscanner import *
from .xivprocess import XIVProcess
from .code_anchor import CodeAnchor, Insn, COND_JUMPS

__all__ = ["meta", "instance", "CodeAnchor", "Insn", "COND_JUMPS", "XIVProcess"]

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