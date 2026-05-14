#! /usr/bin/env python3

import logging
from .auto_fisher import AutoFisher

meta = {
    'name': 'AutoFisher',
    'requirements': [
        "GameState",
        "ActionSender",
        "LogScanner",
        "PostNamazuWrapper",
        "CommandHelper",
        "player",
    ]
}


def init():
    fisher = AutoFisher()
    logging.info(__package__)
    return fisher


instance = init()
