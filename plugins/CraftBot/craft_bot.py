#! /usr/bin/env python3

from asyncio.queues import Queue
import enum
import logging
from typing import Dict, List, Optional
from asyncio import Task, Future
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
import PostNamazuWrapper
import CommandHelper
import player


# --------------------------------------------------------------------------
# CraftState
#
# Read from G+0x38 via config quality_offset=["0x02","0x38"], i.e. the 15th
# slot (Src[14]) of the global uint32[] timeline array reached through
# state_signature. The field empirically reads 1/2/3/4 (Normal/Good/Excellent/
# Poor) during synthesis, but no IDA xref proves the slot is actually the
# crafting condition byte — a future patch may shift it. See the open
# questions list in AGENTS.md.
#
# Modern alternatives (no raw memory scan):
#   EventFramework -> CraftEventHandler.Condition
#   AddonSynthesis.AtkValues[12].Int
# Both are used by PunishXIV/Artisan.
# --------------------------------------------------------------------------
class CraftState(Enum):
    VOID = 0
    NORMAL = 1
    HIGH = 2
    HIGHEST = 3
    LOW = 4


# --------------------------------------------------------------------------
# RoleState
#
# Subset of ActionTimelineId values that PyXIVPlatform's craft / fish state
# machines actually act on — not an exhaustive enumeration of the table.
#
# IDs come from the game's ActionTimeline.csv (see thewakingsands/
# ffxiv-datamining-cn or xivapi/ffxiv-datamining; both regions are kept
# byte-identical at the data level, so either CSV is authoritative).
#
# How the value is read:
#   state_signature resolves to a global uint32[] timeline array G.
#   G+0x00 = Src[0] = currently-playing ActionTimelineId.
#   The game updates G via memmove(G, src, 4*count) on every action change.
#
# When a new patch shifts a fishing / sitting / crafting animation, the
# right fix is almost always to look up the new row in ActionTimeline.csv —
# not to re-scan the signature.
# --------------------------------------------------------------------------
class RoleState(Enum):
    VOID = 0
    IDLE1 = 1            # ActionTimeline 1:  normal/idle_loop
    SITTING = 2          # ActionTimeline 2:  normal/idle
    PENDING = 3          # ActionTimeline 3:  normal/idle_inactive (crafting open)
    SITTED = 4           # ActionTimeline 4:  normal/idle_inactive (crafting result)
    UNKNOWN5 = 5         # ActionTimeline 5:  normal/turn_loop_l (未确认语义)
    IDLE6 = 6            # ActionTimeline 6:  normal/turn_loop_r
    UNKNOWN7 = 7         # ActionTimeline 7:  (Name 空，合法 timeline)
    UNKNOWN8 = 8         # ActionTimeline 8:  (Name 空，合法 timeline)
    CRAFTING = 9         # ActionTimeline 9:  (Name 空，制作中)
    BUFFED = 10          # ActionTimeline 10: (Name 空，制作中有 buff)
    FISH_IDLE = 271               # ActionTimeline 271:  fishing/idle_loop
    FISH_FINISHED = 273           # ActionTimeline 273:  fishing/finish
    FISH_FISHING0 = 274           # ActionTimeline 274:  fishing/casting
    FISH_FISHING1 = 275           # ActionTimeline 275:  fishing/casting_loop
    FISH_HOOK_NOTHING = 283       # ActionTimeline 283:  fishing/miss
    FISH_HOOK = 284               # ActionTimeline 284:  fishing/hooking
    # 注意：以下三个命名存在误导，但 autofish 用 'LIGHT'/'HEAVY'/'BAITED' in name
    # 做字符串匹配，不得改名，否则 autofish 逻辑会断。
    FISH_LIGHT_FISH_BAITED = 292   # ActionTimeline 292:  fishing/hit_excite（命名误导：实际是 excite 咬钩，autofish 用 'LIGHT' in name 匹配精准提钩，故不改名）
    FISH_HEAVY_FISH_BAITED = 293   # ActionTimeline 293:  fishing/hit_strike（命名误导：实际是 strike 咬钩，autofish 用 'HEAVY' in name 匹配力提钩，故不改名）
    FISH_SPECIAL_FISH_BAITED = 294 # ActionTimeline 294:  fishing/hit_bite（命名误导：实际是 bite 咬钩，autofish 用 'BAITED' in name 匹配普通提钩，故不改名）
    FISH_IDLE_SITTED = 3143           # ActionTimeline 3143: fishing_chair/idle_loop
    FISH_FINISHED_SITTED = 3144       # ActionTimeline 3144: fishing_chair/finish
    FISH_FISHING_SITTED0 = 3145       # ActionTimeline 3145: fishing_chair/casting
    FISH_FISHING_SITTED1 = 3146       # ActionTimeline 3146: fishing_chair/casting_loop
    FISH_HOOK_NOTHING_SITTED = 3154   # ActionTimeline 3154: fishing_chair/miss
    FISH_HOOK_SITTED = 3155           # ActionTimeline 3155: fishing_chair/hooking
    FISH_HOOK_HEAVY = 4659            # ActionTimeline 4659: fishing/powerful_hooking
    FISH_HOOK_LIGHT = 4660            # ActionTimeline 4660: fishing/precision_hooking
    FISH_UNKNOWN_IDLE = 4661          # ActionTimeline 4661: fishing/idle_after_bait（撒饵后空闲）
    # 7.x 新增——钓鱼立位
    FISH_SONAR = 4662                 # ActionTimeline 4662: fishing/sonar（鱼群探测）
    FISH_TRIPLE_HOOKING = 8052        # ActionTimeline 8052: fishing/triple_hooking
    FISH_BIGSIZE = 8055               # ActionTimeline 8055: fishing/bigsize
    FISH_GP_RECOVERY = 8056           # ActionTimeline 8056: fishing/gp_recovery
    FISH_RETRIEVE_LURE = 11952        # ActionTimeline 11952: fishing/retrieve_lure
    FISH_REELING_LURE = 11953         # ActionTimeline 11953: fishing/reeling_lure
    FISH_HOOK_BT = 12195              # ActionTimeline 12195: fishing/hooking_bt
    # 7.x 新增——钓鱼坐位
    FISH_HOOK_HEAVY_SITTED = 3170     # ActionTimeline 3170: fishing_chair/hooking_big
    FISH_STRONG_HOOKING_SITTED = 4663 # ActionTimeline 4663: fishing_chair/strong_hooking
    FISH_HOOK_LIGHT_SITTED = 4665     # ActionTimeline 4665: fishing_chair/precision_hooking
    FISH_TRIPLE_HOOKING_SITTED = 8053 # ActionTimeline 8053: fishing_chair/triple_hooking
    # 7.x 新增——制作
    CRAFT_GODSWORK = 11619            # ActionTimeline 11619: craft/action_godswork（工匠神工动作）
    # 特殊值
    FISH_ASK_COLLECT = 527502  # 超出 ActionTimeline 表范围（表最大约 25000）；推测 0x80000 | 0xC8E（高位 flag 编码），运行时实测有效，来源未在 binary 中硬编码


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
        self._task: Optional[Task[None]] = None
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

    async def translate_action_name(self, action: str, lang: Optional[str]):
        if lang == None:
            return action
        index = {
            "c": 0,
            "j": 1,
            "e": 2
        }[lang]
        for tuple in self._config["action_names_cje"]:
            if action in tuple:
                return tuple[index]
        await PostNamazuWrapper.instance.send_cmd("/e WARNING: Unknown action {action}".format(action=repr(action)))
        return action

    async def use_action(self, action: Union[str, List[str]], retry: int, timeout: float, log_pattern: Optional[str] = None, lang: Optional[str] = None):
        for _ in range(retry):
            if self._role_state == RoleState.SITTED:
                break
            if isinstance(action, str):
                now_action = action
            else:
                now_action = action[self._craft_state.value - 1]
            if now_action:
                translated_action = await self.translate_action_name(now_action, lang)
                pattern = log_pattern if log_pattern else translated_action
                try:
                    fut = asyncio.Future()
                    self._listening_actions[pattern] = fut
                    if translated_action != now_action:
                        printed_action = "{now_action} -> {translated_action}".format(now_action=now_action, translated_action=translated_action)
                    else:
                        printed_action = now_action
                    await PostNamazuWrapper.instance.send_cmd("/e Preparing {state} -> {printed_action}".format(state=self._craft_state,
                                                                                                                printed_action=printed_action))
                    await PostNamazuWrapper.instance.send_cmd('/ac "{translated_action}"'.format(translated_action=translated_action))
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
                player_name_in_content = player.config["name"] in content or content.strip().startswith("You")
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
                    if "Gathering Fortune Up" in content:
                        if log.type == 0x8ae:
                            self._have_patient = True
                        else:
                            self._have_patient = False
            if log.type == 0x843:
                if 'sense something amiss' in content:
                    if self._task is not None:
                        self._task.cancel()
                        self._task = None

                        async def f():
                            await self.change_place()
                            self._task = asyncio.create_task(self.autofish())
                        self._task = asyncio.create_task(f())
            if log.type == 0x39:
                if 'elapsed since your last activity. If you are inactive for' in content:
                    self._idle_warn = True

    async def memory_scan(self, process: XIVMemory.XIVProcess):
        self._process = process

        craftbot_state_sig_offset = process.find_signature('craftbot_state')

        if not craftbot_state_sig_offset:
            return

        # RIP-relative 解引：0x02 是 disp32 起点，见 config_common/CraftBot.json 的 _comment_state_offset
        offset_state = process.follow_pointer_path(
            [*map(ast.literal_eval, self._config['state_offset'])],
            craftbot_state_sig_offset
        )

        # G+0x38 = Src[14]，语义为制作 condition；见 config_common/CraftBot.json 的 _comment_quality_offset
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

        if self._role_state in (RoleState.CRAFTING, RoleState.BUFFED):
            state = cast_int(process.read_memory(offset_quality, 4))
            try:
                self._craft_state = CraftState(state)
            except:
                if self._craft_value != state:
                    logging.error(
                        "Unknown craft state: {state}".format(state=state))
                self._craft_state = CraftState.NORMAL

            self._craft_value = state
        else:
            self._craft_state = CraftState.NORMAL

        if self._craft_state != old_craft_state:
            logging.info(f"Craft state changed {old_craft_state} -> {self._craft_state}")

    async def craft(self, recipe: str, num: int, lang: Optional[str]):
        with open(os.path.join(self._config["recipes_dir"], recipe + ".json"), encoding="utf-8") as fin:
            recipe = json.load(fin)

        for i in range(num):
            await asyncio.sleep(2)

            await PostNamazuWrapper.instance.send_cmd(
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
                await self.use_action(action, self._retry_count, self._retry_timeout, lang=lang)
                if self._role_state == RoleState.SITTED:
                    break

        await PostNamazuWrapper.instance.send_cmd("/e Craft stopped")

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
            #             await PostNamazuWrapper.instance.send_cmd("/ac 抛竿")
            #             await asyncio.sleep(self._delay_after_action)
            #         while 'FISHING' in self._role_state.name:
            #             await PostNamazuWrapper.instance.send_cmd("/ac 提钩")
            #             await asyncio.sleep(self._delay_after_action)

            #         await asyncio.sleep(2)

            #         success = await self.use_action("耐心II", self._retry_count, self._retry_timeout, "采集优质获得率提升")
            #         if success:
            #             self._next_can_use_patient = time.time() + 560 / 7 * 3

            # await PostNamazuWrapper.instance.send_cmd("/e CD: {sec:.2f}s".format(sec=(self._next_can_use_patient - time.time())))

            # if self._have_patient and not self._collect:
            #     self._collect = True
            #     await self.use_action("收藏品采集", self._retry_count, self._retry_timeout)

            # if not self._have_patient and self._collect:
            #     self._collect = False
            #     await self.use_action("收藏品采集", self._retry_count, self._retry_timeout)

            # await asyncio.sleep(self._delay_after_action)
            # await PostNamazuWrapper.instance.send_cmd("/ac 以小钓大")
            # await PostNamazuWrapper.instance.send_cmd("/ac 以小钓大II")

            while 'FISHING' not in self._role_state.name:
                await PostNamazuWrapper.instance.send_cmd('/ac "Cast"')
                await asyncio.sleep(self._delay_after_action)

            start_time = time.time()

            while 'FISHING' in self._role_state.name:
                await asyncio.sleep(0.1)

            end_time = time.time()

            elapsed_sec = end_time - start_time
            await PostNamazuWrapper.instance.send_cmd("/e Elapsed time: {sec:.2f}s".format(sec=elapsed_sec))

            await asyncio.sleep(0.5)

            while 'FISH_BAITED' in self._role_state.name:
                success = False
                if self._have_patient:
                    if elapsed_sec >= self._collect_threshold:
                        if 'LIGHT' in self._role_state.name:
                            success = await self.use_action("Precision Hookset", 1, self._retry_timeout, "$Something bites")
                        elif 'HEAVY' in self._role_state.name:
                            success = await self.use_action("	Powerful Hookset", 1, self._retry_timeout, "$Something bites")
                        if success:
                            self._next_can_use_patient += 50 / 7 * 3
                if not success:
                    await self.use_action("Hook", 1, self._retry_timeout, "$Something bites")

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
            await PostNamazuWrapper.instance.send_cmd("/e Handin {i}/{num}".format(i=i, num=num))
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
                lang = params[3] if len(params) > 3 else None
                if lang not in [None, "c", "j", "e"]:
                    return "Unknown language: {lang}".format(lang=lang)

                self._task = asyncio.create_task(self.craft(recipe, num, lang))
                return "Crafting"
            except:
                return "Usage: {cmd} recipe num [c/j/e]".format(cmd=params[0])
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
