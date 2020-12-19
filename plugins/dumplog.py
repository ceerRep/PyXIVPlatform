#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform
import LogScanner

meta = {
    'name': 'DumpLog',
    'requirements': [
        "LogScanner"
    ]
}


async def dump(log: LogScanner.XIVLogLine, process):
    if log.new:
        logging.info("%x %s", log.type, '|'.join(log.fields))


def init(platform: PyXIVPlatform.XIVPlatform):
    logscanner: LogScanner.XIVLogScanner = LogScanner.instance
    logscanner.log_listener(dump)
    logging.info(__file__)

init(PyXIVPlatform.instance)