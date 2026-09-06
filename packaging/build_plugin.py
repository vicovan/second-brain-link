#!/usr/bin/env python3
"""
build_plugin.py — zip a Second Brain Link plugin into an installable archive.

Plugins are a SEPARATE distribution surface from the engine skill. `build_skill.py`
deliberately does not bundle `plugins/`: the engine's zero-network guarantee is the
reason its privacy claim is verifiable, and a plugin that reaches live services must
not be able to weaken it. A plugin declares its own network access in its manifest.

Two packagings, one source — the same split the engine skill uses:

  claude   plugins/<name>/  as-is            -> dist/plugins/claude/<name>.zip
           A Claude Code PLUGIN: several skills under one root, loaded together, with
           ${CLAUDE_PLUGIN_ROOT} resolving cross-skill script paths.

  openai   plugins/<name>/  FLATTENED        -> dist/plugins/openai/<name>/ + .skill
           Codex has no plugin concept — it discovers self-contained SKILLS from
           ~/.agents/skills/. So the skills' scripts collapse into one scripts/ dir,
           each skill's SKILL.md becomes references/<skill>.md, and the manifest is
           plugins/<name>/providers/openai/SKILL.md. Flattening is safe because no
           script or reference basename collides, and every cross-script import is a
           sibling import that only works flat anyway.

Install:
    claude --plugin-dir plugins/<name>              # Claude, straight from source
    claude --plugin-url <url-to-the-zip>            # Claude, from a release
    python3 packaging/build_plugin.py <name> --provider claude --install
                                                    # -> ~/.claude/skills/<name>
    python3 packaging/build_plugin.py <name> --provider openai --install
                                                    # Codex -> ~/.agents/skills/<name>

Usage:
  python3 packaging/build_plugin.py [<name>|all] [--provider claude|openai|all] [--install]

Why a python zip: a `cd plugins && zip` subshell silently no-ops in some sandboxes
and ships a stale archive — we build the zip in-process so it can't drift.
"""
import json
import os
import shutil
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"
DIST = REPO / "dist" / "plugins"
# Where an --install lands, per provider.
#
# ~/.claude/skills/<name> is a first-class Claude Code plugin location — a plugin folder
# there loads as a "skills-directory plugin" (`claude plugin list` shows it as
# <name>@skills-dir), which is also where `claude plugin init` scaffolds one. Second Brain
# Studio reads the same directory, so a single install serves the CLI and both Studios.
# That is the whole point: the plugin is maintained in this repo and installed from it,
# and nothing ships a second copy.
INSTALL_DIRS = {
    "claude": Path.home() / ".claude" / "skills",
    "openai": Path.home() / ".agents" / "skills",
}

SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}
SKIP_SUFFIX = {".pyc", ".pyo"}
# A user's ledger must never reach a distributed archive, even if they ran the plugin
# from inside the repo. Mirrors plugins/.gitignore — belt and braces.
SKIP_DIRS = {"45-jobs", "_state", "JobData", "reports", "applications"}
# providers/ holds OTHER packagings' manifests — each build takes only its own.
CLAUDE_SKIP_DIRS = SKIP_DIRS | {"providers"}
SKIP_FILES = {"seen.json", "brain-path.txt", "companies.txt", "ats_pool.json",
              "last-run.txt", "snooze.txt", "nudged.txt", "lessons.md"}
SKIP_DATA_SUFFIX = {".jsonl", ".pdf", ".docx"}


def _keep(rel: Path, skip_dirs=None) -> bool:
    parts = set(rel.parts[:-1])
    if parts & (skip_dirs or SKIP_DIRS) or parts & SKIP_NAMES:
        return False
    name = rel.name
    if name in SKIP_NAMES or name in SKIP_FILES:
        return False
    if rel.suffix in SKIP_SUFFIX or rel.suffix in SKIP_DATA_SUFFIX:
        return False
    return True


