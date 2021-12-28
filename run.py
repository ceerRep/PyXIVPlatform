#! /usr/bin/env python3

import sys
import inspect
import logging
import asyncio

import PyXIVPlatform


async def main():
    logging.basicConfig(
        format="[%(levelname)s] %(asctime)s %(name)s> %(message)s",
        level=logging.INFO,
        datefmt='%y-%m-%d %H:%M:%S')
    
    fileHandler = logging.FileHandler("platform.log", "a", "utf-8")
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s %(name)s> %(message)s"))
    logging.getLogger().addHandler(fileHandler)

    old_logging = {
        "debug": logging.debug,
        "info": logging.info,
        "warn": logging.warn,
        "warning": logging.warning,
        "critical": logging.critical,
        "error": logging.error
    }

    for name, func in old_logging.items():
        logging.__dict__[name] = (lambda n:
                                  lambda *a, **b: getattr(logging.getLogger(
                                      inspect.getmodule(inspect.stack()[1][0]).__name__), n)
                                  (*a, **b))(name)

    def exception_handler(loop, context):
        logging.error("%s", context)
    asyncio.get_event_loop().set_exception_handler(exception_handler)

    sys.pycache_prefix = '__pycache__'

    platform = PyXIVPlatform.XIVPlatform(sys.argv[1:])
    PyXIVPlatform.instance = platform

    platform.load_modules("plugins")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    loop.run_forever()
