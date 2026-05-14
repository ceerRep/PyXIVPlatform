#! /usr/bin/env python3
"""
Skip the engine's "must-watch this cutscene" guards in real time.

Strategy (resilient to per-version structural drift):

  1. Anchor on the string "IsPlayCutscene" registered with the Lua scripting
     bridge — SE has shipped this name unchanged for years.
  2. Find the `lea r8, [rip+IsPlayCutscene]` xref.  The matching
     `lea r9, [rip+...]` shortly above gives the address of the callback
     function `F` that implements the predicate.
  3. Inside `F`, find the tail block
         xor ecx, ecx ; movzx ebx, bl ; cmp al, 1 ; cmove ebx, ecx
     The instruction immediately after the cmove is the common skip target
     `T` that every guard `jcc` jumps to when the engine wants to refuse a
     skip.
  4. Linear-disasm `F` from its entry, collect every conditional jump whose
     target == T.  NOP all of them on `skip`, restore originals on
     `restore`.

The number of guards (2 in older builds, 3 in current builds, possibly more
in future ones) is discovered automatically — no hand-tuned offsets, no
regex.
"""

import asyncio
import logging
from asyncio.futures import Future
from dataclasses import dataclass
from typing import List, Optional

import PyXIVPlatform
import XIVMemory
import CommandHelper

__all__ = ["meta", "instance"]

meta = {
    'name': 'SkipMainCutscenes',
    'requirements': [
        "CommandHelper",
        "XIVMemory",
    ],
}


@dataclass
class PatchSite:
    rva: int                 # offset into base_image
    original: bytes          # original bytes (saved at locate time)


# Function-locator inputs.  If SE ever renames the registered string, edit
# here only; the rest of the algorithm doesn't care.
_ANCHOR_STRING = b"IsPlayCutscene\x00"
# How far back from the `lea r8, [rip+str]` we look for the matching `lea r9`.
_LEA_R9_BACKSCAN = 64
# Cap on how far we'll linear-disasm into the callback.  ~512 bytes is
# generous; the function has been ~200 bytes historically.
_FN_DISASM_BUDGET = 512


