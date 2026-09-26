#!/usr/bin/env python3
"""
paths.py - where everything lives. One resolver, imported by every script.

A deliberate copy of job-search's resolver, retargeted. Plugins are distributed
independently and the Codex packaging flattens each one on its own, so there is no shared
runtime to import from - and no collision either.

Two rules matter here.

**Nothing counts directory levels.** `Path(__file__).parents[3] / "data"` silently returns
the wrong folder the moment a script moves one level deeper - and a wrong state root does
not raise, it just hands back an empty ledger and a trip that seems to have vanished.

**Your data never lives next to the plugin.** The plugin directory is used for *reading code
only*. Everything about you is written to a state root chosen from your environment, your
brain, or your home directory - never from where this file happens to sit. A plugin
installed read-only from a source checkout must never receive your itineraries.

    state_root()    the ledger: outcomes.jsonl, quotes/, current.json, the manifest
                    inside a brain that is <brain>/.plugins/travel-planner/ - hidden from
                    the vault tree, but carried with the brain
    surface_root()  the brain when we are running inside one, else the working folder
    render_dir()    <surface_root>/47-travel             (the layer the user reads)
    profile_dir()   <surface_root>/47-travel/profile     (onboarding's; nothing else writes it)
    trip_dir(id)    <surface_root>/47-travel/trips/<id>  (itinerary.json + map.geojson live here)

Run it directly to see every decision:  python3 paths.py
"""
import os, pathlib, re, sys

PLUGIN_MARKERS = (".claude-plugin", "SKILL.md")

# <brain>/.plugins/<plugin>/ - dot-prefixed so Studio's vault walker and Obsidian both skip
# it, while it still travels with the brain.
PLUGIN_STATE_DIR = ".plugins"
PLUGIN_NAME = "travel-planner"
HOME_STATE = "~/.second-brain/travel-planner"
ENV_HOME = "TRAVEL_HOME"

# Layer KEYS are stable; FOLDER NAMES vary by subject. This mirrors the engine's
# `mappings/brain/layout.json` variants for the layers this plugin reads or writes. It is
# the ONLY file in the plugin allowed to spell a layer folder (tests/run.py enforces it).
_LAYERS = {
    "person":  {"root": "00-me",  "people": "10-people", "orgs": "15-organizations",
                "voice": "30-voice", "travel": "47-travel", "mirror": "50-mirror",
                "learning": "60-learning", "places": "85-places",
                "synthesis": "90-synthesis", "notes": "_notes"},
    "company": {"root": "00-org", "people": "10-people", "orgs": "15-organizations",
                "voice": "30-content", "travel": "47-travel", "mirror": "50-market-view",
                "learning": "60-knowledge", "places": "85-locations",
                "synthesis": "90-synthesis", "notes": "_notes"},
}
LAYER = _LAYERS["person"]["travel"]      # default for a working folder that is not a brain

# A trip id is a folder name and appears in URLs and wikilinks: keep it boring.
TRIP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def subject_of(brain):
    """'company' when the brain is rooted on the org layer, else 'person'."""
    b = pathlib.Path(brain)
    return "company" if (b / _LAYERS["company"]["root"]).is_dir() else "person"


def layer(brain, key):
    """The folder name for `key` in this brain - the plugin-side layout_for()."""
    return _LAYERS[subject_of(brain)][key]


def _expand(p):
    return pathlib.Path(os.path.expanduser(str(p)))


def plugin_root(start=None):
    """The package root: nearest ancestor holding .claude-plugin/ (Claude Code plugin) or
    SKILL.md (Codex skill). Read-only - used to find references, never to place data."""
    here = pathlib.Path(start or __file__).resolve()
    chain = [here] + list(here.parents)
    for d in chain:
        if (d / ".claude-plugin").is_dir():
            return d
    for d in chain:
        if (d / "SKILL.md").is_file():
            return d
    return None


