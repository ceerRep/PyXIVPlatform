#! /usr/bin/env python3

import logging
from typing import *

from .traslator import OpenAITraslator

meta = {
    'name': 'OpenAITraslator',
    'requirements': [
        "XIVMemory",
        "LogScanner",
        "PostNamazuWrapper"
    ]
}

def init():
    traslator = OpenAITraslator()
    logging.info(__package__)
    return traslator

init()
