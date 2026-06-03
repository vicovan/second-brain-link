#!/usr/bin/env python3
"""
emitters/obsidian.py — the default, primary output target.

Renders the canonical Collector into the Obsidian-native vault (the experience
that has always shipped). This is the DEFAULT emitter and must never regress:
with no `--emit` flag the builder selects exactly this, producing byte-for-byte
the same vault as before the emitter refactor.

Implementation note: the actual layer-by-layer rendering lives in
`build_vault.VaultWriter` (and its frontmatter/link helpers). `ObsidianEmitter`
is the stable seam in front of it so other targets (e.g. GBrain) can be added
without forking the builder. `VaultWriter` is imported lazily to avoid an import
cycle (build_vault imports the emitters package at module load).
"""
from .base import Emitter


class ObsidianEmitter(Emitter):
    """Default emitter: renders the Collector into the Obsidian-native vault. A thin
    seam over build_vault.VaultWriter so other targets can be added without forking
    the builder; output must stay byte-identical to the pre-emitter-refactor vault."""

    name = "obsidian"

    def emit(self, collector, out_dir, *, subject="person", meta=None):
        """Build the Obsidian vault by delegating to VaultWriter (imported lazily to
        break the build_vault↔emitters import cycle)."""
        from build_vault import VaultWriter  # lazy: breaks the import cycle
        VaultWriter(collector, out_dir).build()
