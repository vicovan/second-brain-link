#!/usr/bin/env python3
"""
build_all.py — build EVERYTHING a user can install, and write dist/manifest.json.

One command, one source: the engine skill (both providers) and every plugin (both
providers), exactly as build_skill.py / build_plugin.py make them, plus a manifest the
installers and Second Brain Studio read:

  dist/claude/second-brain-link.skill        dist/openai/second-brain-link.skill
  dist/plugins/claude/<agent>.zip            dist/plugins/openai/<agent>.skill
  dist/manifest.json   (sbl-dist/1: name, kind, provider, version, rev, sha256, bytes, file)

`rev` is a hash of the unpacked CONTENT (paths + bytes, not zip timestamps), so it only
changes when something a user would install actually changed — that is what Studio's
"Update agents" check and the payload staleness guard compare.

Studio never keeps its own copy of any of this: its installer payload is generated from
this dist/ (second-brain-studio/scripts/build-payload.mjs). Edit here, run this, done.

Usage:
  python3 packaging/build_all.py            # build all + manifest
  python3 packaging/build_all.py --check    # exit 1 if dist/ is older than the sources
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DIST = REPO / "dist"
sys.path.insert(0, str(HERE))

import build_plugin  # noqa: E402
import build_skill  # noqa: E402

SOURCE_DIRS = [REPO / "engine", REPO / "providers", REPO / "plugins", REPO / "docs" / "SOURCES.md",
               REPO / "docs" / "ENTITY-MAP.md", HERE]
PROVIDER_LABEL = {"claude": "claude", "openai": "codex"}


def _tree_rev(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.name not in build_plugin.SKIP_NAMES and p.suffix not in build_plugin.SKIP_SUFFIX:
            h.update(p.relative_to(folder).as_posix().encode())
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _zip_rev(zpath: Path) -> str:
    import zipfile  # noqa: PLC0415

    h = hashlib.sha256()
    with zipfile.ZipFile(zpath) as z:
        for n in sorted(z.namelist()):
            h.update(n.encode())
            h.update(b"\0")
            h.update(z.read(n))
    return h.hexdigest()[:16]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _entry(name, kind, provider, version, archive: Path, rev: str):
    return {
        "name": name,
        "kind": kind,
        "provider": PROVIDER_LABEL[provider],
        "version": version,
        "rev": rev,
        "file": archive.relative_to(DIST).as_posix(),
        "sha256": _sha(archive),
        "bytes": archive.stat().st_size,
        # where it installs, relative to the user's home, on every OS
        "installs_to": (".claude/skills/" if provider == "claude" else ".agents/skills/") + name,
    }


def newest_source_mtime() -> float:
    newest = 0.0
    for s in SOURCE_DIRS:
        if s.is_file():
            newest = max(newest, s.stat().st_mtime)
            continue
        for dp, dirs, files in os.walk(s):
            dirs[:] = [d for d in dirs if d not in build_plugin.SKIP_NAMES and d not in build_plugin.SKIP_DIRS]
            for f in files:
                if f in build_plugin.SKIP_NAMES or f.endswith((".pyc", ".pyo")):
                    continue
                newest = max(newest, (Path(dp) / f).stat().st_mtime)
    return newest


def check() -> int:
    man = DIST / "manifest.json"
    if not man.is_file():
        print("dist/manifest.json missing — run: python3 packaging/build_all.py")
        return 1
    if newest_source_mtime() > man.stat().st_mtime:
        print("dist/ is older than engine/ or plugins/ — run: python3 packaging/build_all.py")
        return 1
    print("dist/ is current")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    print("Building everything installable (engine + plugins, Claude + Codex)")
    ok = True
    engine_version = (REPO / "engine" / "VERSION").read_text().strip() if (REPO / "engine" / "VERSION").is_file() else "0"
    entries = []
    for prov in ("claude", "openai"):
        if not build_skill.build(prov):
            ok = False
            continue
        arc = DIST / prov / f"{build_skill.SKILL}.skill"
        entries.append(_entry(build_skill.SKILL, "engine", prov, engine_version, arc,
                              _tree_rev(DIST / prov / build_skill.SKILL)))

    names = build_plugin.discover()
    if not build_plugin.check_shared(names):
        return 1
    for n in names:
        meta = json.loads((build_plugin.PLUGINS / n / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        if build_plugin.build(n):
            arc = build_plugin.DIST / "claude" / f"{n}.zip"
            entries.append(_entry(n, "agent", "claude", meta["version"], arc, _zip_rev(arc)))
        else:
            ok = False
        if build_plugin.build_openai(n):
            arc = build_plugin.DIST / "openai" / f"{n}.skill"
            if arc.is_file():
                entries.append(_entry(n, "agent", "openai", meta["version"], arc,
                                      _tree_rev(build_plugin.DIST / "openai" / n)))
        else:
            ok = False

    manifest = {
        "schema": "sbl-dist/1",
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": "https://github.com/vicovan/second-brain-link/raw/main/dist/",
        "artifacts": entries,
    }
    (DIST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ dist/manifest.json — {len(entries)} artifacts")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
