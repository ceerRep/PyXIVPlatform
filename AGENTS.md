# AGENTS.md — Guide for working on PyXIVPlatform

This is a long-lived guide for any agent (human or AI) working on this repo. It is not a status log; do not put dates, "verified at patch 7.x", or one-off addresses in here. Those belong in commit messages and code comments next to the values they annotate.

## What this project is

PyXIVPlatform is a Python automation platform for FFXIV (auto-craft, auto-fish, chat-log scanning). It works by attaching to the running `ffxiv_dx11.exe`, locating game state via IDA-style byte signatures + RIP / pointer offset chains, and acting on it through key-sends or a sidecar IPC plugin.

The fragile part of the project is the set of signatures and offsets in `config_*/`. Every FFXIV major patch can shift them. Most "agent work" on this repo is: a feature is broken → find the new sig/offset → patch the JSON.

## Codebase layout

- `PyXIVPlatform/platform.py` — config merging (multi-directory `dict.update`), plugin loader.
- `plugins/XIVMemory/` — process attach, sig scanning, pointer-chain following. `xivprocess.follow_pointer_path` is the primitive everyone else builds on. `code_anchor.py` provides string-xref + local-disasm primitives for plugins that patch live code without brittle byte signatures.
- `plugins/GameState/` — game state enums (`RoleState`, `CraftState`, `BiteType`), memory scan reader, `BackgroundTask` utility. Other plugins read state via `GameState.instance`.
- `plugins/ActionSender/` — `ActionDispatcher`: send an in-game action via PostNamazu and await log-based confirmation.
- `plugins/CraftBot/` — crafting automation (craft, handin, jump).
- `plugins/AutoFisher/` — fishing automation (autofish, changeplace, patient buff logic).
- `plugins/LogScanner/` — chat & system log ring buffer reader. `LogType` constants live here.
- `plugins/PostNamazuWrapper/` — sends in-game commands via the bundled PostNamazu DLL.
- `config_common/`, `config_CN/`, `config_Global/` — per-region sigs and offsets. JSON, merged in argv order.
- `recipes/` — user-defined craft macros.

## Where to look when something breaks

When a sig stops resolving or an offset reads garbage, these upstream projects are the fastest source of truth. They are all actively maintained and CN/Global agnostic at the data level.

