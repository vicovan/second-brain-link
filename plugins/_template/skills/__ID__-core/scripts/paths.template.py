#!/usr/bin/env python3
"""paths.py - where everything lives. One resolver, imported by every script (the job-search rule).

Your data never lives next to the plugin: the state root comes from the environment
($__ENV___HOME), the brain (<brain>/.plugins/__ID__/) or the home directory - never from
where this file sits. The plugin directory is for READING code only.
"""
import json, os, pathlib

PLUGIN_NAME = "__ID__"
ENV_HOME = "__ENV___HOME"
HOME_STATE = "~/.second-brain/__ID__"
PLUGIN_STATE_DIR = ".plugins"


def _expand(p):
    return pathlib.Path(os.path.expanduser(str(p)))


def plugin_root(start=None):
    here = pathlib.Path(start or __file__).resolve()
    for d in [here] + list(here.parents):
        if (d / "studio.json").is_file():
            return d
    return None


def contract():
    r = plugin_root()
    try:
        return json.loads((r / "studio.json").read_text(encoding="utf-8")) if r else {}
    except (OSError, ValueError):
        return {}


LAYER = contract().get("layer") or "__LAYER__"

# Layer KEYS are stable; FOLDER NAMES vary by subject (the engine's mappings/brain/layout.json
# variants). A plugin never hardcodes another layer's folder — resolve with layer(brain, key).
_LAYERS = {
    "person":  {"root": "00-me",  "people": "10-people", "orgs": "15-organizations", "career": "40-career",
                "places": "85-places", "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes",
                "agentwork": "96-agents", "own": LAYER},
    "company": {"root": "00-org", "people": "10-people", "orgs": "15-organizations", "career": "40-pipeline",
                "places": "85-locations", "synthesis": "90-synthesis", "goals": "95-goals", "notes": "_notes",
                "agentwork": "96-agents", "own": LAYER},
}


def subject_of(brain):
    return "company" if (pathlib.Path(brain) / _LAYERS["company"]["root"]).is_dir() else "person"


def layer(brain, key):
    """The folder name for `key` in this brain — the plugin-side layout_for()."""
    return _LAYERS[subject_of(brain)][key]


def work_root():
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return _expand(env) if env else pathlib.Path.cwd()


def is_brain(d):
    d = pathlib.Path(d)
    return (d / "00-me" / "identity.md").is_file() or (d / "00-org").is_dir()


def brain_at_cwd(start=None):
    d = pathlib.Path(start or os.environ.get("SBL_BRAIN") or work_root()).resolve()
    for cand in [d] + list(d.parents):
        if is_brain(cand):
            return cand
    return None


def surface_root():
    return brain_at_cwd() or work_root()


def state_root():
    env = os.environ.get(ENV_HOME)
    if env:
        p = _expand(env)
    else:
        b = brain_at_cwd()
        p = (b / PLUGIN_STATE_DIR / PLUGIN_NAME) if b else _expand(HOME_STATE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_dir(dest=None):
    return _expand(dest) if dest else surface_root() / LAYER


def profile_dir(dest=None):
    return render_dir(dest) / "profile"


if __name__ == "__main__":
    print(f"plugin root : {plugin_root()}   (read-only)")
    print(f"state root  : {state_root()}")
    print(f"render dir  : {render_dir()}")
    print(f"brain       : {brain_at_cwd() or '(none - working folder mode)'}")
