#! /usr/bin/env python3

from asyncio.queues import Queue
import enum
import logging
from typing import Dict, List, Optional
from asyncio import Future
from enum import Enum
from XIVMemory.memoryhelper import *

import os
import ast
import json
import time
import math
import struct
import asyncio

import PyXIVPlatform
import LogScanner
import XIVMemory
import PostNamazu
import CommandHelper
import player


class CraftState(Enum):
    VOID = 0
    NORMAL = 1
    HIGH = 2
    HIGHEST = 3
    LOW = 4


class RoleState(Enum):
    VOID = 0
    IDLE1 = 1
    SITTING = 2
    PENDING = 3
    SITTED = 4
    UNKNOWN5 = 5
    IDLE6 = 6
    UNKNOWN7 = 7
    UNKNOWN8 = 8
    CRAFTING = 9
    BUFFED = 10
    FISH_IDLE = 271
    FISH_FINISHED = 273
    FISH_FISHING0 = 274
    FISH_FISHING1 = 275
    FISH_HOOK_NOTHING = 283
    FISH_HOOK = 284
    FISH_LIGHT_FISH_BAITED = 292
    FISH_HEAVY_FISH_BAITED = 293
    FISH_SPECIAL_FISH_BAITED = 294
    FISH_IDLE_SITTED = 3143
    FISH_FINISHED_SITTED = 3144
    FISH_FISHING_SITTED0 = 3145
    FISH_FISHING_SITTED1 = 3146
    FISH_HOOK_NOTHING_SITTED = 3154
    FISH_HOOK_SITTED = 3155
    FISH_HOOK_HEAVY = 4659
    FISH_HOOK_LIGHT = 4660
    FISH_UNKNOWN_IDLE = 4661  # After 撒饵
    FISH_ASK_COLLECT = 527502


