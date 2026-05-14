#! /usr/bin/env python3

import logging

import PyXIVPlatform
import XIVMemory

from .game_state import *
from .game_state import GameStateReader
from .background_task import BackgroundTask

__all__ = ["meta", "instance", "BackgroundTask"]

meta = {
    'name': 'GameState',
    'requirements': [
        "XIVMemory",
    ]
}


def init():
    config = PyXIVPlatform.instance.load_config(__package__)
    reader = GameStateReader(config)
    XIVMemory.instance.add_signature('gamestate', config['state_signature'])
    XIVMemory.instance.add_callback(reader.memory_scan)
    logging.info(__package__)
    return reader


instance: GameStateReader = init()
