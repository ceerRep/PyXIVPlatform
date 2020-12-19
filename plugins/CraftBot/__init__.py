#! /usr/bin/env python3

import logging
from typing import *

from .craft_bot import CraftBot

meta = {
    'name': 'CraftBot',
    'requirements': [
        "XIVMemory",
        "LogScanner",
        "PostNamazu",
        "player"
    ]
}

def init():
    craftbot =  CraftBot()
    logging.info(__package__)
    return craftbot

init()