def reference(name):
    """Path to a shipped reference file (lexicon, connection-time table, ...).

    Claude packaging: skills/trip-planner/references/<name>. Codex packaging: the flat
    references/<name> beside scripts/. Both are `../references/<name>` from this file."""
    here = pathlib.Path(__file__).resolve().parent
    for cand in (here.parent / "references" / name,
                 here.parent.parent / "references" / name):
        if cand.is_file():
            return cand
    return here.parent / "references" / name


def work_root():
    """`$CLAUDE_PROJECT_DIR` when the host set it, else the current directory. Never
    derived from the plugin's location - see the module docstring."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return _expand(env)
    return pathlib.Path.cwd()


def is_brain(d):
    """A directory is a Second Brain vault brain if it has an identity note."""
    b = pathlib.Path(d)
    return any((b / _LAYERS[s]["root"] / "identity.md").is_file() for s in _LAYERS)


def brain_at_cwd(start=None):
    """The brain we are running inside, if any - Studio starts Claude Code in the brain
    the user selected, so this is how the surface announces itself."""
    here = pathlib.Path(start or os.getcwd()).resolve()
    for d in [here] + list(here.parents)[:8]:
        if is_brain(d):
            return d
    return None


def surface_root(verbose=False):
    """Where this run's output belongs: inside a brain that brain, else the working
    folder. Strictly one place per run."""
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
    """The ledger.

    $TRAVEL_HOME                    you said so explicitly
    <brain>/.plugins/travel-planner running inside a brain: hidden, travels with the brain
    <work_root>/47-travel/_state    an existing ledger in a plain working folder
    ~/.second-brain/travel-planner  fresh install, outside any brain
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
    local = work_root() / LAYER / "_state"
    if local.is_dir():
        return say("working folder", local)
    return say("home", _expand(HOME_STATE))


def brain_state_root(brain):
    return pathlib.Path(brain) / PLUGIN_STATE_DIR / PLUGIN_NAME


def machinery_dir(root=None, dest=None):
    """Where the renderer's own bookkeeping goes (manifest, build report).

    Created if missing - falling back to the layer merely because the ledger did not exist
    yet would put machinery in the folder the user reads on every fresh install. Only an
    unwritable state root falls back to `dest`."""
    d = pathlib.Path(root) if root else state_root()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = pathlib.Path(dest or render_dir())
        d.mkdir(parents=True, exist_ok=True)
    return d


def render_dir(dest=None, verbose=False):
    if dest:
        return _expand(dest)
    s = surface_root(verbose)
    return s / (layer(s, "travel") if is_brain(s) else LAYER)


def profile_dir(dest=None, verbose=False):
    return render_dir(dest, verbose) / "profile"


def trips_dir(dest=None):
    return render_dir(dest) / "trips"


def trip_dir(trip_id, dest=None):
    if not TRIP_ID_RE.match(trip_id or ""):
        raise ValueError(f"bad trip id {trip_id!r}: lowercase letters, digits and hyphens only")
    return trips_dir(dest) / trip_id


def places_dir(brain=None):
    """The brain's places layer, or None outside a brain."""
    b = pathlib.Path(brain) if brain else brain_at_cwd()
    if b is None:
        return None
    return b / layer(b, "places")


def other_profile_dir():
    """The profile on the *other* surface, for the read-order fallback, or None."""
    b = brain_at_cwd()
    if b is not None:
        cand = work_root() / LAYER / "profile"
        return cand if cand.is_dir() and cand.resolve() != profile_dir().resolve() else None
    cand = _expand(HOME_STATE).parent / LAYER / "profile"
    return cand if cand.is_dir() else None


def main():
    print(f"plugin root  : {plugin_root()}   (read-only)")
    print(f"work root    : {work_root()}")
    print(f"state root   : {state_root(verbose=True)}")
    print(f"surface root : {surface_root(verbose=True)}")
    print(f"render dir   : {render_dir()}")
    print(f"profile dir  : {profile_dir()}")
    print(f"places dir   : {places_dir()}")
    print(f"other profile: {other_profile_dir()}")


if __name__ == "__main__":
    main()
