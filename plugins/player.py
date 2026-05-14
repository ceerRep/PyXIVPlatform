#! /usr/bin/env python3

import logging
from typing import *

import PyXIVPlatform

meta = {
    'name': 'player',
    'requirements': [
    ]
}

PLACEHOLDER = "<Player Name>"

global config


def init(platform: PyXIVPlatform.XIVPlatform):
    global config
    config = platform.load_config(meta['name'])

    if config.get("name") == PLACEHOLDER:
        name = input("Player name not configured. Enter your character name: ").strip()
        if not name:
            raise ValueError("Player name cannot be empty")
        config["name"] = name
        platform.save_config(meta['name'], {"name": name})
        logging.info("Player name saved: %s", name)

    logging.info(__file__)


init(PyXIVPlatform.instance)
