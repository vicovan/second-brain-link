#!/usr/bin/env python3
"""ledger.py - the __LABEL__'s records: one line per item in <state root>/items.jsonl, one
event per status move in events.jsonl. The one writer (R7); every note and number is rendered
from here (R2). Built on the shared ledger_base.py.

    ledger.py upsert --json '{"key":"acme","title":"Acme","kind":"__ITEM__", ...}'
    ledger.py stage KEY TO [--by agent|user] [--reason TEXT]
    ledger.py list [--stage S] [--funnel F] [--json]
    ledger.py count STAGE|actions|<funnel success> [--days N]
    ledger.py table shortlist|ledger [--funnel F]
    ledger.py next KEY --action A --due YYYY-MM-DD
    ledger.py due
    ledger.py events [--key K] [--days N]
    ledger.py migrate            (idempotent status-id migration, backup kept)
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, contract  # noqa: E402
from ledger_base import Ledger  # noqa: E402

C = contract()
FUNNELS = {f["id"]: f for f in C.get("funnels") or []}
# the transitions table: each open stage may move to the next open stage, any positive, negative
# or parked stage of its funnel; closed stages may return to the first open stage (with a reason)
TRANSITIONS = {}
for f in FUNNELS.values():
    chain = [s["id"] for s in f["stages"] if s.get("role") == "open"]
    closed = [s["id"] for s in f["stages"] if s.get("role") != "open"]
    for i, sid in enumerate(chain):
        TRANSITIONS.setdefault(sid, set()).update(chain[i + 1:i + 2] + closed)
    for sid in closed:
        TRANSITIONS.setdefault(sid, set()).update(chain[:1])
MIGRATIONS = {}   # old status id -> new (filled when a stage id changes; keep forever, idempotent)
L = Ledger(state_root(), "items.jsonl", transitions=TRANSITIONS)


def funnel_of(rec):
    k = rec.get("kind") or ""
    for f in FUNNELS.values():
        if f.get("item") == k:
            return f["id"]
    return next(iter(FUNNELS), "")


def cmd_upsert(a):
    data = json.loads(a.json)
    recs = L.load()
    by = L.by_key(recs)
    key = data.get("key") or data.get("title", "").lower().replace(" ", "-")
    rec = by.get(key)
    now = datetime.datetime.now().replace(microsecond=0).isoformat()
    if rec is None:
        f = FUNNELS.get(funnel_of(data)) or next(iter(FUNNELS.values()))
        first = next(s["id"] for s in f["stages"] if s.get("role") == "open")
        rec = {"key": key, "status": first, "created": now, "funnel": f["id"], "attrs": {}}
        recs.append(rec)
        L.event(key, None, first, "agent", "found", kind="found")
    for k, v in data.items():
        if k not in ("key", "status"):
            rec[k] = v
    rec["updated"] = now
    rec["day"] = now[:10]
    L.save(recs)
    print(json.dumps(rec, ensure_ascii=False))


def cmd_stage(a):
    recs = L.load()
    rec = L.by_key(recs).get(a.key)
    if not rec:
        sys.exit(f"no item {a.key}")
    try:
        L.transition(rec, a.to, a.by, reason=a.reason or "")
    except ValueError as e:
        sys.exit(str(e))
    L.save(recs)
    print(json.dumps({"key": a.key, "status": a.to}))


def cmd_list(a):
    recs = [r for r in L.load() if (not a.stage or r.get("status") == a.stage) and (not a.funnel or r.get("funnel") == a.funnel)]
    if a.json:
        print(json.dumps(recs, ensure_ascii=False))
    else:
        for r in recs:
            print(f"{r['key']:30} {r.get('status', ''):14} {r.get('title', '')}")


def cmd_count(a):
    if a.what == "actions":
        print(L.count("events:acted|found", days=a.days))
        return
    sts = {a.what}
    for f in FUNNELS.values():
        if f.get("success") == a.what or f["id"] == a.what:
            sts |= {s["id"] for s in f["stages"] if s.get("role") == "positive"} | {f["success"]}
    print(L.count(sorted(sts), days=a.days))


def cmd_table(a):
    recs = [r for r in L.load() if not a.funnel or r.get("funnel") == a.funnel]
    if a.which == "shortlist":
        today = datetime.date.today().isoformat()
        recs = sorted([r for r in recs if r.get("day") == today], key=lambda r: -(r.get("score") or 0))
        print(L.table(["title", "score", "status", "why"], recs, labels=["Item", "Score", "Stage", "Why"]), end="")
    else:
        print(L.table(["title", "status", "updated"], sorted(recs, key=lambda r: r.get("title", "")), labels=["Item", "Stage", "Updated"]), end="")


def cmd_next(a):
    recs = L.load()
    rec = L.by_key(recs).get(a.key)
    if not rec:
        sys.exit(f"no item {a.key}")
    rec["next"] = {"action": a.action, "due": a.due}
    L.save(recs)
    print(json.dumps(rec["next"]))


def cmd_due(a):
    for r in L.due():
        print(f"{r['key']:30} {r['next'].get('due')}  {r['next'].get('action')}")


def cmd_events(a):
    for e in L.events(key=a.key, days=a.days):
        print(json.dumps(e, ensure_ascii=False))


def cmd_log(a):
    L.event(a.key or "", None, None, a.by, a.note or "", kind=a.kind)
    print("ok")


def main():
    ap = argparse.ArgumentParser(description="the __LABEL__'s ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("upsert"); g.add_argument("--json", required=True); g.set_defaults(f=cmd_upsert)
    g = sub.add_parser("stage"); g.add_argument("key"); g.add_argument("to"); g.add_argument("--by", default="agent"); g.add_argument("--reason", default=""); g.set_defaults(f=cmd_stage)
    g = sub.add_parser("list"); g.add_argument("--stage"); g.add_argument("--funnel"); g.add_argument("--json", action="store_true"); g.set_defaults(f=cmd_list)
    g = sub.add_parser("count"); g.add_argument("what"); g.add_argument("--days", type=int); g.set_defaults(f=cmd_count)
    g = sub.add_parser("table"); g.add_argument("which", choices=["shortlist", "ledger"]); g.add_argument("--funnel"); g.set_defaults(f=cmd_table)
    g = sub.add_parser("next"); g.add_argument("key"); g.add_argument("--action", required=True); g.add_argument("--due", required=True); g.set_defaults(f=cmd_next)
    g = sub.add_parser("due"); g.set_defaults(f=cmd_due)
    g = sub.add_parser("events"); g.add_argument("--key"); g.add_argument("--days", type=int); g.set_defaults(f=cmd_events)
    g = sub.add_parser("log"); g.add_argument("kind"); g.add_argument("--key", default=""); g.add_argument("--by", default="agent"); g.add_argument("--note", default=""); g.set_defaults(f=cmd_log)
    g = sub.add_parser("migrate"); g.set_defaults(f=lambda a: print(json.dumps(L.migrate(MIGRATIONS))))
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
