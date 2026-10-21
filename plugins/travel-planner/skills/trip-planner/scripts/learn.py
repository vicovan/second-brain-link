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
    learn.py went|loved|not-for-me|save --pick <id> [--note "…"]     the picks funnel (today.py)
    learn.py count went|loved|saved|picks|planned|booked [--days N]   one number for a goal / the throughput
    learn.py picks [--date D] [--json]                                the day's picks with their status
"""
import argparse, contextlib, datetime, json, os, sys
import pathlib as _pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root  # noqa: E402

KINDS = ("planned", "shopped", "held", "booked", "cancelled", "travelled", "rated")
ROOT = state_root()
SCOPE = "travel-planner"
ROOT_FOR_MEMORY = lambda: ROOT  # noqa: E731


# ------------------------------------------------------------------ the shared memory layer
def _brain_of(root):
    """The brain a state root lives in (<brain>/.plugins/<plugin>/), else None."""
    try:
        p = _pl.Path(root).resolve()
        return str(p.parent.parent) if p.parent.name == ".plugins" else None
    except (OSError, TypeError):
        return None


def _memory(kind, source, text, tags=(), evidence=None):
    """Feed memory.py (beside this script) — see docs-memory/SBL-MEMORY-ARCHITECTURE.md.
    Never fails the command it rides on: the ledger is the record; memory is what was learned."""
    try:
        here = str(_pl.Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import memory as _mem  # noqa: PLC0415
        r = _mem.observe(SCOPE, kind, source, text, [t for t in tags if t], evidence, brain=_brain_of(ROOT_FOR_MEMORY()))
        print(f"memory: {r['action']} {r['id']} — " + ("used from now on" if r["status"] == "active" else "waiting for review"))
    except Exception as e:  # noqa: BLE001
        print(f"memory: not recorded ({e})", file=sys.stderr)

OUTCOMES = ROOT / "outcomes.jsonl"
LESSONS = ROOT / "lessons.md"


# ------------------------------------------------------------------ the picks funnel (today.py's ledger)
def _picks_ledger():
    import today as T  # noqa: PLC0415
    return T.ledger()


def pick_move(pick_id, to, note="", by="user"):
    """suggested → saved → went → loved / not_for_me; expired → saved (one writer, the shared lock)."""
    L = _picks_ledger()
    rows = L.load()
    rec = next((r for r in rows if r.get("id") == pick_id), None)
    if not rec:
        raise SystemExit(f"no pick {pick_id}")
    if rec.get("status") == "suggested" and to == "loved":
        L.transition(rec, "went", by, note)
    try:
        L.transition(rec, to, by, note)          # appends the event under the lock
    except ValueError as e:
        raise SystemExit(str(e))
    L.save(rows)                                 # the one writer, under the same lock (released between)
    if to in ("went", "loved", "not_for_me"):
        what = rec.get("name") or pick_id
        _memory("lesson", "outcome", {"went": f"Went to {what} ({rec.get('kind')}, {rec.get('city')})",
                                       "loved": f"Loved {what} ({rec.get('kind')}, {rec.get('city')}) — more like this.",
                                       "not_for_me": f"{what} ({rec.get('kind')}, {rec.get('city')}) was not for me — avoid places like this."}[to]
                + (f": \"{note.strip()[:200]}\"" if note else ""), ["taste", rec.get("slot") or ""], evidence=f"learn.py {to}|{pick_id}")
    try:
        import today as T  # noqa: PLC0415
        T.snapshot(rec.get("date"))
    except Exception:  # noqa: BLE001
        pass
    return rec


def count(what, days=None):
    """One number: picks (went / loved / saved / all) or trips (planned / booked) - outcomes, not activity."""
    if what in ("planned", "booked"):
        import itinerary as itin  # noqa: PLC0415
        want = {"planned": ("planned", "shopped", "booked", "done"), "booked": ("booked", "done")}[what]
        n = 0
        for t in itin.list_trips():
            try:
                if itin.load(t).get("status") in want:
                    n += 1
            except (itin.ItineraryError, ValueError):
                continue
        return n
    rows = _picks_ledger().load()
    if days is not None:
        cut = (datetime.date.today() - datetime.timedelta(days=max(0, int(days) - 1))).isoformat()
        rows = [r for r in rows if str(r.get("updated") or r.get("date") or "")[:10] >= cut]
    sts = {"went": ("went", "loved"), "loved": ("loved",), "saved": ("saved",), "picks": tuple(_picks_ledger().transitions),
           "not_for_me": ("not_for_me",)}[what]
    return sum(1 for r in rows if r.get("status") in sts)


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
    for name in ("went", "loved", "not-for-me", "save"):
        s = sub.add_parser(name); s.add_argument("--pick", required=True); s.add_argument("--note", default="")
    s = sub.add_parser("count"); s.add_argument("what", choices=["went", "loved", "saved", "picks", "not_for_me", "planned", "booked"])
    s.add_argument("--days", type=int)
    s = sub.add_parser("picks"); s.add_argument("--date"); s.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd in ("went", "loved", "not-for-me", "save"):
        to = {"went": "went", "loved": "loved", "not-for-me": "not_for_me", "save": "saved"}[a.cmd]
        rec = pick_move(a.pick, to, a.note)
        print(json.dumps({"id": rec["id"], "name": rec.get("name"), "status": rec["status"]}, ensure_ascii=False))
        return 0
    if a.cmd == "count":
        print(count(a.what, a.days))
        return 0
    if a.cmd == "picks":
        import today as T  # noqa: PLC0415
        rows = T.picks_for(a.date)
        print(json.dumps(rows, ensure_ascii=False) if a.json else T.table(a.date), end="" if not a.json else "\n")
        return 0
    if a.cmd == "log":
        print(json.dumps(upsert({"trip_id": a.trip, "kind": a.kind, "ref": a.ref,
                                 "note": a.note, "at": now()}), ensure_ascii=False))
    elif a.cmd == "rate":
        print(json.dumps(upsert({"trip_id": a.trip, "kind": "rated", "ref": a.ref,
                                 "stars": a.stars, "note": a.note, "at": now()}), ensure_ascii=False))
        # A clear rating is a fact about taste the next plan starts from (the stars used to go nowhere).
        if a.stars <= 2 or a.stars >= 4:
            what = a.ref or a.trip
            _memory("lesson", "outcome", f"Rated {what} {a.stars}/5 on trip {a.trip}" + (f": \"{a.note.strip()[:300]}\"" if a.note else "")
                    + (" — more like this." if a.stars >= 4 else " — avoid places like this."), ["taste", "stays", "food"],
                    evidence=f"learn.py rate|{a.stars} stars {what}")
    elif a.cmd == "add-lesson":
        with _locked(LESSONS):
            existing = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else "# Travel lessons\n\n"
            line = f"- {a.text}" + (f" `#{a.tag}`" if a.tag else "") + f" _({now()[:10]})_\n"
            if a.text not in existing:
                LESSONS.write_text(existing + line, encoding="utf-8")
        print(LESSONS)
        _memory("lesson", "agent", a.text, [a.tag], evidence="learn.py add-lesson|" + a.text)
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
