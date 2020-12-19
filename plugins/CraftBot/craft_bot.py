#! /usr/bin/env python3

from asyncio.queues import Queue
import logging
from typing import Dict, List, Optional
from asyncio import Future
from enum import Enum
from XIVMemory.memoryhelper import *

import os
import ast
import json
import asyncio
import PyXIVPlatform
import LogScanner
import XIVMemory
import PostNamazu
import CommandHelper
import player


class CraftState(Enum):
    NORMAL = 1
    HIGH = 2
    HIGHEST = 3
    LOW = 4


class RoleState(Enum):
    IDLE1 = 1
    SITTING = 2
    PENDING = 3
    SITTED = 4
    UNKNOWN5 = 5
    IDLE6 = 6
    UNKNOWN7 = 7
    UNKNOWN8 = 8
    CRAFTING = 9
    UNKNOWN10 = 10


class CraftBot:
    def __init__(self):
        self._config = PyXIVPlatform.instance.load_config(__package__)
        self._offset_quality = list(
            map(ast.literal_eval, self._config["offset_quality"]))
        self._offset_state = list(
            map(ast.literal_eval, self._config["offset_state"]))
        self._listening_actions: Dict[str, Future[None]] = dict()
        self._craft_state = CraftState.NORMAL
        self._role_state = RoleState.IDLE1
        self._task: Optional[Future[None]] = None

        LogScanner.instance.log_listener(self.on_log_arrival)
        XIVMemory.instance.add_callback(self.memory_scan)
        CommandHelper.instance.add_command("craft", self.on_cmd)
        CommandHelper.instance.add_command("stopcraft", self.on_cmd)

    async def use_action(self, action: Union[str, List[str]], retry: int, timeout: float):
        for _ in range(retry):
            if isinstance(action, str):
                now_action = action
            else:
                now_action = action[self._craft_state.value - 1]
            if now_action:
                try:
                    fut = asyncio.Future()
                    self._listening_actions[now_action] = fut
                    await PostNamazu.instance.send_cmd("/e 准备发动 {now_action}".format(now_action=now_action))
                    await PostNamazu.instance.send_cmd("/ac {now_action}".format(now_action=now_action))
                    await asyncio.wait_for(fut, timeout=timeout)
                    await asyncio.sleep(0.2)
                except asyncio.TimeoutError:
                    del self._listening_actions[now_action]
                    continue
                else:
                    return True
            return True

        return False

    async def on_log_arrival(self, log: LogScanner.XIVLogLine, process: XIVMemory.XIVProcess):
        if log.new:
            content = log.fields[1]
            if log.type in [0x842, 0x82b]:
                if player.config["name"] in content:
                    for sname in self._listening_actions.keys():
                        if sname in content:
                            self._listening_actions.pop(sname).set_result(None)
                            break

    async def memory_scan(self, process: XIVMemory.XIVProcess):
        self._process = process

        state = cast_int(process.read_memory(
            process.follow_pointer_path(self._offset_state), 4))

        try:
            self._role_state = RoleState(state)
        except:
            self._role_state = RoleState.IDLE6

        if self._role_state != RoleState.CRAFTING:
            self._craft_state = CraftState.NORMAL
        else:
            self._craft_state = CraftState(
                cast_int(
                    process.read_memory(
                        process.follow_pointer_path(self._offset_quality), 4)))

    async def craft(self, recipe: str, num: int):
        with open(os.path.join(self._config["recipes_dir"], recipe + ".json"), encoding="utf-8") as fin:
            recipe = json.load(fin)

        for i in range(num):
            await asyncio.sleep(2)

            await PostNamazu.instance.send_cmd(
                "/e Crafting: {i}/{num}".format(i=i, num=num)
            )
            
            while self._role_state.value > RoleState.PENDING.value:
                logging.info(self._role_state)
                await self._process.send_key("NUMPAD0")
                await asyncio.sleep(0.1)

            while self._role_state != RoleState.PENDING and \
                    self._role_state != RoleState.CRAFTING:
                await asyncio.sleep(0.1)

            for action in recipe:
                await self.use_action(action, 3, 3.5)
        
        await PostNamazu.instance.send_cmd("/e Craft stopped")

    async def on_cmd(self, params: List[str]) -> str:
        if params[0] == 'craft':
            try:
                recipe = params[1]
                num = int(params[2])

                self._task = asyncio.ensure_future(self.craft(recipe, num))
                return "Crafting"
            except:
                return "Usage: {cmd} recipe num".format(cmd=params[0])
        elif params[0] == 'stopcraft':
            if self._task:
                self._task.cancel()
                self._listening_actions = dict()
                self._task = None
