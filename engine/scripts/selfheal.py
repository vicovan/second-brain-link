#!/usr/bin/env python3
"""
selfheal.py — make the skill robust and self-repairing at runtime.

Three capabilities, all deterministic (no LLM in this module):

1. doctor(work, out_dir)        — preflight health check → writes `_DOCTOR.md`.
2. guarded_extract(...)         — run one source adapter so a single broken
                                  adapter can't kill the whole build; on failure it
                                  logs, records a fix-hint, and continues.
3. write_error_report(...)      — on an unrecoverable error, classify it against a
   classify(exc)                  known-fix registry and write `_ERROR.md` with the
                                  traceback, the likely cause, the auto-fixes
                                  already attempted, and a concrete "To fix" hint.

The agent (Claude Code) reads `_ERROR.md` when a run exits non-zero, applies the
smallest fix to the relevant script, mirrors it to the installed copy, and re-runs
(SKILL.md's self-heal protocol). This module makes that loop precise instead of
guesswork.
"""
import sys
import traceback
from pathlib import Path


# --- known-fix registry: (predicate, cause, "to fix" hint) -------------------
# Predicates take (exc, text) where text is a lowercased repr+message.
_REGISTRY = [
    (lambda e, t: isinstance(e, UnicodeDecodeError) or "codec can't decode" in t,
     "A file isn't valid UTF-8 (encoding drift).",
     "`read_csv`/`read_json` in sources/common.py already try utf-8-sig→utf-8→"
     "latin-1; add the offending file's encoding to that list or pass "
     "errors='replace'."),
    (lambda e, t: isinstance(e, KeyError),
     "An expected column/key was missing from an export file (format drift).",
     "Use the adapter's fuzzy `_col(row, ...alias...)` helper instead of indexing "
     "the dict directly; add the real header name as an alias."),
    (lambda e, t: isinstance(e, (IndexError,)) ,
     "A row/array was shorter than expected (ragged file).",
     "Guard the index access; read_csv already pads short rows, so prefer "
     "`row.get(col)` over positional access."),
    (lambda e, t: "json" in t and ("expecting" in t or "decode" in t),
     "A JSON file (or mapping_overrides.json) is malformed.",
     "Validate the JSON; the builder already ignores bad overrides — apply the "
     "same try/except where this raised."),
    (lambda e, t: isinstance(e, FileNotFoundError),
     "A referenced path doesn't exist.",
     "Check the export path / output dir; the source must be a .zip or folder."),
    (lambda e, t: isinstance(e, PermissionError),
     "A file couldn't be read (permissions/locked).",
     "Skip the file defensively and continue; surface it in coverage."),
]


def classify(exc):
    """Return (cause, hint) for an exception using the known-fix registry."""
    text = (repr(exc) + " " + str(exc)).lower()
    for pred, cause, hint in _REGISTRY:
        try:
            if pred(exc, text):
                return cause, hint
        except Exception:
            continue
    return ("Unrecognized error.",
            "Read the traceback below, open the named script at the top frame, and "
            "apply the smallest fix; keep the deterministic-core + privacy "
            "invariants (see CLAUDE.md §2).")


