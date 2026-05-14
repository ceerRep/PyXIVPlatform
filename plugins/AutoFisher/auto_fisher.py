#! /usr/bin/env python3

import ast
import asyncio
import logging
import time
from typing import List

import PyXIVPlatform
import PostNamazuWrapper
import LogScanner
import CommandHelper
import GameState
import ActionSender
import player

from LogScanner.log_types import LogType
from GameState.game_state import RoleState, BiteType
from GameState.background_task import BackgroundTask


def _any_pattern_in(patterns: list, content: str) -> bool:
    return any(p in content for p in patterns)


class AutoFisher:
    def __init__(self):
        self._config = PyXIVPlatform.instance.load_config(__package__)
        self._state = GameState.instance
        self._dispatcher = ActionSender.instance
        self._bg_task = BackgroundTask()

        self._have_patient: bool = False
        self._collect: bool = False
        self._next_can_use_patient: float = 0.0
        self._collect_threshold: float = 0.0
        self._change_place_time: float = 0.0
        self._idle_warn: bool = False
        self._patient_mode: bool = False

        self._cast_action: list = self._config["cast_action"]
        self._hook_action: list = self._config["hook_action"]
        self._precision_hookset: list = self._config["precision_hookset_action"]
        self._powerful_hookset: list = self._config["powerful_hookset_action"]
        self._patient_action: list = self._config["patient_action"]
        self._patient_buff_patterns: list = self._config["patient_buff_patterns"]
        self._patient_cooldown: float = self._config["patient_cooldown"]
        self._collectible_action: list = self._config["collectible_action"]
        self._mooch_actions: list = self._config["mooch_actions"]
        self._bite_patterns: list = self._config["bite_patterns"]
        self._amiss_patterns: list = self._config["amiss_patterns"]
        self._idle_patterns: list = self._config["idle_patterns"]
        self._retry_count: int = self._config["retry_count"]
        self._retry_timeout: float = self._config["retry_timeout"]
        self._delay_after_action: float = self._config["delay_after_action"]

        LogScanner.instance.log_listener(self.on_log_arrival)
        CommandHelper.instance.add_command("autofish", self.on_cmd)
        CommandHelper.instance.add_command("stopfish", self.on_cmd)
        CommandHelper.instance.add_command("changeplace", self.on_cmd)

    def _bite_log_pattern(self) -> str:
        return "$" + self._bite_patterns[0]

    async def on_log_arrival(self, log: LogScanner.XIVLogLine, process):
        if not log.new:
            return
        content = log.fields[1]

        if log.type in (LogType.GATHER_STATUS_GAIN, LogType.GATHER_STATUS_LOSE):
            if player.config["name"] in content:
                if _any_pattern_in(self._patient_buff_patterns, content):
                    self._have_patient = (log.type == LogType.GATHER_STATUS_GAIN)

        if log.type == LogType.GATHERING_SYSTEM:
            if _any_pattern_in(self._amiss_patterns, content):
                async def _reposition():
                    await self.change_place()
                    await self.run()
                self._bg_task.start(_reposition())

        if log.type == LogType.SYSTEM_NOTICE:
            if _any_pattern_in(self._idle_patterns, content):
                self._idle_warn = True

    def start(self, change_place_time: float, collect_threshold: float,
              patient_mode: bool = False):
        self._change_place_time = change_place_time
        self._collect_threshold = collect_threshold
        self._patient_mode = patient_mode
        self._bg_task.start(self.run())

    async def run(self):
        while True:
            if self._idle_warn:
                await self.change_place()
                self._idle_warn = False

            if self._patient_mode:
                await self._apply_patient_if_needed()

            while not self._state.role_state.is_casting:
                await self._dispatcher.dispatch(
                    self._cast_action, 1, self._retry_timeout)
                await asyncio.sleep(self._delay_after_action)

            start_time = time.time()

            while self._state.role_state.is_casting:
                await asyncio.sleep(0.1)

            elapsed_sec = time.time() - start_time
            await PostNamazuWrapper.instance.send_cmd(
                f"/e Elapsed time: {elapsed_sec:.2f}s")

            await asyncio.sleep(0.5)

            while self._state.role_state.is_baited:
                success = False
                if self._have_patient:
                    if elapsed_sec >= self._collect_threshold:
                        bite = self._state.role_state.bite_type
                        if bite == BiteType.LIGHT:
                            success = await self._dispatcher.dispatch(
                                self._precision_hookset, 1, self._retry_timeout,
                                log_pattern=self._bite_log_pattern())
                        elif bite == BiteType.HEAVY:
                            success = await self._dispatcher.dispatch(
                                self._powerful_hookset, 1, self._retry_timeout,
                                log_pattern=self._bite_log_pattern())
                        if success:
                            self._next_can_use_patient += 50 / 7 * 3
                if not success:
                    await self._dispatcher.dispatch(
                        self._hook_action, 1, self._retry_timeout,
                        log_pattern=self._bite_log_pattern())

            while self._state.role_state == RoleState.VOID:
                await asyncio.sleep(0.1)

            while self._state.role_state.is_hooking:
                await asyncio.sleep(0.1)

            while self._state.role_state == RoleState.VOID:
                await asyncio.sleep(0.1)

            if self._state.role_state == RoleState.FISH_ASK_COLLECT:
                while self._state.role_state == RoleState.FISH_ASK_COLLECT:
                    await self._state.process.send_key("NUMPAD0")
                    await asyncio.sleep(0.1)

            await asyncio.sleep(self._delay_after_action)

            if self._patient_mode:
                for mooch in self._mooch_actions:
                    await self._dispatcher.dispatch(
                        mooch, 1, self._retry_timeout)

    async def _apply_patient_if_needed(self):
        if self._have_patient and not self._collect:
            self._collect = True
            await self._dispatcher.dispatch(
                self._collectible_action, self._retry_count, self._retry_timeout)

        if not self._have_patient and self._collect:
            self._collect = False
            await self._dispatcher.dispatch(
                self._collectible_action, self._retry_count, self._retry_timeout)

        if not self._have_patient and time.time() > self._next_can_use_patient:
            while self._state.role_state.is_casting:
                await self._dispatcher.dispatch(
                    self._hook_action, 1, self._retry_timeout)
                await asyncio.sleep(self._delay_after_action)

            await asyncio.sleep(2)

            success = await self._dispatcher.dispatch(
                self._patient_action, self._retry_count, self._retry_timeout,
                log_pattern="$" + self._patient_buff_patterns[0])
            if success:
                self._next_can_use_patient = time.time() + self._patient_cooldown

    async def change_place(self):
        process = self._state.process
        key = 'q' if self._change_place_time < 0 else 'e'
        await process.send_key(key)
        await asyncio.sleep(3)

        t = abs(self._change_place_time)
        await process.send_key(key, True, False)
        await asyncio.sleep(t)
        await process.send_key(key, False, True)
        self._change_place_time = -self._change_place_time

    def cancel(self):
        self._dispatcher.cancel_all()
        self._bg_task.cancel()

    async def on_cmd(self, params: List[str]) -> str:
        if params[0] == 'autofish':
            try:
                change_place_time = ast.literal_eval(params[1])
                collect_threshold = ast.literal_eval(params[2])
                patient_mode = len(params) > 3 and params[3].lower() in ('true', '1', 'patient')
                self.start(change_place_time, collect_threshold, patient_mode)
                return "Fishing"
            except (IndexError, ValueError):
                return f"Usage: {params[0]} walktime threshold [patient]"
        elif params[0] == 'stopfish':
            self.cancel()
        elif params[0] == 'changeplace':
            try:
                self._change_place_time = ast.literal_eval(params[1])
                await self.change_place()
            except (IndexError, ValueError):
                return f"Usage: {params[0]} walktime"
