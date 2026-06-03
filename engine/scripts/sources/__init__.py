#!/usr/bin/env python3
"""Source registry — AUTO-DISCOVERS adapters from two kinds of definition:

  1. Python adapters in sources/personal/ (person) and sources/company/ (company)
     — exposing NAME, detect(), extract() (+ optional SUBJECT/QUARANTINE).
  2. Declarative JSON mappings in engine/mappings/sources/*.json (+ any --mappings
     override dir), interpreted by mapping.py into the SAME contract.

Adding a source = drop a Python file in the right subfolder OR (preferred for new
JSON exports) write a mapping JSON — no edit here is needed. **When a JSON mapping
and a Python adapter share a NAME, the mapping wins** (so a mapping can override a
.py adapter without deleting it). Personal modules default SUBJECT="person";
company modules / company mappings set SUBJECT="company".
"""
import importlib
import pkgutil


def _load_py(subpkg, default_subject):
    """Auto-discover Python adapter modules in a subpackage (personal/ or company/).
    Imports every non-underscore module exposing the NAME/detect/extract contract,
    defaulting its SUBJECT (person/company), and returns them sorted by NAME."""
    pkg = importlib.import_module(f"{__name__}.{subpkg}")
    mods = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue  # skip _template.py and other private/helper modules
        m = importlib.import_module(f"{__name__}.{subpkg}.{info.name}")
        if not (hasattr(m, "NAME") and hasattr(m, "detect") and hasattr(m, "extract")):
            continue  # not a valid adapter — ignore
        if not hasattr(m, "SUBJECT"):
            m.SUBJECT = default_subject  # personal→person, company→company
        mods.append(m)
    return sorted(mods, key=lambda m: m.NAME)


# Module-level registry, rebuildable when --mappings override dirs are supplied.
ALL = []
BY_NAME = {}
ALL_QUARANTINE = set()
_PY_ADAPTERS = _load_py("personal", "person") + _load_py("company", "company")


def register_mappings(extra_mapping_dirs=None):
    """(Re)build ALL/BY_NAME/ALL_QUARANTINE from Python adapters + JSON mappings.
    JSON mappings win on NAME clash. Called at import with defaults, and again by
    the builder when --mappings override dirs are given."""
    global ALL, BY_NAME, ALL_QUARANTINE
    try:
        import mapping  # top-level (scripts dir on sys.path)
        maps = mapping.load_mappings(extra_mapping_dirs)
    except Exception:
        maps = {}
    by_name = {m.NAME: m for m in _PY_ADAPTERS}
    by_name.update(maps)                       # mapping wins on clash (overrides same-named .py)
    ALL = sorted(by_name.values(), key=lambda m: m.NAME)
    BY_NAME = by_name
    ALL_QUARANTINE = set()
    for _m in ALL:
        # union of every adapter's sensitive-file set; builder/profiler quarantine these
        ALL_QUARANTINE |= set(getattr(_m, "QUARANTINE", set()))
    return ALL


register_mappings()   # default registry (python adapters + shipped mappings)


def detect_sources(file_index):
    """Return the list of adapter/mapping modules whose signature matches.
    file_index: {normalized_filename: [Path,...]}"""
    return [m for m in ALL if m.detect(file_index)]