def _meta(name: str):
    """(src, manifest dict) or (src, None) when this is not a plugin."""
    src = PLUGINS / name
    manifest = src / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return src, None
    try:
        return src, json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ! {name}: plugin.json is not valid JSON — {e}")
        return src, None


def build_openai(name: str) -> bool:
    """Flatten the plugin into a single Codex skill folder + .skill zip."""
    src, meta = _meta(name)
    if not meta:
        print(f"  ! {name}: no usable .claude-plugin/plugin.json")
        return False
    man = src / "providers" / "openai" / "SKILL.md"
    if not man.is_file():
        print(f"  - {name}: no providers/openai/SKILL.md — skipping openai packaging")
        return True                      # not an error: a plugin may be Claude-only

    out = DIST / "openai" / name
    if out.exists():
        shutil.rmtree(out)
    (out / "scripts").mkdir(parents=True)
    (out / "references").mkdir(parents=True)

    # 1. every skill's scripts -> one flat scripts/ (sibling imports then resolve)
    seen: dict[str, Path] = {}
    for f in sorted(src.glob("skills/*/scripts/*")):
        if not f.is_file() or f.name in SKIP_NAMES or f.suffix in SKIP_SUFFIX:
            continue
        if f.name in seen:
            print(f"  ! {name}: script name collision — {f.name} in {seen[f.name]} and {f}")
            return False
        seen[f.name] = f
        shutil.copy2(f, out / "scripts" / f.name)

    # 2. each skill's SKILL.md becomes the workflow reference the manifest routes to
    for sk in sorted(src.glob("skills/*/SKILL.md")):
        shutil.copy2(sk, out / "references" / (sk.parent.name + ".md"))

    # 3. references + assets, flat (checked for collisions the same way)
    ref_seen: dict[str, Path] = {}
    for f in sorted(list(src.glob("skills/*/references/*")) + list(src.glob("skills/*/assets/*"))):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        if f.name in ref_seen:
            print(f"  ! {name}: reference name collision — {f.name}")
            return False
        ref_seen[f.name] = f
        shutil.copy2(f, out / "references" / f.name)

    # 4. the manifest + any provider extras (agents/openai.yaml)
    shutil.copy2(man, out / "SKILL.md")
    for f in sorted((src / "providers" / "openai").rglob("*")):
        if not f.is_file() or f.name == "SKILL.md" or f.name in SKIP_NAMES:
            continue
        dest = out / f.relative_to(src / "providers" / "openai")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    # 5. docs + licence so the installed skill can explain itself offline
    for extra in ("LICENSE", "README.md", "requirements.txt"):
        if (src / extra).is_file():
            shutil.copy2(src / extra, out / extra)

    # 6. ${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/ -> scripts/  (flat layout)
    for f in list(out.rglob("*.md")) + list(out.rglob("*.sh")):
        txt = f.read_text(encoding="utf-8")
        new = re.sub(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/[a-z-]+/scripts/", "scripts/", txt)
        new = new.replace("${CLAUDE_PLUGIN_ROOT}/", "")
        if new != txt:
            f.write_text(new, encoding="utf-8")

    n = _zip(out, DIST / "openai" / f"{name}.skill", name)
    print(f"  ✓ {name} v{meta['version']} (openai): {n} files → "
          f"{(DIST / 'openai' / (name + '.skill')).relative_to(REPO)}; folder → "
          f"{out.relative_to(REPO)}/")
    return True


def _zip(folder: Path, zip_path: Path, arc_root: str) -> int:
    if zip_path.exists():
        zip_path.unlink()
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
            for f in sorted(files):
                if f in SKIP_NAMES:
                    continue
                full = Path(dp) / f
                z.write(full, str(Path(arc_root) / full.relative_to(folder)))
                n += 1
    return n


def build(name: str) -> bool:
    src = PLUGINS / name
    manifest = src / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        print(f"  ! {name}: no .claude-plugin/plugin.json — not a plugin")
        return False
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ! {name}: plugin.json is not valid JSON — {e}")
        return False
    for key in ("name", "version", "description"):
        if not meta.get(key):
            print(f"  ! {name}: plugin.json is missing '{key}'")
            return False

    # A plugin that reaches the network says so, in the manifest, where a reader can find it.
    net = meta.get("network") or {}
    net_note = ""
    if net.get("required"):
        eps = net.get("endpoints") or []
        net_note = f"  network: {len(eps)} declared endpoint(s)"

    (DIST / "claude").mkdir(parents=True, exist_ok=True)
    zip_path = DIST / "claude" / f"{name}.zip"
    if zip_path.exists():
        zip_path.unlink()

    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES and d not in CLAUDE_SKIP_DIRS]
            for f in sorted(files):
                full = Path(dp) / f
                rel = full.relative_to(src)
                if not _keep(rel, CLAUDE_SKIP_DIRS):
                    continue
                z.write(full, str(Path(name) / rel))
                n += 1

    print(f"  ✓ {name} v{meta['version']} (claude): {n} files → "
          f"{zip_path.relative_to(REPO)} ({zip_path.stat().st_size} bytes)")
    if net_note:
        print(net_note)
    return True


