#! /usr/bin/env python3

import atexit
import logging
from typing import *

import PyXIVPlatform
import XIVMemory
import CommandHelper

from .postnamazu import PostNamazuWrapper

__all__ = ["meta", "instance"]

meta = {
    'name': 'PostNamazuWrapper',
    'requirements': [
        "LogScanner",
        "CommandHelper",
        "XIVMemory"
    ]
}


def init(platform: PyXIVPlatform.XIVPlatform):
    namazu = PostNamazuWrapper()
    CommandHelper.instance.add_command("do_cmd", namazu.cmd_do_cmd)
    logging.info(__package__)
    return namazu


instance: PostNamazuWrapper = init(PyXIVPlatform.instance)
