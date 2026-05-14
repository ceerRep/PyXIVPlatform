#! /usr/bin/env python3

import ast
import logging
from enum import Enum
from typing import Optional

from XIVMemory.memoryhelper import cast_int


class CraftState(Enum):
    VOID = 0
    NORMAL = 1
    HIGH = 2
    HIGHEST = 3
    LOW = 4


class BiteType(Enum):
    LIGHT = "light"
    HEAVY = "heavy"
    NORMAL = "normal"


# --------------------------------------------------------------------------
# RoleState
#
# Subset of ActionTimelineId values that PyXIVPlatform's craft / fish state
# machines actually act on — not an exhaustive enumeration of the table.
#
# IDs come from the game's ActionTimeline.csv (see thewakingsands/
# ffxiv-datamining-cn or xivapi/ffxiv-datamining; both regions are kept
# byte-identical at the data level, so either CSV is authoritative).
#
# How the value is read:
#   state_signature resolves to a global uint32[] timeline array G.
#   G+0x00 = Src[0] = currently-playing ActionTimelineId.
#   The game updates G via memmove(G, src, 4*count) on every action change.
#
# When a new patch shifts a fishing / sitting / crafting animation, the
# right fix is almost always to look up the new row in ActionTimeline.csv —
# not to re-scan the signature.
# --------------------------------------------------------------------------
class RoleState(Enum):
    VOID = 0
    IDLE1 = 1            # ActionTimeline 1:  normal/idle_loop
    SITTING = 2          # ActionTimeline 2:  normal/idle
    PENDING = 3          # ActionTimeline 3:  normal/idle_inactive (crafting open)
    SITTED = 4           # ActionTimeline 4:  normal/idle_inactive (crafting result)
    UNKNOWN5 = 5         # ActionTimeline 5:  normal/turn_loop_l (未确认语义)
    IDLE6 = 6            # ActionTimeline 6:  normal/turn_loop_r
    UNKNOWN7 = 7         # ActionTimeline 7:  (Name 空，合法 timeline)
    UNKNOWN8 = 8         # ActionTimeline 8:  (Name 空，合法 timeline)
    CRAFTING = 9         # ActionTimeline 9:  (Name 空，制作中)
    BUFFED = 10          # ActionTimeline 10: (Name 空，制作中有 buff)
    FISH_IDLE = 271               # ActionTimeline 271:  fishing/idle_loop
    FISH_FINISHED = 273           # ActionTimeline 273:  fishing/finish
    FISH_FISHING0 = 274           # ActionTimeline 274:  fishing/casting
    FISH_FISHING1 = 275           # ActionTimeline 275:  fishing/casting_loop
    FISH_HOOK_NOTHING = 283       # ActionTimeline 283:  fishing/miss
    FISH_HOOK = 284               # ActionTimeline 284:  fishing/hooking
    FISH_BITE_EXCITE = 292         # ActionTimeline 292:  fishing/hit_excite
    FISH_BITE_STRIKE = 293         # ActionTimeline 293:  fishing/hit_strike
    FISH_BITE_NORMAL = 294         # ActionTimeline 294:  fishing/hit_bite
    FISH_IDLE_SITTED = 3143           # ActionTimeline 3143: fishing_chair/idle_loop
    FISH_FINISHED_SITTED = 3144       # ActionTimeline 3144: fishing_chair/finish
    FISH_FISHING_SITTED0 = 3145       # ActionTimeline 3145: fishing_chair/casting
    FISH_FISHING_SITTED1 = 3146       # ActionTimeline 3146: fishing_chair/casting_loop
    FISH_HOOK_NOTHING_SITTED = 3154   # ActionTimeline 3154: fishing_chair/miss
    FISH_HOOK_SITTED = 3155           # ActionTimeline 3155: fishing_chair/hooking
    FISH_HOOK_HEAVY = 4659            # ActionTimeline 4659: fishing/powerful_hooking
    FISH_HOOK_LIGHT = 4660            # ActionTimeline 4660: fishing/precision_hooking
    FISH_UNKNOWN_IDLE = 4661          # ActionTimeline 4661: fishing/idle_after_bait（撒饵后空闲）
    # 7.x 新增——钓鱼立位
    FISH_SONAR = 4662                 # ActionTimeline 4662: fishing/sonar（鱼群探测）
    FISH_TRIPLE_HOOKING = 8052        # ActionTimeline 8052: fishing/triple_hooking
    FISH_BIGSIZE = 8055               # ActionTimeline 8055: fishing/bigsize
    FISH_GP_RECOVERY = 8056           # ActionTimeline 8056: fishing/gp_recovery
    FISH_RETRIEVE_LURE = 11952        # ActionTimeline 11952: fishing/retrieve_lure
    FISH_REELING_LURE = 11953         # ActionTimeline 11953: fishing/reeling_lure
    FISH_HOOK_BT = 12195              # ActionTimeline 12195: fishing/hooking_bt
    # 7.x 新增——钓鱼坐位
    FISH_HOOK_HEAVY_SITTED = 3170     # ActionTimeline 3170: fishing_chair/hooking_big
    FISH_STRONG_HOOKING_SITTED = 4663 # ActionTimeline 4663: fishing_chair/strong_hooking
    FISH_HOOK_LIGHT_SITTED = 4665     # ActionTimeline 4665: fishing_chair/precision_hooking
    FISH_TRIPLE_HOOKING_SITTED = 8053 # ActionTimeline 8053: fishing_chair/triple_hooking
    # 7.x 新增——制作
    CRAFT_GODSWORK = 11619            # ActionTimeline 11619: craft/action_godswork（工匠神工动作）
    # 特殊值
    FISH_ASK_COLLECT = 527502  # 超出 ActionTimeline 表范围（表最大约 25000）；推测 0x80000 | 0xC8E（高位 flag 编码），运行时实测有效，来源未在 binary 中硬编码

    @property
    def is_casting(self) -> bool:
        return self in _CASTING_STATES

    @property
    def is_baited(self) -> bool:
        return self in _BAITED_STATES

    @property
    def is_hooking(self) -> bool:
        return self in _HOOKING_STATES

    @property
    def bite_type(self) -> Optional['BiteType']:
        return _BITE_TYPE_MAP.get(self)


