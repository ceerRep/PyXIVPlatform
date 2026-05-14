#! /usr/bin/env python3
"""
Code-level anchoring helpers.

Plugins that patch live game code can avoid brittle byte signatures by
anchoring on stable artifacts (strings registered with the engine, named
xrefs, function epilogues) and then locally disassembling around the anchor
to discover the patch sites — even when the surrounding instructions get
re-shuffled across game versions.

Usage from a plugin (typical pattern):

    anchor = CodeAnchor(process)            # process: XIVProcess
    str_rva = anchor.find_string(b"IsPlayCutscene\\x00")
    lea_r8  = anchor.find_lea_to(str_rva, reg="r8")[0]
    fn_rva  = anchor.read_lea_target(
                  anchor.find_lea_above(lea_r8, reg="r9"))
    insns   = anchor.disasm(fn_rva, 512)
    ...

All RVAs are offsets into the loaded image (i.e. into base_image), NOT file
offsets.  XIVProcess.base_image is a memory-image read, so RVA == byte index
into base_image, and absolute_va == process.get_base_address() + rva.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM


# x86-64: 32-bit GPR -> its low-byte alias.  Used to match patterns like
# `movzx <R32>, <low8(R)>` without binding to a specific register.
_LOW8_OF = {
    "eax": "al",   "ecx": "cl",   "edx": "dl",   "ebx": "bl",
    "esp": "spl",  "ebp": "bpl",  "esi": "sil",  "edi": "dil",
    "r8d": "r8b",  "r9d": "r9b",  "r10d": "r10b", "r11d": "r11b",
    "r12d": "r12b", "r13d": "r13b", "r14d": "r14b", "r15d": "r15b",
}
_GPR32 = frozenset(_LOW8_OF.keys())


# --- regs we care about for `lea reg, [rip+disp32]` -------------------------
# 64-bit lea opcodes: REX.W (0x48 or 0x4C) + 0x8D + ModR/M.
# ModR/M for `lea <reg>, [rip+disp32]` is (reg << 3) | 0b101 with mod=00.
# For r8..r15 we use REX.W|REX.R = 0x4C and the low 3 bits of the reg field.
_LEA_PREFIX = {
    "rax": b"\x48\x8d\x05",
    "rcx": b"\x48\x8d\x0d",
    "rdx": b"\x48\x8d\x15",
    "rbx": b"\x48\x8d\x1d",
    "rsp": b"\x48\x8d\x25",
    "rbp": b"\x48\x8d\x2d",
    "rsi": b"\x48\x8d\x35",
    "rdi": b"\x48\x8d\x3d",
    "r8":  b"\x4c\x8d\x05",
    "r9":  b"\x4c\x8d\x0d",
    "r10": b"\x4c\x8d\x15",
    "r11": b"\x4c\x8d\x1d",
    "r12": b"\x4c\x8d\x25",
    "r13": b"\x4c\x8d\x2d",
    "r14": b"\x4c\x8d\x35",
    "r15": b"\x4c\x8d\x3d",
}

# x86-64 conditional jumps (excludes unconditional `jmp`).
COND_JUMPS = frozenset({
    "je", "jne", "jz", "jnz", "js", "jns", "jo", "jno", "jp", "jnp",
    "jpe", "jpo", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae",
    "jc", "jnc", "jcxz", "jecxz", "jrcxz",
})


@dataclass
class Insn:
    """Lightweight, RVA-keyed instruction record."""
    rva: int
    size: int
    mnemonic: str
    op_str: str
    bytes: bytes
    # cached: imm operand target RVA when the only operand is an immediate
    # (mostly useful for `jcc rel`/`jmp rel`); None otherwise.
    branch_target_rva: Optional[int]


class CodeAnchor:
    """
    Wraps an XIVProcess and provides string-xref + local-disasm primitives.

    We work entirely in RVAs: 0 == start of base_image. Convert to absolute
    VA only when calling write_memory.
    """

    def __init__(self, process):
        self._proc = process
        self._image: bytes = process.base_image
        self._base: int = process.get_base_address()
        # capstone state is cheap to construct but we reuse one instance
        self._md = Cs(CS_ARCH_X86, CS_MODE_64)
        self._md.detail = True

    # --- conversions --------------------------------------------------------

    def rva_to_va(self, rva: int) -> int:
        return self._base + rva

    def va_to_rva(self, va: int) -> int:
        return va - self._base

    # --- raw search --------------------------------------------------------

    def find_string(self, needle: bytes) -> Optional[int]:
        """Return RVA of `needle` in the loaded image, or None."""
        idx = self._image.find(needle)
        return idx if idx >= 0 else None

    def find_all_strings(self, needle: bytes) -> List[int]:
        out, pos = [], 0
        while True:
            i = self._image.find(needle, pos)
            if i < 0:
                return out
            out.append(i)
            pos = i + 1

    # --- lea [rip+disp32] xref scanning ------------------------------------

    def find_lea_to(self, target_rva: int, reg: str) -> List[int]:
        """
        Return RVAs of every `lea <reg>, [rip+disp32]` whose computed target
        equals `target_rva`. Scans the entire image — fine for one-shot
        anchor work but cache results in plugin state if you need them often.
        """
        prefix = _LEA_PREFIX[reg]
        out: List[int] = []
        pos = 0
        while True:
            i = self._image.find(prefix, pos)
            if i < 0:
                return out
            disp = int.from_bytes(self._image[i + 3:i + 7], "little",
                                  signed=True)
            if i + 7 + disp == target_rva:
                out.append(i)
            pos = i + 1

    def find_lea_above(self, anchor_rva: int, reg: str,
                       max_back: int = 64) -> Optional[int]:
        """
        Walk backward from `anchor_rva` looking for the nearest
        `lea <reg>, [rip+disp32]` within max_back bytes. Returns its RVA.
        """
        prefix = _LEA_PREFIX[reg]
        start = max(0, anchor_rva - max_back)
        window = self._image[start:anchor_rva]
        i = window.rfind(prefix)
        return start + i if i >= 0 else None

    def read_lea_target(self, lea_rva: int) -> int:
        """Decode the [rip+disp32] target of a 7-byte lea at lea_rva."""
        disp = int.from_bytes(self._image[lea_rva + 3:lea_rva + 7], "little",
                              signed=True)
        return lea_rva + 7 + disp

    # --- local disassembly --------------------------------------------------

    def disasm(self, start_rva: int, n_bytes: int = 256) -> List[Insn]:
        chunk = self._image[start_rva:start_rva + n_bytes]
        out: List[Insn] = []
        for ins in self._md.disasm(chunk, start_rva):
            tgt = None
            if ins.operands and ins.operands[0].type == X86_OP_IMM:
                tgt = ins.operands[0].imm
            out.append(Insn(
                rva=ins.address, size=ins.size,
                mnemonic=ins.mnemonic, op_str=ins.op_str,
                bytes=bytes(ins.bytes),
                branch_target_rva=tgt,
            ))
        return out

    def disasm_until_ret(self, start_rva: int,
                         max_bytes: int = 1024) -> List[Insn]:
        """Linear disasm that stops at the first ret/retn (or runs out)."""
        out = []
        for ins in self.disasm(start_rva, max_bytes):
            out.append(ins)
            if ins.mnemonic in ("ret", "retn"):
                break
        return out

    # --- pattern matching over instruction lists ----------------------------

    @staticmethod
    def find_insn_pattern(insns: Sequence[Insn],
                          pattern: Sequence) -> Optional[int]:
        """
        Find the first index `i` in `insns` such that the next len(pattern)
        instructions match. Each pattern element is one of:

          - a string  -> match Insn.mnemonic exactly
          - a (mnemonic, op_str) tuple -> match both exactly
          - a callable Insn -> bool

        Returns None if no match.
        """
        n, m = len(insns), len(pattern)
        for i in range(n - m + 1):
            ok = True
            for k, p in enumerate(pattern):
                ins = insns[i + k]
                if isinstance(p, str):
                    if ins.mnemonic != p:
                        ok = False; break
                elif isinstance(p, tuple):
                    mn, op = p
                    if ins.mnemonic != mn or ins.op_str != op:
                        ok = False; break
                elif callable(p):
                    if not p(ins):
                        ok = False; break
                else:
                    raise TypeError(f"bad pattern element: {p!r}")
            if ok:
                return i
        return None

    @staticmethod
    def cond_jumps_to(insns: Sequence[Insn], target_rva: int) -> List[Insn]:
        """All conditional jumps in `insns` whose target == target_rva."""
        return [
            ins for ins in insns
            if ins.mnemonic in COND_JUMPS
            and ins.branch_target_rva == target_rva
        ]

    @staticmethod
    def find_imm_load(insns: Sequence[Insn], reg: str,
                      *, last: bool = False) -> Optional[int]:
        """
        Find a `mov <reg>, imm` in `insns` and return the imm.  By default
        returns the first match; pass `last=True` to return the last (handy
        when the early-prologue load is uninteresting and the magic value is
        loaded just before a registry/lookup call).
        """
        found = None
        for ins in insns:
            if ins.mnemonic != "mov":
                continue
            parts = ins.op_str.split(", ", 1)
            if len(parts) != 2 or parts[0] != reg:
                continue
            try:
                val = int(parts[1], 0)
            except ValueError:
                continue
            if not last:
                return val
            found = val
        return found

    @staticmethod
    def find_bool_fold(insns: Sequence[Insn]) -> Optional[Tuple[int, int]]:
        """
        Locate the standardized bool-fold epilog seen in many SE Lua-callback
        predicates:

            xor   R_a, R_a            ; R_a = 0
            movzx R_b32, R_b8         ; R_b32 = (uint8) R_b8 — preserves bool
            cmp   al, 1               ; was the helper call's bool true?
            cmove R_b32, R_a          ; if so, R_b = 0  (return false)

        The constraint we enforce is structural, not textual: R_a and R_b
        can be any two distinct GPRs as long as R_b8 is the low byte of
        R_b32 and the cmove conditional moves R_a into R_b32.

        Returns (start_index, end_index_exclusive) into `insns`, or None.
        """
        n = len(insns)
        for i in range(n - 3):
            i_xor, i_movzx, i_cmp, i_cmove = insns[i:i + 4]

            # --- xor R_a, R_a ---
            if i_xor.mnemonic != "xor":
                continue
            xp = i_xor.op_str.split(", ", 1)
            if len(xp) != 2 or xp[0] != xp[1] or xp[0] not in _GPR32:
                continue
            r_a = xp[0]

            # --- movzx R_b32, R_b8  (R_b8 must be R_b32's low byte) ---
            if i_movzx.mnemonic != "movzx":
                continue
            mp = i_movzx.op_str.split(", ", 1)
            if len(mp) != 2 or mp[0] not in _GPR32:
                continue
            r_b32 = mp[0]
            if mp[1] != _LOW8_OF[r_b32]:
                continue
            if r_b32 == r_a:
                continue

            # --- cmp al, 1 ---
            if i_cmp.mnemonic != "cmp" or i_cmp.op_str != "al, 1":
                continue

            # --- cmove/cmovz R_b32, R_a ---
            if i_cmove.mnemonic not in ("cmove", "cmovz"):
                continue
            cp = i_cmove.op_str.split(", ", 1)
            if len(cp) != 2 or cp[0] != r_b32 or cp[1] != r_a:
                continue

            return (i, i + 4)
        return None
