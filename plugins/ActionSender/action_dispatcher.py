#! /usr/bin/env python3

import asyncio
import logging
from typing import Callable, Dict, List, Optional, Union

from GameState.game_state import CraftState, RoleState


class ActionDispatcher:
    def __init__(self, postnamazu, delay_after_action: float, config: dict):
        self._postnamazu = postnamazu
        self._delay_after_action = delay_after_action
        self._pending: Dict[str, asyncio.Future] = {}
        self._action_names_cje: list = config["action_names_cje"]

    async def translate_action_name(self, action: str, lang: Optional[str]) -> str:
        if lang is None:
            return action
        index = {"c": 0, "j": 1, "e": 2}[lang]
        for names in self._action_names_cje:
            if action in names:
                return names[index]
        await self._postnamazu.send_cmd(f"/e WARNING: Unknown action {action!r}")
        return action

    async def dispatch(
        self,
        action: Union[str, List[str]],
        retry: int,
        timeout: float,
        craft_state: CraftState = CraftState.NORMAL,
        role_state_reader: Optional[Callable[[], RoleState]] = None,
        log_pattern: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> bool:
        for _ in range(retry):
            if role_state_reader and role_state_reader() == RoleState.SITTED:
                break
            if isinstance(action, str):
                now_action = action
            else:
                now_action = action[craft_state.value - 1]
            if not now_action:
                continue
            translated = await self.translate_action_name(now_action, lang)
            pattern = log_pattern if log_pattern else translated
            try:
                fut = asyncio.Future()
                self._pending[pattern] = fut
                if translated != now_action:
                    printed = f"{now_action} -> {translated}"
                else:
                    printed = now_action
                await self._postnamazu.send_cmd(
                    f"/e Preparing {craft_state} -> {printed}")
                await self._postnamazu.send_cmd(f'/ac "{translated}"')
                await asyncio.wait_for(fut, timeout=timeout)
                await asyncio.sleep(self._delay_after_action)
            except asyncio.TimeoutError:
                self._pending.pop(pattern, None)
                continue
            else:
                return True
        return False

    def on_log_confirm(self, content: str, player_name_in_content: bool):
        assert len(self._pending) <= 1
        for sname in list(self._pending.keys()):
            real_sname = sname
            check_player = player_name_in_content
            if sname.startswith('$'):
                real_sname = sname[1:]
                check_player = True
            if check_player and real_sname in content:
                self._pending.pop(sname).set_result(None)
                break

    def cancel_all(self):
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
