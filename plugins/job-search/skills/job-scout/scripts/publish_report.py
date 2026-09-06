#!/usr/bin/env python3
"""
publish_report.py - mirror the daily job dashboard into the user's Second Brain so they can open and
watch it from Obsidian / Second Brain Studio as well as from the JobAutomation folder.

    python3 publish_report.py                 # mirror today's report
    python3 publish_report.py --date 2026-01-15
    python3 publish_report.py --all           # backfill every report ever written
    python3 publish_report.py --quiet         # for calling after every status change

The canonical report stays `<state root>/reports/YYYY-MM-DD.md`. This only ever COPIES it into
`<brain>/_notes/job-pipeline/`, which `_STRUCTURE.md` documents as "YOUR OWN NOTES - the engine
never writes, overwrites or deletes anything here". Nothing else in the vault is written to, and
the mirror is one-way: edits made to the copy are overwritten on the next call, which the copy
says on its own first line.

No brain reachable is not an error - it exits 0 having done nothing, so the pipeline runs
unchanged on a machine that has no vault.
"""
import argparse, datetime, os, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from find_brain import state_root, from_env, from_cwd, remembered, searched  # noqa: E402

SUBDIR = "_notes/job-pipeline"          # the only place in the vault this script may write
INDEX = "Job Pipeline - Today.md"


def brain():
    for fn in (from_env, from_cwd, remembered, searched):
        p = fn()
        if p:
            return p.resolve()
    return None


def banner(date, src):
    return (
        "---\n"
        "type: note\n"
        "tags: [jobsearch, dashboard, jobautomation]\n"
        f"date: {date}\n"
        "---\n\n"
        f"> [!info] Mirror of the JobAutomation dashboard for **{date}**\n"
        "> The live file is `" + str(src) + "`.\n"
        "> This copy is rewritten every time a job's status changes, so edits made here are lost —\n"
        "> change the report in the JobAutomation folder instead.\n\n"
    )


def write_if_changed(path, text, quiet):
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.write_text(text, encoding="utf-8")
    if not quiet:
        print(f"mirrored -> {path}", file=sys.stderr)
    return True


RELLINK = re.compile(r"\]\((\.\.?/[^)]+)\)")


def absolutise(body, report):
    """The report's CV links are relative to <state root>/reports/, so they break once the file is
    read from the vault. Rewrite them to file:// URLs, which is the form Obsidian opens. The
    canonical report keeps its relative links - the user asked for those explicitly."""
    base = report.parent

    def sub(m):
        target = (base / m.group(1)).resolve()
        return "](" + target.as_uri() + ")" if target.exists() else m.group(0)

    return RELLINK.sub(sub, body)


def mirror(dest_dir, report, quiet):
    date = report.stem
    body = absolutise(report.read_text(encoding="utf-8"), report)
    out = dest_dir / f"{date}.md"
    return write_if_changed(out, banner(date, report) + body, quiet)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--all", action="store_true", help="mirror every report, not just one day")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    reports = state_root() / "reports"
    b = brain()
    if b is None:
        if not a.quiet:
            print("no brain reachable - nothing mirrored (this is not an error)", file=sys.stderr)
        return 0

    dest = b / SUBDIR
    # Refuse to write anywhere but _notes/, whatever the resolver returned.
    if not str(dest.resolve() if dest.exists() else dest).startswith(str(b / "_notes")):
        print("refusing to write outside _notes/", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)

    todo = sorted(reports.glob("*.md")) if a.all else [reports / f"{a.date}.md"]
    todo = [r for r in todo if r.is_file()]
    if not todo:
        if not a.quiet:
            print(f"no report for {a.date} yet - nothing to mirror", file=sys.stderr)
        return 0

    changed = sum(mirror(dest, r, a.quiet) for r in todo)

    # A stable note to open from Obsidian, always pointing at the newest day.
    latest = todo[-1].stem
    index = ("---\ntype: note\ntags: [jobsearch, dashboard, jobautomation]\n---\n\n"
             "# Job pipeline — today\n\n"
             f"Latest dashboard: [[{latest}]]\n\n"
             "All days:\n" + "".join(f"- [[{r.stem}]]\n" for r in reversed(todo)) +
             "\nMirrored from the JobAutomation folder. Read-only — edits here are overwritten.\n")
    write_if_changed(dest / INDEX, index, a.quiet)

    if not a.quiet:
        print(f"{len(todo)} report(s) checked, {changed} updated, in {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