def _offending_frame(exc):
    """Best-effort: the last traceback frame inside our scripts/ tree."""
    tb = exc.__traceback__
    last = None
    while tb is not None:
        fn = tb.tb_frame.f_code.co_filename
        if "second-brain-link" in fn or "/scripts/" in fn:
            last = (fn, tb.tb_lineno, tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    return last


def write_error_report(out_dir, label, exc, attempted=None):
    """Write a structured _ERROR.md the agent can act on. Returns the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cause, hint = classify(exc)
    frame = _offending_frame(exc)
    where = (f"`{Path(frame[0]).name}` line {frame[1]} in `{frame[2]}()`"
             if frame else "unknown (see traceback)")
    lines = [
        "# Second Brain Link — error report",
        "",
        f"Step that failed: **{label}**",
        f"Exception: `{type(exc).__name__}: {exc}`",
        "",
        "## Likely cause",
        cause,
        "",
        "## Where",
        where,
        "",
        "## Auto-fixes already attempted",
    ]
    lines += [f"- {a}" for a in (attempted or [])] or ["- (none — failed on first pass)"]
    lines += [
        "",
        "## To fix",
        hint,
        "",
        "## Self-heal protocol (for your coding agent)",
        "1. Apply the smallest change to the script named under **Where**.",
        "2. Mirror the edit to the installed skill copy (and re-package) — see the "
        "repo CLAUDE.md / AGENTS.md sync rule.",
        "3. Re-run the same command; cap at ~3 passes. Keep all privacy + "
        "deterministic-core invariants.",
        "",
        "## Traceback",
        "```",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip(),
        "```",
    ]
    p = out_dir / "_ERROR.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def guarded_extract(mod, call, col, *, log):
    """Run one adapter's extract() defensively. `call` is a 0-arg thunk that
    invokes the adapter. On success returns its consumed-keys set; on failure
    logs a classified hint and returns an empty set so the build continues with
    the other sources (auto-heal: the run retries minus the broken adapter)."""
    try:
        return call() or set()
    except Exception as e:
        cause, hint = classify(e)
        frame = _offending_frame(e)
        where = f"{Path(frame[0]).name}:{frame[1]}" if frame else "?"
        log(f"[selfheal] adapter '{getattr(mod, 'NAME', '?')}' failed at {where} "
            f"— {type(e).__name__}: {e}. Cause: {cause} Continuing without it.")
        col.note(f"[selfheal] '{getattr(mod,'NAME','?')}' skipped after error; "
                 f"fix hint: {hint}")
        return set()


# --- doctor ------------------------------------------------------------------

def doctor(work, out_dir, *, detect_sources=None, index_files=None):
    """Preflight checks; write `_DOCTOR.md` (PASS/WARN/FAIL). Returns the worst
    status string. detect_sources/index_files are injected to avoid import cycles."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(work)
    checks = []  # (status, label, detail)

    pv = sys.version_info
    checks.append(("PASS" if pv >= (3, 8) else "FAIL",
                   "Python ≥ 3.8", f"running {pv.major}.{pv.minor}.{pv.micro}"))
    checks.append(("PASS" if work.exists() else "FAIL",
                   "Export path exists", str(work)))

    n_files = n_read = n_badenc = 0
    if work.is_dir():
        for p in work.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".csv", ".json", ".ics", ".vcf"):
                n_files += 1
                try:
                    with open(p, "rb") as f:
                        raw = f.read(4096)
                    try:
                        raw.decode("utf-8")
                    except UnicodeDecodeError:
                        n_badenc += 1
                    n_read += 1
                except Exception:
                    pass
        checks.append(("PASS" if n_read == n_files else "WARN",
                       "Data files readable", f"{n_read}/{n_files} readable"))
        checks.append(("PASS" if n_badenc == 0 else "WARN",
                       "UTF-8 clean", f"{n_badenc} non-utf8 (read_csv falls back to latin-1)"))

    if detect_sources and index_files:
        try:
            idx, _ = index_files(work)
            srcs = [m.NAME for m in detect_sources(idx)]
            checks.append(("PASS" if srcs else "WARN",
                           "Source(s) detected", ", ".join(srcs) or "none — will use catch-all"))
            checks.append(("PASS" if idx else "FAIL",
                           "Indexable files found", f"{len(idx)} normalized keys"))
        except Exception as e:
            checks.append(("WARN", "Source detection", f"errored: {e}"))

    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
    worst = max((s for s, _, _ in checks), key=lambda s: rank[s]) if checks else "PASS"
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    lines = ["# Second Brain Link — doctor", "",
             f"Overall: **{icon[worst]} {worst}**", "", "## Checks", ""]
    for s, label, detail in checks:
        lines.append(f"- {icon[s]} **{label}** — {detail}")
    if worst != "PASS":
        lines += ["", "## Notes",
                  "WARN is non-blocking (the build degrades gracefully). FAIL must "
                  "be resolved before building. If a build still errors, the run "
                  "writes `_ERROR.md` with a fix hint."]
    (out_dir / "_DOCTOR.md").write_text("\n".join(lines), encoding="utf-8")
    return worst