_CASTING_STATES = frozenset({
    RoleState.FISH_FISHING0, RoleState.FISH_FISHING1,
    RoleState.FISH_FISHING_SITTED0, RoleState.FISH_FISHING_SITTED1,
})

_BAITED_STATES = frozenset({
    RoleState.FISH_BITE_EXCITE,
    RoleState.FISH_BITE_STRIKE,
    RoleState.FISH_BITE_NORMAL,
})

_HOOKING_STATES = frozenset({
    RoleState.FISH_HOOK, RoleState.FISH_HOOK_NOTHING,
    RoleState.FISH_HOOK_HEAVY, RoleState.FISH_HOOK_LIGHT,
    RoleState.FISH_HOOK_SITTED, RoleState.FISH_HOOK_NOTHING_SITTED,
    RoleState.FISH_HOOK_HEAVY_SITTED, RoleState.FISH_HOOK_LIGHT_SITTED,
    RoleState.FISH_STRONG_HOOKING_SITTED,
    RoleState.FISH_TRIPLE_HOOKING, RoleState.FISH_TRIPLE_HOOKING_SITTED,
    RoleState.FISH_HOOK_BT,
})

_BITE_TYPE_MAP = {
    RoleState.FISH_BITE_EXCITE: BiteType.LIGHT,
    RoleState.FISH_BITE_STRIKE: BiteType.HEAVY,
    RoleState.FISH_BITE_NORMAL: BiteType.NORMAL,
}


class GameStateReader:
    def __init__(self, config: dict):
        self._config = config
        self._role_state = RoleState.IDLE1
        self._craft_state = CraftState.NORMAL
        self._role_value = 0
        self._craft_value = 0
        self._process = None

    @property
    def role_state(self) -> RoleState:
        return self._role_state

    @property
    def craft_state(self) -> CraftState:
        return self._craft_state

    @property
    def process(self):
        return self._process

    async def memory_scan(self, process):
        self._process = process

        sig_offset = process.find_signature('gamestate')

        if not sig_offset:
            return

        offset_state = process.follow_pointer_path(
            [*map(ast.literal_eval, self._config['state_offset'])],
            sig_offset,
        )
        offset_quality = process.follow_pointer_path(
            [*map(ast.literal_eval, self._config['quality_offset'])],
            sig_offset,
        )

        state = cast_int(process.read_memory(offset_state, 4))

        old_role_state = self._role_state
        old_craft_state = self._craft_state

        try:
            self._role_state = RoleState(state)
        except ValueError:
            if self._role_value != state:
                logging.error("Unknown role state: %s", state)
            self._role_state = RoleState.IDLE6

        self._role_value = state

        if self._role_state != old_role_state:
            logging.info("Role changed %s -> %s", old_role_state, self._role_state)

        if self._role_state in (RoleState.CRAFTING, RoleState.BUFFED):
            state = cast_int(process.read_memory(offset_quality, 4))
            try:
                self._craft_state = CraftState(state)
            except ValueError:
                if self._craft_value != state:
                    logging.error("Unknown craft state: %s", state)
                self._craft_state = CraftState.NORMAL
            self._craft_value = state
        else:
            self._craft_state = CraftState.NORMAL

        if self._craft_state != old_craft_state:
            logging.info("Craft state changed %s -> %s", old_craft_state, self._craft_state)
