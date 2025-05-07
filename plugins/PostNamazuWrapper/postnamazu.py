#! /usr/bin/env python3

import atexit
import os
import aiohttp
from typing import Union

import logging
import XIVMemory
import PyXIVPlatform

from typing import List

config = PyXIVPlatform.instance.load_config(__package__)

if config["use_embedded_postnamazu"]:
    import clr
    System = __import__('System')

    dirpath = os.path.dirname(__file__)

    System.Reflection.Assembly.LoadFile(os.path.join(dirpath, "GreyMagic.dll"))
    System.Reflection.Assembly.LoadFile(os.path.join(dirpath, "PostNamazu.dll"))

    PostNamazu = __import__('PostNamazu')
    PostNamazu.Logger.SetLogger(System.Action[str](logging.info))

    class PostNamazuWrapper:
        def __init__(self):
            self._postNamazu = PostNamazu.PostNamazu()
            self._postNamazu.InitPlugin()
            XIVMemory.instance.add_callback(self.scan)
            atexit.register(self.deinit)
        
        def deinit(self):
            self._postNamazu.DeInitPlugin()
        
        async def scan(self, process: XIVMemory.XIVProcess):
            self.set_pid(process.pid)
        
        def set_pid(self, pid: int):
            if pid is None:
                pid = 0
            self._postNamazu.ProcessChanged(pid)
        
        async def send_cmd(self, cmd: str):
            self._postNamazu.DoAction('command', cmd)

        async def cmd_do_cmd(self, params: List[str]):
            await self.send_cmd(' '.join(params[1:]))
            return ""
        
else:
    class PostNamazuWrapper:
        async def send_cmd(self, cmd: str):
            async with aiohttp.ClientSession() as session:
                async with session.post(config["post_namazu_addr"], data=cmd.encode('utf-8')) as resp:
                    await resp.text()

        async def cmd_do_cmd(self, params: List[str]):
            await self.send_cmd(' '.join(params[1:]))
            return ""
