#! /usr/bin/env python3

import atexit
import logging
from typing import *

import PyXIVPlatform
import XIVMemory

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
    logging.info(__package__)
    return namazu


instance: PostNamazuWrapper = init(PyXIVPlatform.instance)
