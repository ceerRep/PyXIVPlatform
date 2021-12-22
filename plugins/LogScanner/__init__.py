#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform
import XIVMemory
import CommandHelper
from .logscanner import *
from .logcommand import LogStream

__all__ = ["meta", "instance"]

meta = {
    'name': 'LogScanner',
    'requirements': [
        "XIVMemory"
    ]
}

def init(platform: PyXIVPlatform.XIVPlatform):
    memoryscanner: XIVMemory.MemoryScanner = XIVMemory.instance
    config = platform.load_config(__package__)
    scanner = XIVLogScanner(config)
    memoryscanner.add_signature('logscanner_log', config['log_signature'])
    memoryscanner.add_callback(scanner.scan)

    stream = LogStream(scanner)
    CommandHelper.instance.add_stream(stream, stream)

    logging.info(__package__)
    return scanner

instance: XIVLogScanner = init(PyXIVPlatform.instance)
