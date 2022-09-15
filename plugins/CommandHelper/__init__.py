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


async def cmd_test(params: List[str]):
    import ast
    import PostNamazuWrapper
    await PostNamazuWrapper.instance.send_bytes_cmd(b' '.join(map(ast.literal_eval, params[1:])))
    return ''


async def cmd_echo(params: List[str]):
    return ' '.join(params[1:]) + '\n'


async def cmd_exit(params: List[str]):
    asyncio.get_event_loop().stop()
    logging.info("Press enter to exit")
    return ""

class StdioWrapper:
    @staticmethod
    def readline():
        print("> ", end='', flush=True)
        return sys.stdin.readline()
    
    @staticmethod
    def write(msg: str):
        logging.info(msg)
        return len(msg)
    
    @staticmethod
    def flush():
        return sys.stdout.flush()

def init(platform: PyXIVPlatform.XIVPlatform):
    global instance

    cmd_helper = CommandHelper()
    instance = cmd_helper
    
    stdio = StdioWrapper()
    cmd_helper.add_stream(stdio, stdio)

    cmd_helper.add_command("echo", cmd_echo)
    cmd_helper.add_command("exit", cmd_exit)
    cmd_helper.add_command("test", cmd_test)

    logging.info(__package__)

    return cmd_helper

instance = init(PyXIVPlatform.instance)
