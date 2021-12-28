#! /usr/bin/env python3

import asyncio
from asyncio.futures import Future
import logging
from typing import *

import PyXIVPlatform
import XIVMemory
import CommandHelper

__all__ = ["meta", "instance"]

meta = {
    'name': 'SkipMainCutscenes',
    'requirements': [
        "CommandHelper",
        "XIVMemory"
    ]
}

class SkipMainCutscenes:
    signature = '75|90 33|90 48 ?? ?? ?? ?? ?? ?? ?? ?? 00 00 00 48 ?? ?? ?? E8 ?? ?? ?? ?? ?? ?? ?? 00 74|90 18|90'
    signature_len = len(signature.split())
    def __init__(self, memory: XIVMemory.MemoryScanner, command: CommandHelper.CommandHelper):
        self._next_action = None
        self._action_fut = None

        memory.add_signature('skipmaincutscenes', self.signature)
        memory.add_callback(self.scan)

        command.add_command('mainscenaro', self.cmd_mainscenaro)
    
    async def scan(self, process: XIVMemory.XIVProcess):
        addr = process.find_signature('skipmaincutscenes') + process.get_base_address()

        match self._next_action:
            case 'skip':
                process.write_memory(addr, b'\x90\x90')
                process.write_memory(addr + self.signature_len - 2, b'\x90\x90')

                self._action_fut.set_result('main cutscenes skipped')
            case 'restore':
                process.write_memory(addr, b'\x75\x33')
                process.write_memory(addr + self.signature_len - 2, b'\x74\x18')

                self._action_fut.set_result('main cutscenes restored')
        self._next_action = None
        self._action_fut = None
    
    async def cmd_mainscenaro(self, params: List[str]) -> str:
        try:
            assert params[1] in ['skip', 'restore']
            self._action_fut: Future[str] = asyncio.Future()
            self._next_action = params[1]
            return await self._action_fut
        except:
            return f'Usage: {params[0]} <skip|restore>'


def init(platform: PyXIVPlatform.XIVPlatform):
    inst = SkipMainCutscenes(XIVMemory.instance, CommandHelper.instance)
    logging.info(__package__)
    return inst


instance: SkipMainCutscenes = init(PyXIVPlatform.instance)
