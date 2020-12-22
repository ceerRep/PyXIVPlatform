#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform

from .postnamazu import PostNamazu

__all__ = ["meta", "instance"]

meta = {
    'name': 'PostNamazu',
    'requirements': [
        "LogScanner",
        "CommandHelper"
    ]
}


def init(platform: PyXIVPlatform.XIVPlatform):
    namazu = PostNamazu()
    logging.info(__package__)
    return namazu


instance: PostNamazu = init(PyXIVPlatform.instance)
