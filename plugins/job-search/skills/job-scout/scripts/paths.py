#!/usr/bin/env python3
"""
paths.py - where everything lives. One resolver, imported by every script.

Two rules matter here.

**Nothing counts directory levels.** The original code did
`Path(__file__).resolve().parents[3] / "JobData"`, which silently returned the wrong
folder the moment the scripts moved one level deeper - and a wrong state root does not
raise, it just hands back an empty `seen.json` and re-applies to jobs already sent.

**Your data never lives next to the plugin.** An earlier version resolved the state root
as "the folder containing the plugin", which is fine when the plugin sits in your own
working folder and catastrophic when it is installed read-only from a marketplace cache
or a source checkout - your CVs and application history would be written into somebody
else's repository. The plugin directory is now used for *reading code only*. Everything
about you is written to a state root chosen from your environment, your brain, or your
home directory - never from where this file happens to sit.

    state_root()    the ledger: seen.json, outcomes.jsonl, reports/, applications/
                    inside a brain that is <brain>/.plugins/job-search/ - hidden from the
                    vault tree, but carried with the brain
    surface_root()  the brain when we are running inside one, else the working folder
    profile_dir()   <surface_root>/45-jobs/profile
    render_dir()    <surface_root>/45-jobs

Run it directly to see every decision:  python3 paths.py
"""
import os, pathlib, sys

# How to recognise the package root. Claude Code loads this as a PLUGIN (a folder of
# skills under .claude-plugin/); Codex installs it as a single flat SKILL (SKILL.md +
# scripts/ + references/). Either way this is used for READING code only — never to
# decide where the user's data goes. See the module docstring.
PLUGIN_MARKERS = (".claude-plugin", "SKILL.md")

# Where a plugin keeps its working files inside a brain: <brain>/.plugins/<plugin>/.
#
# Dot-prefixed on purpose. Second Brain Studio's vault walker skips any entry starting
# with "." (vaultIndexStore.ts listVaultFiles) and so does Obsidian, so the ledger travels
# with the brain — move it, back it up, sync it and the application history comes along —
# without appearing in the tree beside the notes the user actually reads. It is also
# subject-agnostic: unlike the old <brain>/45-jobs/_state it does not depend on resolving
# the jobs layer, which is named differently in a company brain.
PLUGIN_STATE_DIR = ".plugins"
PLUGIN_NAME = "job-search"
# The pre-2026-09 location, still read so an existing install is never handed an empty
# ledger. `render_brain.py --migrate-layout` moves it; until then it simply keeps working.
LEGACY_STATE_DIRNAME = "_state"
HOME_STATE = "~/.second-brain/job-search"

# Layer KEYS are stable; FOLDER NAMES vary by subject. This mirrors the engine's
# `mappings/brain/layout.json` variants for the handful of layers this plugin touches
# — a plugin must never hardcode a folder name, for the same reason the builder must
# not: a company brain names them differently. Resolve with layer(brain, key).
_LAYERS = {
    "person":  {"root": "00-me",  "people": "10-people", "orgs": "15-organizations",
                "career": "40-career",   "jobs": "45-jobs",
                "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes"},
    "company": {"root": "00-org", "people": "10-people", "orgs": "15-organizations",
                "career": "40-pipeline", "jobs": "45-hiring",
                "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes"},
}
LAYER = _LAYERS["person"]["jobs"]      # back-compat default for a personal brain


def subject_of(brain):
    """'company' when the brain is rooted on the org layer, else 'person'."""
    b = pathlib.Path(brain)
    return "company" if (b / _LAYERS["company"]["root"]).is_dir() else "person"


def layer(brain, key):
    """The folder name for `key` in this brain — the plugin-side layout_for()."""
    return _LAYERS[subject_of(brain)][key]


def _expand(p):
    return pathlib.Path(os.path.expanduser(str(p)))


def plugin_root(start=None):
    """The package root: the nearest ancestor holding .claude-plugin/ (Claude Code
    plugin) or SKILL.md (Codex skill).

    Read-only. Used to locate sibling skills' scripts and references, never to decide
    where your data goes. Resolves symlinks first so it works when a skill is reached
    through a symlink rather than through its real path.
    """
    here = pathlib.Path(start or __file__).resolve()
    chain = [here] + list(here.parents)
    # .claude-plugin wins outright: in the Claude packaging every skill folder also
    # holds a SKILL.md, so checking both markers together would stop at the SKILL
    # instead of the plugin that contains it.
    for d in chain:
        if (d / ".claude-plugin").is_dir():
            return d
    for d in chain:
        if (d / "SKILL.md").is_file():
            return d
    return None