| Project | Why it's useful |
|---|---|
| [aers/FFXIVClientStructs](https://github.com/aers/FFXIVClientStructs) | Authoritative C# reverse-engineered struct definitions for the entire client. Updated within days of every patch. Includes per-version breaking-change docs. Start here for "what does this struct look like now". |
| [OverlayPlugin/cactbot](https://github.com/OverlayPlugin/cactbot) | Maintains live byte signatures for charmap, job data, in-combat state, entity memory layout. Cross-check signatures here when ours stops being unique. |
| [PunishXIV/Artisan](https://github.com/PunishXIV/Artisan) | Crafting plugin. Shows the modern, struct-based way to read crafting condition / quality / durability / step without raw memory scanning. |
| [FFXIV-CombatReborn/GatherBuddyReborn](https://github.com/FFXIV-CombatReborn/GatherBuddyReborn) | Fishing & gathering. Has well-maintained bite-type / fishing-state enums useful for cross-checking RoleState. |
| [Natsukage/PostNamazu](https://github.com/Natsukage/PostNamazu) | Upstream of the bundled DLL. When in-game command sending breaks after a patch, swap in a new release; no Python changes needed. |
| [thewakingsands/ffxiv-datamining-cn](https://github.com/thewakingsands/ffxiv-datamining-cn) and [xivapi/ffxiv-datamining](https://github.com/xivapi/ffxiv-datamining) | Raw game-data CSV dumps (ActionTimeline, Action, Status, Item, …). Both regions stay byte-identical at the data level — pick whichever loads faster for you. |
| [goatcorp/Dalamud](https://github.com/goatcorp/Dalamud) | Reference for high-level enums (`ConditionFlag`, etc.) when you want a sanity check on naming. |
| [ravahn/FFXIV_ACT_Plugin](https://github.com/ravahn/FFXIV_ACT_Plugin) | The ACT-side reference for log-line / network parsing. |
| [strings.wakingsands.com](https://strings.wakingsands.com) | Full-text search across all game CSV strings (Action, Status, LogMessage, …) in CN/JP/EN. Use the Elasticsearch `_search` endpoint to look up log patterns, buff names, or action names when a patch renames something. |

## Mental model: how a sig/offset entry works

Every sig in `config_*/*.json` is consumed via `XIVProcess.find_signature` + `XIVProcess.follow_pointer_path` (`plugins/XIVMemory/xivprocess.py`). A path is a list of integers; the first element pairs with `inst_pos` to do a RIP-relative jump, subsequent zero-`inst_pos` steps are 64-bit pointer dereferences with an added offset.

```
path = [inst_pos, off1, off2, ...]
inst_pos != 0  →  base = sig_addr + inst_pos + 4 + int32(sig_addr + inst_pos)   # RIP
inst_pos == 0  →  base = uint64(base) + offset                                   # deref
```

Two consequences worth remembering:

- A path written for an old sig **does not transfer** to a new sig with a different instruction shape (e.g. `mov r,[rip+disp32]` vs `lea r,[rip+disp32]; call …`). Re-derive from scratch.
- `0` is propagated as "null pointer; abort" — don't read this as "offset zero".

## Conventions

- **JSON has no comments.** Configs are merged with `dict.update`, so any unknown key is silently ignored. Use `"_comment_<key>": "…"` siblings for inline annotation; logic never reads them.
- **Annotate at the value, not in this file.** When you fix a sig or offset, put the *why* and *gotchas* in a `_comment_*` next to the value (and/or a code comment if the consumer is in Python). This file should remain a guide; per-value details rot too fast for here.
- **Don't paste live RVAs / VAs in source.** They differ per patch and per region. Validate uniqueness with a throwaway script instead — don't bake the address into a config or comment.
- **Three-step sig validation:** (1) Python `re` over the binary should hit exactly once; (2) the resolved RIP target must land in a sane PE section (`.data` for globals, `.text` for code); (3) cross-check the semantic against an upstream project before trusting it.
- **CN ≈ Global at the data and struct level.** ActionTimeline.csv, struct field offsets, etc. are kept in sync. Only RVAs of code and globals differ. If a region-specific config diverges on a *struct* offset, suspect a stale config before suspecting SE.
- **Log patterns and action names must be i18n arrays.** Any string matched against game log content or sent via `/ac` must be a `[CN, JP, EN]` array in config, never a hardcoded single-language string. Use `strings.wakingsands.com` to look up the correct text for each locale (query the Elasticsearch `_search` endpoint with the known CN or EN string). SE can rename buff/action names across patches — the config array is the only thing that needs updating.

## Pitfalls

- `PlayerState::Instance()` and similar singletons can return NULL before login. Always null-check the first dereference.
- `find_signature` caches `0` as the "not found" sentinel. Harmless because RVA 0 is the MZ header, but be aware before you put a sig that legitimately resolves at file offset 0.
- A sig hitting more than once is silently *not* unique under the current `re.search` (returns the first match). Confirm uniqueness by counting matches yourself before trusting the runtime.
- Some `RoleState` enum names are misleading (e.g. `FISH_BITE_EXCITE` is actually the "precision hookset" bite). Classification is done via `RoleState.is_casting` / `.is_baited` / `.bite_type` properties backed by frozen sets — enum names are safe to rename.

## Open questions

Living list of unknowns worth resolving when convenient. Add a row when you discover one; remove it when you resolve it. Keep entries terse; details belong in code or commit messages.

| Area | Question |
|---|---|
| `GameState` | The condition byte read at the crafting-state pointer's `+0x38` is empirically 1/2/3/4 during synthesis but has no static xref proving the field's purpose. Confirm or replace with the modern `CraftEventHandler.Condition` / `AddonSynthesis.AtkValues` path used by Artisan. |
| `LogScanner` | The `[16, 0, 0x40, 0x38C]` chain still works but lands inside a large undocumented class mid-struct. Replace with documented `RaptureLogModule` field accessors when bandwidth allows. |
| `RoleState` | `FISH_ASK_COLLECT = 527502` exceeds the ActionTimeline range and is not a binary constant — likely a high-bit flag composed at runtime. Source unknown. |

## Working with IDA

IDA Pro / `idalib` is the right tool for resolving "where does this sig point to and what struct is at the other end". When you spawn an agent for IDA work, give it three constraints up front:

- **Reuse an existing analyzed database.** First-time auto-analysis on the FFXIV binary is slow (tens of minutes) and produces large databases. Open with `run_auto_analysis=False` if one already exists; never write back (`save=False`).
- **Stream findings to a log file as you go**, not just to the agent's final report. Long IDA sessions can be cut off by network or context limits, and intermediate findings are valuable on their own.
- **Set a wall-clock or tool-call budget.** "Find this one struct field" tasks shouldn't run for hours; stop early and hand off rather than chasing the perfect answer.

## Updating this file

When you learn something the next agent will want to know, edit this file. When the thing you learned is specific to a single value (a sig, an offset, an enum entry), put it in a code comment or `_comment_*` field next to that value instead. The split keeps both surfaces useful.