def discover():
    if not PLUGINS.is_dir():
        return []
    return sorted(p.name for p in PLUGINS.iterdir()
                  if p.is_dir() and (p / ".claude-plugin" / "plugin.json").is_file())


def install(name: str, provider: str) -> bool:
    """Copy a built packaging into the agent's discovery dir."""
    dest_root = INSTALL_DIRS.get(provider)
    if not dest_root:
        print(f"  ! {provider}: no install location for this provider")
        return True
    # Claude keeps the plugin whole (skills, commands, hooks, .claude-plugin), so it is
    # installed from the SOURCE folder. Codex has no plugin concept and gets the
    # flattened build tree instead.
    src = (REPO / "plugins" / name) if provider == "claude" else (DIST / provider / name)
    if not src.is_dir():
        print(f"  ! nothing built for {name}/{provider}")
        return False
    dest = dest_root / name
    dest_root.mkdir(parents=True, exist_ok=True)
    # A SYMLINK here is the normal developer install — it points at the checkout so the
    # plugin stays current with no copy step. rmtree() on a symlink raises; worse, a
    # careless follow would delete the repo through it. Unlink the link itself.
    if dest.is_symlink():
        print(f"  ! {dest} is a symlink to {os.readlink(dest)} — leaving it alone")
        print("    (it already tracks the source; remove it yourself to install a copy)")
        return True
    if dest.exists():
        shutil.rmtree(dest)
    # SKIP_DIRS as well as SKIP_NAMES: the claude install copies from SOURCE, and a
    # developer who ran the plugin inside the repo has a ledger sitting in it. The zip
    # build filters those for the same reason — an install must not carry one either.
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(*SKIP_NAMES, *SKIP_DIRS, "*.pyc", "*.pyo"),
    )
    print(f"  ⇒ installed {name} ({provider}) → {dest}")
    return True


def main():
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    do_install = "--install" in argv
    provider = "all"
    if "--provider" in argv:
        i = argv.index("--provider")
        if i + 1 < len(argv):
            provider = argv[i + 1].lower()
            if provider in args:
                args.remove(provider)
    which = (args[0] if args else "all").lower()
    names = discover() if which == "all" else [which]
    if not names:
        print("No plugins found under plugins/")
        sys.exit(0)
    provs = ["claude", "openai"] if provider == "all" else [provider]
    print(f"Packaging plugin(s): {', '.join(names)} → {', '.join(provs)}")
    ok = True
    for n in names:
        for pv in provs:
            ok = (build(n) if pv == "claude" else build_openai(n)) and ok
            if do_install:
                ok = install(n, pv) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