def work_root():
    """The folder this run is working in.

    `$CLAUDE_PROJECT_DIR` when the host set it, else the current directory. Deliberately
    NOT derived from the plugin's location - see the module docstring.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return _expand(env)
    return pathlib.Path.cwd()


def is_brain(d):
    """A directory is a Second Brain vault brain if it has an identity note.

    Either subject counts: a personal brain roots on 00-me, a company brain on 00-org.
    """
    b = pathlib.Path(d)
    return any((b / _LAYERS[s]["root"] / "identity.md").is_file() for s in _LAYERS)


def brain_at_cwd(start=None):
    """The brain we are running inside, if any - Second Brain Studio starts Claude Code
    in the brain the user selected, so this is how the surface announces itself."""
    here = pathlib.Path(start or os.getcwd()).resolve()
    for d in [here] + list(here.parents)[:8]:
        if is_brain(d):
            return d
    return None


def surface_root(verbose=False):
    """Where this run's output belongs. Strictly one place per run: inside a brain it is
    that brain, otherwise the working folder. Never both."""
    b = brain_at_cwd()
    if b is not None:
        if verbose:
            print(f"surface: brain at {b}", file=sys.stderr)
        return b
    ws = work_root()
    if verbose:
        print(f"surface: working folder at {ws}", file=sys.stderr)
    return ws


def state_root(verbose=False):
    """The ledger. Order matters: an existing install must never be handed an empty one.

    $JOB_SEARCH_HOME             you said so explicitly
    <brain>/45-jobs/_state       LEGACY, only if it still exists - an un-migrated install
                                 must never be handed an empty ledger
    <brain>/.plugins/job-search  running inside a brain: hidden, travels with the brain
    <work_root>/45-jobs/_state   an existing ledger in the working folder
    ~/.second-brain/job-search   fresh install
    """
    def say(why, p):
        if verbose:
            print(f"state_root via {why}: {p}", file=sys.stderr)
        return p

    env = os.environ.get("JOB_SEARCH_HOME")
    if env:
        return say("$JOB_SEARCH_HOME", _expand(env))

    b = brain_at_cwd()
    if b is not None:
        # Legacy first, and only when it is really there: the whole point is that an
        # install predating the move keeps reading its own history until it is migrated.
        old = b / layer(b, "jobs") / LEGACY_STATE_DIRNAME
        if old.is_dir():
            return say("brain (legacy _state)", old)
        return say("brain", brain_state_root(b))

    local = work_root() / LAYER / LEGACY_STATE_DIRNAME
    if local.is_dir():
        return say("working folder", local)

    return say("home", _expand(HOME_STATE))


def brain_state_root(brain):
    """Where this plugin's files live inside `brain` — the post-migration location."""
    return pathlib.Path(brain) / PLUGIN_STATE_DIR / PLUGIN_NAME


def render_dir(dest=None, verbose=False):
    if dest:
        return _expand(dest)
    s = surface_root(verbose)
    return s / (layer(s, "jobs") if is_brain(s) else LAYER)


def profile_dir(dest=None, verbose=False):
    return render_dir(dest, verbose) / "profile"


def other_profile_dir():
    """The profile on the *other* surface, for the read-order fallback. Returns None when
    there is no other surface to look at."""
    b = brain_at_cwd()
    if b is not None:
        cand = work_root() / LAYER / "profile"
        return cand if cand.is_dir() else None
    for cand in (render_dir() / "profile", _expand(HOME_STATE).parent / LAYER / "profile"):
        if cand.is_dir():
            return cand
    return None


def main():
    print(f"plugin root  : {plugin_root()}   (read-only)")
    print(f"work root    : {work_root()}")
    print(f"state root   : {state_root(verbose=True)}")
    print(f"surface root : {surface_root(verbose=True)}")
    print(f"render dir   : {render_dir()}")
    print(f"profile dir  : {profile_dir()}")
    print(f"other profile: {other_profile_dir()}")


if __name__ == "__main__":
    main()
