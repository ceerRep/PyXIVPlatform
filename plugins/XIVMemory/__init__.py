#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform
import CommandHelper

from .config import config_init, get_config
from .memoryscanner import *

__all__ = ["meta", "instance"]

meta = {
    'name': 'XIVMemory',
    'requirements': [
        "CommandHelper"
    ]
}

async def command_config(platform: PyXIVPlatform.XIVPlatform, params: List[str]):
    if not (2 <= len(params) <= 3):
        return "Usage: %s name [value]" % params[0]

    config = get_config()
    if params[1] not in config:
        return "None"
    else:
        if len(params) == 3:
            try:
                config[params[1]] = float(params[2])
                platform.save_config(__package__, config)
            except Exception as e:
                return str(e)
        return str(config[params[1]])


def init(platform: PyXIVPlatform.XIVPlatform):
    platform.save_config(__package__,
                         config_init(platform.load_config(__package__)))
    scanner = MemoryScanner()
    scanner.start_scan()

    cmd_helper: CommandHelper.CommandHelper = CommandHelper.instance
    cmd_helper.add_command(
        "memoryconfig", lambda params: command_config(platform, params)
    )

    logging.info(__package__)
    return scanner

instance: MemoryScanner = init(PyXIVPlatform.instance)