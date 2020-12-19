#! /usr/bin/env python3

import os
import sys
import json
import types
import logging
import asyncio
import importlib

from typing import *

__all__ = ["XIVPlatform", "instance"]


class XIVPlugin:
    def __init__(self, module: types.ModuleType) -> None:
        self.name: str = module.meta['name']
        self.requirements: List[str] = module.meta['requirements']
        self.module = module


class XIVPlatform:
    def __init__(self, config_path: str):
        self.__config_path = config_path
        self.__plugins: Dict[str, XIVPlugin] = {}

        self.global_config = self.load_config("Global")

    def load_modules(self, plugin_path: str):
        sys.path.append(plugin_path)

        for module in os.listdir(plugin_path):
            if module[:2] == "__":
                continue
            if "_disabled" not in module:
                if os.path.isfile(os.path.join(plugin_path, module)):
                    module = os.path.splitext(module)[0]
                module = XIVPlugin(importlib.import_module(module))
                self.__plugins[module.name] = module

    def get_plugin(self, name: str) -> XIVPlugin:
        return self.__plugins[name]

    def load_config(self, name: Any) -> Dict[str, Any]:
        if not isinstance(name, str):
            if not isinstance(name, type):
                name = name.__class__
            name = name.__name__

        try:
            with open(os.path.join(self.__config_path, name + '.json'), encoding='utf-8') as fin:
                config = json.load(fin)
        except:
            config = {}

        if not isinstance(config, dict):
            config = {}

        return config

    def save_config(self, name: Any, config: Dict[str, Any]) -> bool:
        if not isinstance(name, str):
            if not isinstance(name, type):
                name = name.__class__
            name = name.__name__

        try:
            with open(os.path.join(self.__config_path, name + '.json'), 'w', encoding='utf-8') as fout:
                json.dump(config, fout, ensure_ascii=False, indent=2)
        except:
            return False
        return True


instance: Optional[XIVPlatform] = None
