#!/usr/bin/env python3
"""
_template.py — scaffold for a new source adapter. COPY this to `<name>.py`
(or run `python3 scripts/new_source.py <name>`), then fill in detect() + extract().

A source adapter is the ONE place that knows a specific export's on-disk format.
It reads that format and pushes canonical records into the shared `Collector`
(`sources/common.py`). The builder renders the vault from the collector and has
no source-specific code — so adding a source never touches the builder, privacy,
Obsidian output, or cross-source merge.

CONTRACT
  NAME : str
  detect(file_index) -> bool
  extract(root, file_index, all_paths, col) -> set[str]   # keys consumed

PRIVACY (enforced at the collector, but don't fight it):
  - Never store third-party emails/phones — just don't pass them; add_person
    also drops names that look like emails.
  - Never read message bodies — only col.add_message_signal(NAME, who, date).
  - Add sensitive filenames to QUARANTINE so they're catalogued, never imported.
  - Parse defensively: partial coverage is fine, crashes are not. Anything you
    can't place, leave for the catch-all (don't delete it).
"""
# NOTE: this template is copied into sources/personal/ or sources/company/ (one
# level below `common`), so it imports from the parent package: `..common`.
from ..common import (read_csv, read_json, walk_json_arrays, nk, norm_file,
                      iso_date, fix_mojibake)

NAME = "template"   # <- change to your source name, e.g. "twitter"

# Normalized filenames (lowercase, no spaces/punctuation, shard suffix stripped)
# that are sensitive and must never be imported — only catalogued.
QUARANTINE = set()   # e.g. {"account", "contacts", "directmessages"}

# Files whose presence signals "this export belongs to this source".
SIGNATURE = set()    # e.g. {"tweets", "account", "follower"}


def detect(file_index) -> bool:
    """file_index: {normalized_filename: [Path, ...]}.
    Return True if this export looks like ours."""
    keys = set(file_index)
    return bool(SIGNATURE & keys)


def extract(root, file_index, all_paths, col) -> set:
    """Parse our files and push records into `col`. Return the set of normalized
    keys consumed (so the builder knows what's accounted for).

    root       : Path to the export root
    file_index : {normalized_filename: [Path, ...]}  (CSV/JSON/ICS/… indexed)
    all_paths  : list[Path] of every file (use for formats not in file_index)
    col        : the shared Collector — push via col.add_*(...)
    """
    consumed = set()

    # --- example patterns (delete what you don't use) ---------------------
    #
    # CSV file by normalized key:
    #   for key, paths in file_index.items():
    #       if key == "connections":
    #           for p in paths:
    #               for r in read_csv(p):
    #                   col.add_person(NAME,
    #                       name=fix_mojibake(r.get("Name", "")),
    #                       company=r.get("Company", ""),
    #                       role=r.get("Title", ""),
    #                       date=r.get("Connected On", ""))
    #           consumed.add(key)
    #
    # JSON anywhere (formats drift — search for the shape, don't assume a path):
    #   import json
    #   for p in all_paths:
    #       if p.suffix.lower() != ".json":
    #           continue
    #       data = read_json(p)
    #       for arr in walk_json_arrays(data, want_keys=("name", "username")):
    #           for o in arr:
    #               col.add_person(NAME, name=o.get("name") or o.get("username"))
    #
    # Message SIGNAL only (NEVER the body):
    #   for r in read_csv(some_path):
    #       col.add_message_signal(NAME, r.get("from"), r.get("date"))
    #
    # Identity:
    #   col.set_identity(NAME, name=..., headline=..., location=..., about=...)
    #
    # ----------------------------------------------------------------------

    return consumed