class SkipMainCutscenes:

    def __init__(self, memory: XIVMemory.MemoryScanner,
                 command: CommandHelper.CommandHelper):
        self._next_action: Optional[str] = None
        self._action_fut: Optional[Future[str]] = None

        # cache: keyed by (handle id) so we re-locate when XIVProcess swaps.
        self._sites: List[PatchSite] = []
        self._sites_for_image: int = 0   # id(base_image) we located against

        memory.add_callback(self.scan)
        command.add_command('mainscenaro', self.cmd_mainscenaro)

    # ------------------------------------------------------------------
    # Locator
    # ------------------------------------------------------------------

    def _locate(self, process: "XIVMemory.XIVProcess") -> List[PatchSite]:
        anchor = XIVMemory.CodeAnchor(process)

        str_rva = anchor.find_string(_ANCHOR_STRING)
        if str_rva is None:
            raise RuntimeError(
                f"anchor string {_ANCHOR_STRING!r} not found in image")

        lea_r8_rvas = anchor.find_lea_to(str_rva, reg="r8")
        if not lea_r8_rvas:
            raise RuntimeError("no `lea r8, [rip+IsPlayCutscene]` xref found")
        if len(lea_r8_rvas) > 1:
            logging.info("SkipMainCutscenes: %d xrefs to anchor; using first",
                         len(lea_r8_rvas))
        lea_r8 = lea_r8_rvas[0]

        lea_r9 = anchor.find_lea_above(lea_r8, reg="r9",
                                       max_back=_LEA_R9_BACKSCAN)
        if lea_r9 is None:
            raise RuntimeError("no nearby `lea r9, [rip+callback]` found")
        fn_rva = anchor.read_lea_target(lea_r9)

        insns = anchor.disasm(fn_rva, _FN_DISASM_BUDGET)
        span = anchor.find_bool_fold(insns)
        if span is None:
            raise RuntimeError("bool-fold tail block not found in callback")
        _, end = span
        tail_last = insns[end - 1]
        skip_target = tail_last.rva + tail_last.size

        body = insns[:end]
        guards = anchor.cond_jumps_to(body, skip_target)
        if not guards:
            raise RuntimeError("no conditional jumps to skip target found")

        # Diagnostic: the unconditional `jmp T` we see right after the
        # `xor bl, bl` early-return ("no cutscene playing") is expected and
        # NOT patched. Count it so the operator can sanity-check.
        uncond_to_T = [
            ins for ins in body
            if ins.mnemonic == "jmp" and ins.branch_target_rva == skip_target
        ]
        # Magic ID the function looks up in the global content registry —
        # changes whenever SE renumbers the table (we saw 0xC2 in older builds,
        # 0xDF currently). Useful as a version fingerprint.
        magic_id = anchor.find_imm_load(body, "edx", last=True)

        sites = [PatchSite(rva=g.rva, original=g.bytes) for g in guards]
        logging.info(
            "SkipMainCutscenes: callback @ 0x%x, T = 0x%x, "
            "%d guard(s), %d unconditional skip(s), magic_id = %s",
            anchor.rva_to_va(fn_rva),
            anchor.rva_to_va(skip_target),
            len(sites),
            len(uncond_to_T),
            f"0x{magic_id:x}" if magic_id is not None else "?",
        )
        for g in guards:
            logging.info("  guard 0x%x  %s %s  (%s)",
                         anchor.rva_to_va(g.rva),
                         g.mnemonic, g.op_str, g.bytes.hex(' '))
        return sites

    def _ensure_located(self, process: "XIVMemory.XIVProcess") -> bool:
        img_id = id(process.base_image)
        if self._sites and self._sites_for_image == img_id:
            return True
        try:
            self._sites = self._locate(process)
            self._sites_for_image = img_id
            return True
        except Exception as e:
            logging.error("SkipMainCutscenes locate failed: %s", e)
            self._sites = []
            self._sites_for_image = 0
            return False

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    async def scan(self, process: "XIVMemory.XIVProcess"):
        if self._next_action is None:
            return

        if not self._ensure_located(process):
            if self._action_fut is not None:
                self._action_fut.set_result("locate failed; see log")
                self._action_fut = None
            self._next_action = None
            return

        action = self._next_action
        if action == "inspect":
            base = process.get_base_address()
            lines = [f"found {len(self._sites)} guard(s):"]
            for s in self._sites:
                lines.append(
                    f"  VA 0x{base + s.rva:x}  bytes={s.original.hex(' ')}")
            if self._action_fut is not None:
                self._action_fut.set_result("\n".join(lines))
                self._action_fut = None
            self._next_action = None
            return

        base = process.get_base_address()
        for site in self._sites:
            data = (b"\x90" * len(site.original)
                    if action == "skip" else site.original)
            process.write_memory(base + site.rva, data)

        if self._action_fut is not None:
            self._action_fut.set_result(
                f"main cutscenes {'skipped' if action == 'skip' else 'restored'} "
                f"({len(self._sites)} guard(s) patched)")
            self._action_fut = None
        self._next_action = None

    # ------------------------------------------------------------------
    # Command surface
    # ------------------------------------------------------------------

    async def cmd_mainscenaro(self, params: List[str]) -> str:
        try:
            assert params[1] in ('skip', 'restore', 'inspect')
            self._action_fut = asyncio.Future()
            self._next_action = params[1]
            return await self._action_fut
        except Exception:
            return f'Usage: {params[0]} <skip|restore|inspect>'


def init(platform: PyXIVPlatform.XIVPlatform):
    inst = SkipMainCutscenes(XIVMemory.instance, CommandHelper.instance)
    logging.info(__package__)
    return inst


instance: SkipMainCutscenes = init(PyXIVPlatform.instance)
