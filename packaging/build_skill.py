#!/usr/bin/env python3
"""
build_skill.py — assemble a per-provider installable skill from the shared engine.

The engine lives ONCE under `engine/`. Each provider has a thin manifest under
`providers/<provider>/SKILL.md`. This script copies the engine + that manifest
into a self-contained skill dir under `dist/<provider>/second-brain-link/` and
zips it to `dist/<provider>/second-brain-link.skill` (Agent Skills open standard:
same layout for Claude and OpenAI — only the manifest + the in-vault guide differ,
the latter chosen at build time via `build_vault.py --provider`).

Usage:
  python3 packaging/build_skill.py [claude|openai|all]   # default: all

Why a python zip: a `cd skills && zip` subshell silently no-ops in some sandboxes
and ships a stale archive — we build the zip in-process so it can't drift.
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENGINE = REPO / "engine"
PROVIDERS = REPO / "providers"
DIST = REPO / "dist"
SKILL = "second-brain-link"
SKIP = {"__pycache__", ".DS_Store"}


def _clean(p: Path):
    for junk in p.rglob("__pycache__"):
        shutil.rmtree(junk, ignore_errors=True)
    for ds in p.rglob(".DS_Store"):
        ds.unlink(missing_ok=True)


def build(provider: str):
    manifest = PROVIDERS / provider / "SKILL.md"
    if not manifest.exists():
        print(f"  ! no manifest at {manifest.relative_to(REPO)} — skipping {provider}")
        return False
    out_dir = DIST / provider / SKILL
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # engine: scripts/ + references/ + mappings/ (declarative source + brain mappings)
    _clean(ENGINE)
    shutil.copytree(ENGINE / "scripts", out_dir / "scripts",
                    ignore=shutil.ignore_patterns(*SKIP))
    for sub in ("references", "mappings"):
        if (ENGINE / sub).exists():
            shutil.copytree(ENGINE / sub, out_dir / sub,
                            ignore=shutil.ignore_patterns(*SKIP))
    # ship the user-facing export/import guide inside the skill (as
    # references/SOURCES.md — SKILL.md points the agent at it) so the installed
    # agent can answer "how do I export X" offline for all 24 sources.
    for doc in ("SOURCES.md", "ENTITY-MAP.md"):
        src_doc = REPO / "docs" / doc
        if src_doc.exists():
            (out_dir / "references").mkdir(exist_ok=True)
            shutil.copy2(src_doc, out_dir / "references" / doc)
    # the provider manifest becomes the skill's SKILL.md
    shutil.copy2(manifest, out_dir / "SKILL.md")
    # copy any other provider-specific files alongside the manifest (e.g. the
    # Codex `agents/openai.yaml` metadata) so the installable matches the format.
    pdir = PROVIDERS / provider
    for extra in pdir.rglob("*"):
        if extra.name == "SKILL.md" or extra.is_dir() or extra.name in SKIP:
            continue
        dest = out_dir / extra.relative_to(pdir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extra, dest)

    _clean(out_dir)
    # zip it (entries prefixed with second-brain-link/)
    zip_path = DIST / provider / f"{SKILL}.skill"
    if zip_path.exists():
        zip_path.unlink()
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dirs, files in os.walk(out_dir):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for f in files:
                if f in SKIP:
                    continue
                full = Path(dp) / f
                arc = Path(SKILL) / full.relative_to(out_dir)
                z.write(full, str(arc))
                n += 1
    print(f"  ✓ {provider}: {n} files → {zip_path.relative_to(REPO)} "
          f"({zip_path.stat().st_size} bytes); folder → {out_dir.relative_to(REPO)}/")
    return True


# Where each provider's coding agent discovers installed skills.
INSTALL_DIRS = {
    "claude": Path.home() / ".claude" / "skills",
    "openai": Path.home() / ".agents" / "skills",   # OpenAI Codex Agent Skills (user scope)
}


def install(provider: str):
    src = DIST / provider / SKILL
    if not src.is_dir():
        print(f"  ! nothing built for {provider} (run build first)"); return False
    dest_root = INSTALL_DIRS.get(provider)
    if not dest_root:
        print(f"  ! no install dir known for {provider}"); return False
    dest = dest_root / SKILL
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    print(f"  ⇒ installed {provider} → {dest}")
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_install = "--install" in sys.argv[1:]
    which = (args[0] if args else "all").lower()
    provs = sorted(p.name for p in PROVIDERS.iterdir() if p.is_dir()) \
        if which == "all" else [which]
    print(f"Packaging Second Brain Link (engine → {', '.join(provs)})")
    ok = all(build(p) for p in provs)
    if do_install:
        for p in provs:
            install(p)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