class CraftBot:
    def __init__(self):
        self._config = PyXIVPlatform.instance.load_config(__package__)
        self._retry_count: int = self._config["retry_count"]
        self._retry_timeout: float = self._config["retry_timeout"]
        self._delay_after_action: float = self._config["delay_after_action"]
        self._listening_actions: Dict[str, Future[None]] = dict()
        self._craft_value = 0
        self._craft_state = CraftState.NORMAL
        self._role_value = 0
        self._role_state = RoleState.IDLE1
        self._task: Optional[Future[None]] = None
        self._have_patient = False
        self._collect_threshold = 0.0
        self._change_place_time = 0.0
        self._collect = False
        self._next_can_use_patient = 0
        self._idle_warn = False

        LogScanner.instance.log_listener(self.on_log_arrival)
        XIVMemory.instance.add_signature(
            'craftbot_state', self._config['state_signature'])
        XIVMemory.instance.add_callback(self.memory_scan)
        CommandHelper.instance.add_command("craft", self.on_cmd)
        CommandHelper.instance.add_command("stopcraft", self.on_cmd)
        CommandHelper.instance.add_command("autohandin", self.on_cmd)
        CommandHelper.instance.add_command("autofish", self.on_cmd)
        CommandHelper.instance.add_command("changeplace", self.on_cmd)
        CommandHelper.instance.add_command("jump", self.on_cmd)

    async def use_action(self, action: Union[str, List[str]], retry: int, timeout: float, log_pattern: Optional[str] = None):
        for _ in range(retry):
            if self._role_state == RoleState.SITTED:
                break
            if isinstance(action, str):
                now_action = action
            else:
                now_action = action[self._craft_state.value - 1]
            if now_action:
                pattern = log_pattern if log_pattern else now_action
                try:
                    fut = asyncio.Future()
                    self._listening_actions[pattern] = fut
                    await PostNamazu.instance.send_cmd("/e Preparing {state} -> {now_action}".format(state=self._craft_state,
                                                                                                     now_action=now_action))
                    await PostNamazu.instance.send_cmd("/ac {now_action}".format(now_action=now_action))
                    await asyncio.wait_for(fut, timeout=timeout)
                    await asyncio.sleep(self._delay_after_action)
                except asyncio.TimeoutError:
                    del self._listening_actions[pattern]
                    continue
                else:
                    return True
            return True

        return False

    def setTimeout(self, f: Callable[..., Awaitable], timeout: float):
        async def run():
            await asyncio.sleep(timeout)
            self._task = asyncio.create_task(f())
        self._task = asyncio.create_task(run())

    async def on_log_arrival(self, log: LogScanner.XIVLogLine, process: XIVMemory.XIVProcess):
        if log.new:
            content = log.fields[1]
            if log.type & 0x800:  # system message
                player_name_in_content = player.config["name"] in content
                assert len(self._listening_actions) <= 1
                for sname in self._listening_actions.keys():
                    real_sname = sname
                    if sname[0] == '$':
                        real_sname = sname[1:]
                        player_name_in_content = True
                    if player_name_in_content and (real_sname in content):
                        self._listening_actions.pop(sname).set_result(None)
                        break
            if log.type in [0x8ae, 0x8b0]:
                if player.config["name"] in content:
                    if "采集优质获得率提升" in content:
                        if log.type == 0x8ae:
                            self._have_patient = True
                        else:
                            self._have_patient = False
            if log.type == 0x843:
                if '警惕性很高' in content:
                    if self._task is not None:
                        self._task.cancel()
                        self._task = None

                        async def f():
                            await self.change_place()
                            self._task = asyncio.create_task(self.autofish())
                        self._task = asyncio.create_task(f())
            if log.type == 0x39:
                if '没有进行任何操作，超过10分钟会被强制退出任务' in content:
                    self._idle_warn = True

    async def memory_scan(self, process: XIVMemory.XIVProcess):
        self._process = process

        craftbot_state_sig_offset = process.find_signature('craftbot_state')

        if not craftbot_state_sig_offset:
            return

        offset_state = process.follow_pointer_path(
            [*map(ast.literal_eval, self._config['state_offset'])],
            craftbot_state_sig_offset
        )

        offset_quality = process.follow_pointer_path(
            [*map(ast.literal_eval, self._config['quality_offset'])],
            craftbot_state_sig_offset
        )

        state = cast_int(process.read_memory(offset_state, 4))

        old_role_state = self._role_state
        old_craft_state = self._craft_state

        try:
            self._role_state = RoleState(state)
        except:
            if self._role_value != state:
                logging.error(
                    "Unknown role state: {state}".format(state=state))
            self._role_state = RoleState.IDLE6

        self._role_value = state

        if self._role_state != old_role_state:
            logging.info("Role changed {old_role} -> {new_role}".format(
                old_role=old_role_state, new_role=self._role_state))

        if self._role_state == RoleState.PENDING:
            self._craft_state = CraftState.NORMAL
        else:
            try:
                state = cast_int(process.read_memory(offset_quality, 4))
                self._craft_state = CraftState(state)
            except:
                if self._craft_state != state:
                    logging.error(
                        "Unknown craft state: {state}".format(state=state))
                self._craft_state = CraftState.NORMAL

            self._craft_value = state

            if self._craft_state != old_craft_state:
                logging.info(f"Craft state changed {old_craft_state} -> {self._craft_state}")

    async def craft(self, recipe: str, num: int):
        with open(os.path.join(self._config["recipes_dir"], recipe + ".json"), encoding="utf-8") as fin:
            recipe = json.load(fin)

        for i in range(num):
            await asyncio.sleep(2)

            await PostNamazu.instance.send_cmd(
                "/e Crafting: {i}/{num}".format(i=i, num=num)
            )

            while self._role_state == RoleState.CRAFTING:
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)

            now_state = self._role_state
            while (self._role_state == now_state and
                    self._role_state not in (RoleState.PENDING, RoleState.CRAFTING)):
                # logging.info(self._role_state)
                await self._process.send_key("NUMPAD0")
                await asyncio.sleep(0.1)

            while self._role_state != RoleState.PENDING and \
                    self._role_state != RoleState.CRAFTING:
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.2)

            for action in recipe:
                await self.use_action(action, self._retry_count, self._retry_timeout)
                if self._role_state == RoleState.SITTED:
                    break

        await PostNamazu.instance.send_cmd("/e Craft stopped")

    async def change_place(self):

        key = 'q' if self._change_place_time < 0 else 'e'
        await self._process.send_key(key)
        await asyncio.sleep(3)

        time = abs(self._change_place_time)
        await self._process.send_key(key, True, False)
        await asyncio.sleep(time)
        await self._process.send_key(key, False, True)
        self._change_place_time = -self._change_place_time

    async def autofish(self):
        while True:

            if self._idle_warn:
                await self.change_place()
                self._idle_warn = False

            # if not self._have_patient:
            #     if time.time() > self._next_can_use_patient:

            #         while 'FISHING' not in self._role_state.name:
            #             await PostNamazu.instance.send_cmd("/ac 抛竿")
            #             await asyncio.sleep(self._delay_after_action)
            #         while 'FISHING' in self._role_state.name:
            #             await PostNamazu.instance.send_cmd("/ac 提钩")
            #             await asyncio.sleep(self._delay_after_action)

            #         await asyncio.sleep(2)

            #         success = await self.use_action("耐心II", self._retry_count, self._retry_timeout, "采集优质获得率提升")
            #         if success:
            #             self._next_can_use_patient = time.time() + 560 / 7 * 3

            # await PostNamazu.instance.send_cmd("/e CD: {sec:.2f}s".format(sec=(self._next_can_use_patient - time.time())))

            if self._have_patient and not self._collect:
                self._collect = True
                await self.use_action("收藏品采集", self._retry_count, self._retry_timeout)

            if not self._have_patient and self._collect:
                self._collect = False
                await self.use_action("收藏品采集", self._retry_count, self._retry_timeout)

            await asyncio.sleep(self._delay_after_action)
            await PostNamazu.instance.send_cmd("/ac 以小钓大")
            await PostNamazu.instance.send_cmd("/ac 以小钓大II")

            while 'FISHING' not in self._role_state.name:
                await PostNamazu.instance.send_cmd("/ac 抛竿")
                await asyncio.sleep(self._delay_after_action)

            start_time = time.time()

            while 'FISHING' in self._role_state.name:
                await asyncio.sleep(0.1)

            end_time = time.time()

            elapsed_sec = end_time - start_time
            await PostNamazu.instance.send_cmd("/e Elapsed time: {sec:.2f}s".format(sec=elapsed_sec))

            await asyncio.sleep(0.5)

            while 'FISH_BAITED' in self._role_state.name:
                success = False
                if self._have_patient:
                    if elapsed_sec >= self._collect_threshold:
                        if 'LIGHT' in self._role_state.name:
                            success = await self.use_action("精准提钩", 1, self._retry_timeout, "$有鱼上钩了")
                        elif 'HEAVY' in self._role_state.name:
                            success = await self.use_action("强力提钩", 1, self._retry_timeout, "$有鱼上钩了")
                        if success:
                            self._next_can_use_patient += 50 / 7 * 3
                if not success:
                    await self.use_action("提钩", 1, self._retry_timeout, "$有鱼上钩了")

            while self._role_state == RoleState.VOID:
                await asyncio.sleep(0.1)

            while 'HOOK' in self._role_state.name:
                await asyncio.sleep(0.1)

            while self._role_state == RoleState.VOID:
                await asyncio.sleep(0.1)

            if self._role_state == RoleState.FISH_ASK_COLLECT:
                while self._role_state == RoleState.FISH_ASK_COLLECT:
                    await self._process.send_key("NUMPAD0")
                    await asyncio.sleep(0.1)

            await asyncio.sleep(self._delay_after_action)

    async def jump(self, timeout: float):
        while True:
            await self._process.send_key("SPACE")
            await asyncio.sleep(timeout)

    async def handin(self, num: int):
        await asyncio.sleep(5)
        for i in range(num):
            await PostNamazu.instance.send_cmd("/e Handin {i}/{num}".format(i=i, num=num))
            await self._process.send_key("NUMPAD0")
            await asyncio.sleep(0.1)
            await self._process.send_key("MULTIPLY")
            await asyncio.sleep(0.1)
            await self._process.send_key("NUMPAD0")
            await asyncio.sleep(0.1)
            await self._process.send_key("NUMPAD0")
            await asyncio.sleep(1)

    def cancel(self):
        if self._task:
            self._listening_actions = dict()
            self._task.cancel()
            self._task = None

    async def on_cmd(self, params: List[str]) -> str:
        if params[0] == 'craft':
            try:
                recipe = params[1]
                num = int(params[2])

                self._task = asyncio.create_task(self.craft(recipe, num))
                return "Crafting"
            except:
                return "Usage: {cmd} recipe num".format(cmd=params[0])
        elif params[0] == 'stopcraft':
            self.cancel()
        elif params[0] == 'autohandin':
            self._task = asyncio.create_task(self.handin(int(params[1])))
        elif params[0] == 'autofish':
            try:
                self._change_place_time = ast.literal_eval(params[1])
                self._collect_threshold = ast.literal_eval(params[2])
                self._task = asyncio.create_task(self.autofish())
            except:
                return "Usage: {cmd} walktime threshold".format(cmd=params[0])
        elif params[0] == 'changeplace':
            try:
                self._change_place_time = ast.literal_eval(params[1])
                await self.change_place()
            except Exception as e:
                return "Usage: {cmd} walktime".format(cmd=params[0])
        elif params[0] == 'jump':
            try:
                self._task = asyncio.create_task(
                    self.jump(ast.literal_eval(params[1])))
            except:
                return "Usage: {cmd} timeout".format(cmd=params[0])
