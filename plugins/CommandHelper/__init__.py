#! /usr/bin/env python3

import sys
import logging
import asyncio
import PyXIVPlatform
from typing import List

from .command import CommandHelper

__all__ = ["meta", "instance"]

meta = {
    'name': 'CommandHelper',
    'requirements': [
    ]
}

async def cmd_echo(params: List[str]):
    return ' '.join(params[1]) + '\n'


async def cmd_exit(params: List[str]):
    asyncio.get_event_loop().stop()
    logging.info("Press enter to exit")
    return ""


def init(platform: PyXIVPlatform.XIVPlatform):
    global instance

    cmd_helper = CommandHelper()
    instance = cmd_helper
    
    cmd_helper.add_stream(sys.stdin, sys.stdout)

    cmd_helper.add_command("echo", cmd_echo)
    cmd_helper.add_command(
        "exit", cmd_exit
    )

    logging.info(__package__)

    return cmd_helper

instance = init(PyXIVPlatform.instance)