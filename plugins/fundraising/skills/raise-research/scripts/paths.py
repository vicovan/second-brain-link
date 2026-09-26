#!/usr/bin/env python3
"""
paths.py - where everything lives. One resolver, imported by every script.

Ported from job-search's resolver, and it keeps both of its rules:

**Nothing counts directory levels.** A wrong state root does not raise; it hands back
an empty ledger, and an empty ledger re-drafts emails that were already sent.

**Your data never lives next to the plugin.** The plugin directory is for *reading
code only*. The founder's records, drafts and applications are written to a state
root chosen from the environment, the brain, or the home directory.

    state_root()    the ledger: targets.jsonl, events.jsonl, lessons.md, the manifest
                    inside a brain that is <brain>/.plugins/fundraising/ - hidden from
                    the vault tree, but carried with the brain
    surface_root()  the brain when we are running inside one, else the working folder
    render_dir()    <surface_root>/<fundraising layer>
    profile_dir()   <render_dir>/profile

Run it directly to see every decision:  python3 paths.py
"""
import os, pathlib, sys

PLUGIN_MARKERS = (".claude-plugin", "SKILL.md")
PLUGIN_STATE_DIR = ".plugins"
PLUGIN_NAME = "fundraising"
HOME_STATE = "~/.second-brain/fundraising"
ENV_HOME = "FUNDRAISE_HOME"

# Layer KEYS are stable; FOLDER NAMES vary by subject. This mirrors the engine's
# `mappings/brain/layout.json` variants for the layers this plugin touches. A plugin
# must never hardcode a folder name anywhere else — resolve with layer(brain, key).
_LAYERS = {
    "person":  {"root": "00-me",  "people": "10-people", "orgs": "15-organizations",
                "career": "40-career", "fundraising": "46-fundraising",
                "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes"},
    "company": {"root": "00-org", "people": "10-people", "orgs": "15-organizations",
                "career": "40-pipeline", "fundraising": "46-fundraising",
                "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes"},
}
LAYER = _LAYERS["person"]["fundraising"]


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
    """The package root (read-only): nearest ancestor with .claude-plugin/, else SKILL.md."""
    here = pathlib.Path(start or __file__).resolve()
    chain = [here] + list(here.parents)
    for d in chain:
        if (d / ".claude-plugin").is_dir():
            return d
    for d in chain:
        if (d / "SKILL.md").is_file():
            return d
    return None


def work_root():
    """$CLAUDE_PROJECT_DIR when the host set it, else the current directory."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return _expand(env) if env else pathlib.Path.cwd()


def is_brain(d):
    """A directory is a brain if it has an identity note under either subject's root."""
    b = pathlib.Path(d)
    return any((b / _LAYERS[s]["root"] / "identity.md").is_file() for s in _LAYERS)


def brain_at_cwd(start=None):
    """The brain we are running inside, if any. Studio starts Claude Code in the brain
    the user selected, so this is how the surface announces itself."""
    here = pathlib.Path(start or os.getcwd()).resolve()
    for d in [here] + list(here.parents)[:8]:
        if is_brain(d):
            return d
    return None


def surface_root(verbose=False):
    """Strictly one place per run: inside a brain, that brain; otherwise the working folder."""
    b = brain_at_cwd()
    if b is not None:
        if verbose:
            print(f"surface: brain at {b}", file=sys.stderr)
        return b
    ws = work_root()
    if verbose:
        print(f"surface: working folder at {ws}", file=sys.stderr)
    return ws


def brain_state_root(brain):
    return pathlib.Path(brain) / PLUGIN_STATE_DIR / PLUGIN_NAME


def state_root(verbose=False):
    """The ledger.

    $FUNDRAISE_HOME               you said so explicitly
    <brain>/.plugins/fundraising  running inside a brain: hidden, travels with the brain
    <work_root>/.plugins/fundraising   an existing ledger in the working folder
    ~/.second-brain/fundraising   fresh install outside any brain
    """
    def say(why, p):
        if verbose:
            print(f"state_root via {why}: {p}", file=sys.stderr)
        return p

    env = os.environ.get(ENV_HOME)
    if env:
        return say("$" + ENV_HOME, _expand(env))
    b = brain_at_cwd()
    if b is not None:
        return say("brain", brain_state_root(b))
    local = brain_state_root(work_root())
    if local.is_dir():
        return say("working folder", local)
    return say("home", _expand(HOME_STATE))


def render_dir(dest=None, verbose=False):
    if dest:
        return _expand(dest)
    s = surface_root(verbose)
    return s / (layer(s, "fundraising") if is_brain(s) else LAYER)


def profile_dir(dest=None, verbose=False):
    return render_dir(dest, verbose) / "profile"


def brain_layer(key, brain=None):
    """Absolute path of another layer of the active brain (read-only use), or None."""
    b = pathlib.Path(brain) if brain else brain_at_cwd()
    if b is None:
        return None
    return b / layer(b, key)


def main():
    print(f"plugin root  : {plugin_root()}   (read-only)")
    print(f"work root    : {work_root()}")
    print(f"state root   : {state_root(verbose=True)}")
    print(f"surface root : {surface_root(verbose=True)}")
    print(f"render dir   : {render_dir()}")
    print(f"profile dir  : {profile_dir()}")
    b = brain_at_cwd()
    print(f"brain        : {b if b else '(none — working folder mode)'}")


if __name__ == "__main__":
    main()
