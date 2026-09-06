#!/usr/bin/env python3
"""
find_brain.py - locate the user's Second Brain Link brain, wherever it currently lives.

A vault moves, and a brain folder gets renamed. So nothing here is hardcoded as a fact: a
directory is your brain only if <dir>/00-me/identity.md carries a `title:` matching the
`owner:` in your own profile.

That also keeps other people's brains out — a vault can hold several — and it reads exactly
one file per candidate to decide.

    python3 find_brain.py            # print the path, or nothing and exit 1
    python3 find_brain.py --verbose  # say how it was found, on stderr

Resolution order, cheapest and most certain first:
    1. $SECOND_BRAIN_HOME               (explicit override, always wins)
    2. the current directory and its parents  (Studio starts Claude Code inside the vault)
    3. the recorded path in <state root>/brain-path.txt  (last known good)
    4. a bounded search of the usual roots
Whatever it finds, it re-records in brain-path.txt so step 4 is rare.
"""
import argparse, os, pathlib, re, sys

def owner_name():
    """Who this installation belongs to — read from the profile, never hardcoded.

    Returns None when there is no profile yet (a fresh install, mid-onboarding), and the
    caller then accepts whichever brain it is standing in rather than refusing to start.
    """
    try:
        from paths import profile_dir, work_root, state_root, LAYER
        for cand in (profile_dir(), state_root().parent / LAYER / "profile",
                     work_root() / LAYER / "profile"):
            f = pathlib.Path(cand) / "profile.md"
            if f.is_file():
                for line in f.read_text(encoding="utf-8", errors="replace").split("\n")[:30]:
                    m = re.match(r"^owner:\s*(.+?)\s*$", line)
                    if m:
                        return m.group(1).strip().strip('"\'').lower()
    except (OSError, ImportError):
        pass                      # no profile reachable yet — onboarding will write one
    return None


OWNER = owner_name()
MAX_PARENTS = 8

# Where a vault plausibly sits. Bounded on purpose - this never walks the whole disk.
ROOTS = ["~/Documents", "~/Desktop", "~/",
         "~/Library/Mobile Documents/com~apple~CloudDocs"]   # macOS iCloud; harmless elsewhere
VAULT_HINTS = ["SecondBrainLink", "SecondBrain", "second-brain-link", "secondbrainlink"]


def is_brain(p):
    """Is this directory a brain belonging to the person this installation is for?

    Identity comes from `00-me/identity.md` -> `title:`, never from the folder name: a vault can
    hold several people's brains, and folder names get renamed. When no profile exists yet there is
    nobody to match against, so any brain counts - that is the onboarding case, and it is the only
    time this is permissive.
    """
    from paths import layer
    f = pathlib.Path(p) / layer(p, "root") / "identity.md"
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                low = line.strip().lower()
                if low.startswith("title:"):
                    return True if OWNER is None else OWNER in low
                if low == "---" and i:
                    break
    except OSError:
        return False
    return False


def owner_of(p):
    """The `title:` of any brain directory, whoever it belongs to, or None if it is not a brain."""
    from paths import layer
    f = pathlib.Path(p) / layer(p, "root") / "identity.md"
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                if line.strip().lower().startswith("title:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def usable(p):
    from paths import layer
    return p and is_brain(p) and (pathlib.Path(p) / layer(p, "career")).is_dir()


def cwd_brain():
    """Any brain at or above cwd, whoever owns it. Second Brain Studio starts Claude Code inside
    the brain it has selected, so this is what the app chose - even when it is not the user's."""
    here = pathlib.Path.cwd().resolve()
    for d in [here] + list(here.parents)[:MAX_PARENTS]:
        if owner_of(d):
            return d, owner_of(d)
    return None, None


def from_env():
    v = os.environ.get("SECOND_BRAIN_HOME")
    if not v:
        return None
    p = pathlib.Path(os.path.expanduser(v))
    if usable(p):
        return p
    # pointed at the vault rather than the brain
    for d in sorted(p.glob("personal/*")) + sorted(p.glob("*")):
        if usable(d):
            return d
    return None


def from_cwd():
    here = pathlib.Path.cwd().resolve()
    for d in [here] + list(here.parents)[:MAX_PARENTS]:
        if usable(d):
            return d
        for sub in sorted(d.glob("personal/*")):
            if usable(sub):
                return sub
    return None


def state_root():
    """Delegates to paths.py — the single resolver. Kept as a function so callers
    that already import `state_root` keep working."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paths import state_root
    return state_root()


def remembered():
    f = state_root() / "brain-path.txt"
    try:
        p = pathlib.Path(f.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return p if usable(p) else None


def searched():
    for root in ROOTS:
        r = pathlib.Path(os.path.expanduser(root))
        if not r.is_dir():
            continue
        for hint in VAULT_HINTS:
            for vault in sorted(r.glob(hint)) + sorted(r.glob(f"*/{hint}")):
                for pat in ("vault/personal/*", "personal/*", "*"):
                    for d in sorted(vault.glob(pat)):
                        if usable(d):
                            return d
    return None


def remember(p):
    try:
        root = state_root()
        if root.is_dir():
            (root / "brain-path.txt").write_text(str(p) + "\n", encoding="utf-8")
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--who", action="store_true",
                    help="print who owns the brain at/above cwd (what Studio has selected) and stop")
    a = ap.parse_args()

    if a.who:
        d, name = cwd_brain()
        if d:
            print(f"{name}\t{d}")
            return 0 if (OWNER is None or OWNER in (name or "").lower()) else 2
        print("none")
        return 1
    for how, fn in (("$SECOND_BRAIN_HOME", from_env), ("cwd", from_cwd),
                    ("brain-path.txt", remembered), ("search", searched)):
        p = fn()
        if p:
            p = p.resolve()
            remember(p)
            if a.verbose:
                print(f"found via {how}: {p}", file=sys.stderr)
            print(p)
            return 0
    if a.verbose:
        print("no brain of the user's found - skip the brain step", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
