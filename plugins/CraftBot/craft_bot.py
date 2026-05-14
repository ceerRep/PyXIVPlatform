#! /usr/bin/env python3

import os
import ast
import json
import asyncio
import logging
from typing import List, Optional

import PyXIVPlatform
import PostNamazuWrapper
import CommandHelper
import GameState
import ActionSender
from GameState.game_state import RoleState
from GameState.background_task import BackgroundTask


class CraftBot:
    def __init__(self):
        self._config = PyXIVPlatform.instance.load_config(__package__)
        self._state = GameState.instance
        self._dispatcher = ActionSender.instance
        self._bg_task = BackgroundTask()

        CommandHelper.instance.add_command("craft", self.on_cmd)
        CommandHelper.instance.add_command("stopcraft", self.on_cmd)
        CommandHelper.instance.add_command("autohandin", self.on_cmd)
        CommandHelper.instance.add_command("jump", self.on_cmd)

    async def craft(self, recipe_name: str, num: int, lang: Optional[str]):
        with open(os.path.join(self._config["recipes_dir"], recipe_name + ".json"), encoding="utf-8") as fin:
            recipe = json.load(fin)

        for i in range(num):
            await asyncio.sleep(2)

            await PostNamazuWrapper.instance.send_cmd(
                f"/e Crafting: {i}/{num}")

            while self._state.role_state == RoleState.CRAFTING:
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.1)

            now_state = self._state.role_state
            while (self._state.role_state == now_state and
                    self._state.role_state not in (RoleState.PENDING, RoleState.CRAFTING)):
                await self._state.process.send_key("NUMPAD0")
                await asyncio.sleep(0.1)

            while self._state.role_state not in (RoleState.PENDING, RoleState.CRAFTING):
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.2)

            for action in recipe:
                await self._dispatcher.dispatch(
                    action, self._config["retry_count"], self._config["retry_timeout"],
                    craft_state=self._state.craft_state,
                    role_state_reader=lambda: self._state.role_state,
                    lang=lang,
                )
                if self._state.role_state == RoleState.SITTED:
                    break

        await PostNamazuWrapper.instance.send_cmd("/e Craft stopped")

    async def jump(self, timeout: float):
        while True:
            await self._state.process.send_key("SPACE")
            await asyncio.sleep(timeout)

    async def handin(self, num: int):
        await asyncio.sleep(5)
        for i in range(num):
            await PostNamazuWrapper.instance.send_cmd(f"/e Handin {i}/{num}")
            await self._state.process.send_key("NUMPAD0")
            await asyncio.sleep(0.1)
            await self._state.process.send_key("MULTIPLY")
            await asyncio.sleep(0.1)
            await self._state.process.send_key("NUMPAD0")
            await asyncio.sleep(0.1)
            await self._state.process.send_key("NUMPAD0")
            await asyncio.sleep(1)

    def cancel(self):
        self._dispatcher.cancel_all()
        self._bg_task.cancel()

    async def on_cmd(self, params: List[str]) -> str:
        if params[0] == 'craft':
            try:
                recipe = params[1]
                num = int(params[2])
                lang = params[3] if len(params) > 3 else None
                if lang not in [None, "c", "j", "e"]:
                    return f"Unknown language: {lang}"
                self._bg_task.start(self.craft(recipe, num, lang))
                return "Crafting"
            except (IndexError, ValueError):
                return f"Usage: {params[0]} recipe num [c/j/e]"
        elif params[0] == 'stopcraft':
            self.cancel()
        elif params[0] == 'autohandin':
            self._bg_task.start(self.handin(int(params[1])))
        elif params[0] == 'jump':
            try:
                self._bg_task.start(self.jump(ast.literal_eval(params[1])))
            except (IndexError, ValueError):
                return f"Usage: {params[0]} timeout"
