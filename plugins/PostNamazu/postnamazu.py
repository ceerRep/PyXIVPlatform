#! /usr/bin/env python3

import aiohttp

from .config import get_config

class PostNamazu:
    async def send_cmd(self, cmd: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(get_config()["post_namazu_addr"], data=cmd.encode('utf-8')) as resp:
                await resp.text()