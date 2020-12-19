#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform

meta = {
    'name': 'player',
    'requirements': [
    ]
}

global config

def init(platform: PyXIVPlatform.XIVPlatform):
    global config
    config = platform.load_config(meta['name'])
    logging.info(__file__)

init(PyXIVPlatform.instance)