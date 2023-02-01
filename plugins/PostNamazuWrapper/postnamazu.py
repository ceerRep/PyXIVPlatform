#! /usr/bin/env python3

import atexit
import os
from typing import Union

import clr
System = __import__('System')

import logging
import XIVMemory
import PyXIVPlatform

dirpath = os.path.dirname(__file__)

System.Reflection.Assembly.LoadFile(os.path.join(dirpath, "GreyMagic.dll"))
System.Reflection.Assembly.LoadFile(os.path.join(dirpath, "PostNamazu.dll"))

PostNamazu = __import__('PostNamazu')
PostNamazu.Logger.SetLogger(System.Action[str](logging.info))

config = PyXIVPlatform.instance.load_config(__package__)

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
        self._postNamazu.DoAction("command", cmd)
    
    async def send_bytes_cmd(self, cmd: bytes):
        self._postNamazu.DoBytesCommand(cmd)
