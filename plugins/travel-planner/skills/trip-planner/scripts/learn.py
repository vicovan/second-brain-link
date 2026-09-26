#!/usr/bin/env python3
"""
learn.py - what happened, so the next trip is planned better. The ledger has one writer.

    outcomes.jsonl   one row per (trip_id, kind, ref), UPSERTED: a later write for the same
                     key replaces the earlier one rather than appending a duplicate
    lessons.md       short, durable lessons ("hated early flights", "stopover nights were the
                     best part") that every skill reads at the start of a run

Only the orchestrator (the main agent) calls this. A parallel subagent never does: two
simultaneous appends to a JSONL file produce a line nothing can parse, and an unparseable
line is a booking that silently disappears. The file lock below is a second line of
defence, not permission.

    learn.py log --trip <id> --kind planned|shopped|held|booked|cancelled|travelled \
                 [--ref <booking or stop id>] [--note "..."]
    learn.py rate --trip <id> --stars 1-5 [--ref <poi/stop id>] [--note "what worked"]
    learn.py add-lesson "text" [--tag pace]
    learn.py show [--trip <id>]
    learn.py kpi
"""
import argparse, contextlib, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root  # noqa: E402

KINDS = ("planned", "shopped", "held", "booked", "cancelled", "travelled", "rated")
ROOT = state_root()
OUTCOMES = ROOT / "outcomes.jsonl"
LESSONS = ROOT / "lessons.md"


@contextlib.contextmanager
def _locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    with open(lock, "a+") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass                          # no fcntl (Windows): single-writer rule still holds
        try:
            yield
        finally:
            try:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def rows():
    out = []
    try:
        with open(OUTCOMES, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    print(f"warning: unreadable ledger line skipped: {line[:80]}", file=sys.stderr)
    except OSError:
        pass
    return out


def upsert(row):
    key = (row["trip_id"], row["kind"], row.get("ref", ""))
    with _locked(OUTCOMES):
        cur = [r for r in rows() if (r.get("trip_id"), r.get("kind"), r.get("ref", "")) != key]
        cur.append(row)
        tmp = OUTCOMES.with_name(OUTCOMES.name + ".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cur), encoding="utf-8")
        os.replace(tmp, OUTCOMES)
    return row


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def main():
    ap = argparse.ArgumentParser(description="the travel ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("log"); s.add_argument("--trip", required=True)
    s.add_argument("--kind", required=True, choices=KINDS); s.add_argument("--ref", default="")
    s.add_argument("--note", default="")
    s = sub.add_parser("rate"); s.add_argument("--trip", required=True)
    s.add_argument("--stars", type=int, required=True, choices=range(1, 6))
    s.add_argument("--ref", default=""); s.add_argument("--note", default="")
    s = sub.add_parser("add-lesson"); s.add_argument("text"); s.add_argument("--tag", default="")
    s = sub.add_parser("show"); s.add_argument("--trip")
    sub.add_parser("kpi")
    a = ap.parse_args()
    if a.cmd == "log":
        print(json.dumps(upsert({"trip_id": a.trip, "kind": a.kind, "ref": a.ref,
                                 "note": a.note, "at": now()}), ensure_ascii=False))
    elif a.cmd == "rate":
        print(json.dumps(upsert({"trip_id": a.trip, "kind": "rated", "ref": a.ref,
                                 "stars": a.stars, "note": a.note, "at": now()}), ensure_ascii=False))
    elif a.cmd == "add-lesson":
        with _locked(LESSONS):
            existing = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else "# Travel lessons\n\n"
            line = f"- {a.text}" + (f" `#{a.tag}`" if a.tag else "") + f" _({now()[:10]})_\n"
            if a.text not in existing:
                LESSONS.write_text(existing + line, encoding="utf-8")
        print(LESSONS)
    elif a.cmd == "show":
        for r in rows():
            if not a.trip or r.get("trip_id") == a.trip:
                print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == "kpi":
        rs = rows()
        trips = sorted({r["trip_id"] for r in rs})
        stars = [r["stars"] for r in rs if r.get("kind") == "rated" and not r.get("ref")]
        print(f"trips: {len(trips)}")
        for k in KINDS[:-1]:
            n = len({r['trip_id'] for r in rs if r.get('kind') == k})
            if n:
                print(f"  {k}: {n}")
        if stars:
            print(f"trip rating: ★{sum(stars) / len(stars):.1f} over {len(stars)} trip(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
