#! /usr/bin/env python3

import logging

import PyXIVPlatform
import LogScanner
from LogScanner.log_types import LogType
import PostNamazuWrapper
import player

from .action_dispatcher import ActionDispatcher

__all__ = ["meta", "instance"]

meta = {
    'name': 'ActionSender',
    'requirements': [
        "LogScanner",
        "PostNamazuWrapper",
        "player",
    ]
}


def init():
    config = PyXIVPlatform.instance.load_config(__package__)
    dispatcher = ActionDispatcher(
        PostNamazuWrapper.instance,
        config["delay_after_action"],
        config,
    )

    async def on_log(log: LogScanner.XIVLogLine, process):
        if log.new:
            content = log.fields[1]
            if log.type & LogType.SYSTEM_FLAG:
                player_name_in_content = (
                    player.config["name"] in content
                    or content.strip().startswith("You")
                )
                dispatcher.on_log_confirm(content, player_name_in_content)

    LogScanner.instance.log_listener(on_log)
    logging.info(__package__)
    return dispatcher


instance: ActionDispatcher = init()
