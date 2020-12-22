#! /usr/bin/env python3

import sys
import logging
import asyncio

import PyXIVPlatform


def main():
    logging.basicConfig(
        format="[%(levelname)s] %(asctime)s %(message)s",
        level=logging.INFO,
        datefmt='%y-%m-%d %H:%M:%S')

    def exception_handler(loop, context):
        logging.error("%s", context)
    asyncio.get_event_loop().set_exception_handler(exception_handler)

    platform = PyXIVPlatform.XIVPlatform(sys.argv[1:])
    PyXIVPlatform.instance = platform

    platform.load_modules("plugins")

    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
