#!/usr/bin/env python3
"""Emitter registry. Adding an output target = add one emitter module here.

Mirrors `sources/__init__.py`. `obsidian` is the DEFAULT and must always be
present; `gbrain` is additive/opt-in (registered when available)."""
from .obsidian import ObsidianEmitter

ALL = [ObsidianEmitter]

# GBrain is optional/additive; register it if the module is present.
try:
    from .gbrain import GBrainEmitter
    ALL.append(GBrainEmitter)
except Exception:
    pass

BY_NAME = {e.name: e for e in ALL}


def select(names):
    """Resolve a list of emitter names (or 'both') to instantiated emitters.
    Unknown names are ignored with the caller able to detect the gap via BY_NAME.
    'both' expands to obsidian + gbrain (whichever are registered)."""
    if isinstance(names, str):
        names = [names]
    out, seen = [], set()
    for n in names:
        if n == "both":
            want = ["obsidian", "gbrain"]
        else:
            want = [n]
        for w in want:
            if w in BY_NAME and w not in seen:
                seen.add(w)
                out.append(BY_NAME[w]())
    return out
