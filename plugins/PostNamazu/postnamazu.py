#! /usr/bin/env python3

import aiohttp
import PyXIVPlatform

config = PyXIVPlatform.instance.load_config(__package__)

class PostNamazu:
    async def send_cmd(self, cmd: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(config["post_namazu_addr"], data=cmd.encode('utf-8')) as resp:
                await resp.text()