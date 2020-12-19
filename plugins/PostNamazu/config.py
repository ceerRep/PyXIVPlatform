#! /usr/bin/env python3

from typing import *

default_config = {
    "post_namazu_addr": ""
}

global g_config


def config_init(config: Dict[str, Any]) -> Dict[str, Any]:
    global g_config
    g_config = config.copy()

    if not g_config:
        g_config = {}

    for key, value in default_config.items():
        if key not in g_config:
            g_config[key] = value

    return g_config


def get_config() -> Dict[str, Any]:
    return g_config
