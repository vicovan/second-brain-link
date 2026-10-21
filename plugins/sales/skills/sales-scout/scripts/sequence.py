#!/usr/bin/env python3
"""
sequence.py - cadences: which step is due, for whom, and why a sequence stopped.

A sequence is a readable note in <sales layer>/sequences/<Name>.md (edit it in Obsidian):

    ---
    type: sales-sequence
    name: Warm — new offer
    applies_to: warm, dormant          # origins it fits (revival, warm, dormant, intro, cold)
    ---
    | n | channel | wait_days | kind | requires | brief |
    |---|---|---|---|---|---|
    | 1 | email | 0 | first | | the reason now, one question |
    | 2 | linkedin_invite | 3 | connect | social | a short note, no pitch |

The text of each step is written per contact at send time, from the voice layer and the
account's evidence - a sequence holds the plan, never a mail-merge template.

State is the ledger: `sequence_started`, `sent` (with `step`), `connected`, and the stop events.
A contact's sequence stops on a reply, a bounce, an unsubscribe, a booked meeting, `stopped`,
or when the account leaves the working stages (replied / meeting / trial / won / lost /
nurture).

    sequence.py seed                     copy the shipped templates into the layer (never overwrites)
    sequence.py list [--json]
    sequence.py start KEY --sequence NAME [--contacts "A,B"]
    sequence.py due [--date YYYY-MM-DD] [--json|--count]  every step due today, one row per contact
    sequence.py timeline KEY [--json]                each contact's steps: sent / due / waiting / ...
    sequence.py stop KEY [--contact NAME] --reason TEXT
"""
import argparse, datetime, json, os, pathlib, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402
from paths import render_dir, plugin_root  # noqa: E402

SOCIAL = ("linkedin_invite", "linkedin_dm", "x_dm", "whatsapp")
WORKING = ("researched", "sequenced", "contacted")


def seq_dir():
    return render_dir() / "sequences"


def template_dirs():
    here = pathlib.Path(__file__).resolve().parent
    root = plugin_root() or here.parent.parent.parent
    return [root / "skills" / "sales-sequence" / "references", here.parent / "references"]


def parse(path):
    txt = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    meta = {}
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        for line in txt[3:end].splitlines():
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if m:
                meta[m.group(1)] = m.group(2).split("#", 1)[0].strip().strip('"')
    steps = []
    for line in txt.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0].isdigit():
            steps.append({"n": int(cells[0]), "channel": cells[1], "wait_days": prof.as_int(cells[2], 0),
                          "kind": cells[3], "requires": cells[4] if len(cells) > 4 else "",
                          "brief": cells[5] if len(cells) > 5 else ""})
    steps.sort(key=lambda s: s["n"])
    return {"name": meta.get("name") or pathlib.Path(path).stem, "file": str(path),
            "applies_to": prof.as_list(meta.get("applies_to")), "steps": steps}


def load_all():
    d = seq_dir()
    return {s["name"]: s for s in (parse(f) for f in sorted(d.glob("*.md")))} if d.is_dir() else {}


def find_seq(name):
    allq = load_all()
    if name in allq:
        return allq[name]
    k = ledger.name_key(name)
    for n, s in allq.items():
        if ledger.name_key(n) == k:
            return s
    return None


def _d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def channel_ok(step, c):
    ch = step["channel"]
    if ch == "email":
        return bool(c.get("email")) and c.get("email_source") in ("brain", "public-page", "reply")
    if ch.startswith("linkedin"):
        return "linkedin.com/in/" in (c.get("profile_url") or "")
    if ch == "x_dm":
        return bool(re.search(r"x\.com/|twitter\.com/", c.get("profile_url") or ""))
    return True


def timeline(a, today=None, evs=None, snd=None):
    """Each contact's steps with a status: sent / due / waiting / upcoming / skipped / stopped."""
    today = today or datetime.date.today()
    evs = evs if evs is not None else ledger.events(account=a["key"])
    snd = snd or prof.sending()
    starts = [e for e in evs if e.get("kind") == "sequence_started"]
    if not starts:
        return {}
    st = starts[-1]
    seq = find_seq(st.get("sequence", ""))
    if not seq:
        return {}
    start = _d(st["ts"]) or today
    names = prof.as_list(st.get("contacts")) or [c["name"] for c in a.get("contacts") or []]
    account_stopped = a.get("stage") not in WORKING
    out = {}
    for name in names:
        c = next((x for x in a.get("contacts") or [] if ledger.name_key(x.get("name")) == ledger.name_key(name)), None)
        if not c:
            continue
        mine = [e for e in evs if ledger.name_key(e.get("contact")) == ledger.name_key(name) and e.get("ts", "") >= st["ts"]]
        stop = next((e for e in mine if e.get("kind") in ledger.STOPS), None)
        sent = {e.get("step"): _d(e["ts"]) for e in mine if e.get("kind") == "sent" and e.get("step") is not None
                and not e.get("dry_run")}
        connected = any(e.get("kind") == "connected" for e in mine)
        rows, anchor, pending = [], start, False
        for s in seq["steps"]:
            r = dict(s)
            if s["n"] in sent:
                r["status"], r["date"] = "sent", sent[s["n"]].isoformat()
                anchor = sent[s["n"]]
            elif stop or account_stopped:
                r["status"] = "stopped"
            elif pending:
                r["status"] = "upcoming"
            elif not channel_ok(s, c):
                r["status"] = "skipped"
                r["why"] = "no reachable " + s["channel"]
            elif "connected" in s["requires"] and not connected:
                r["status"], r["why"] = "waiting", "after the connection is accepted"
                pending = True
            else:
                due = anchor + datetime.timedelta(days=s["wait_days"])
                r["date"] = due.isoformat()
                r["status"] = "due" if due <= today else "upcoming"
                if s["channel"] in SOCIAL and not prof.on(snd.get("social_auto")):
                    r["assisted"] = True
                pending = True
            rows.append(r)
        out[name] = {"steps": rows, "stopped": (stop or {}).get("kind") or ("stage " + a.get("stage", "")
                                                                           if account_stopped else "")}
    return {"sequence": seq["name"], "started": st["ts"][:10], "contacts": out}


def due(today=None):
    today = today or datetime.date.today()
    snd = prof.sending()
    acc = ledger.load_accounts()
    evs = ledger.events()
    rows = []
    for a in acc.values():
        if a.get("stage") not in WORKING:
            continue
        mine = [e for e in evs if e.get("account") == a["key"]]
        t = timeline(a, today, mine, snd)
        for name, tl in (t.get("contacts") or {}).items():
            for s in tl["steps"]:
                if s.get("status") == "due":
                    rows.append({"account": a["key"], "name": a["name"], "contact": name,
                                 "sequence": t["sequence"], "step": s["n"], "channel": s["channel"],
                                 "kind": s["kind"], "brief": s["brief"], "due": s["date"],
                                 "assisted": bool(s.get("assisted"))})
    rows.sort(key=lambda r: (r["due"], r["name"].lower(), r["step"]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    g = sub.add_parser("list"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("start"); g.add_argument("key"); g.add_argument("--sequence", required=True)
    g.add_argument("--contacts", default="")
    g = sub.add_parser("due"); g.add_argument("--date"); g.add_argument("--json", action="store_true")
    g.add_argument("--count", action="store_true", help="print only the number (for routine conditions)")
    g = sub.add_parser("timeline"); g.add_argument("key"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("stop"); g.add_argument("key"); g.add_argument("--contact", default="")
    g.add_argument("--reason", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "seed":
        d = seq_dir()
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for td in template_dirs():
            for f in sorted(td.glob("sequence-*.md")) if td.is_dir() else []:
                name = parse(f)["name"]
                dest = d / (re.sub(r'[\\/:*?"<>|]', "", name) + ".md")
                if not dest.exists():
                    shutil.copyfile(f, dest)
                    n += 1
        print(f"seeded {n} sequences into {d}")
        return 0
    if a.cmd == "list":
        allq = load_all()
        if a.json:
            print(json.dumps(list(allq.values()), indent=2, ensure_ascii=False))
        else:
            for s in allq.values():
                print(f"{s['name']}  ({len(s['steps'])} steps · fits {', '.join(s['applies_to']) or 'any'})")
        return 0
    if a.cmd == "start":
        seq = find_seq(a.sequence)
        if not seq:
            print(f"no sequence {a.sequence!r} - `sequence.py list`", file=sys.stderr)
            return 1
        acc = ledger.load_accounts()
        x = ledger.find(acc, a.key)
        if not x:
            print(f"no account {a.key!r}", file=sys.stderr)
            return 1
        ledger.log("sequence_started", account=x["key"], sequence=seq["name"], contacts=a.contacts)
        x["sequence"] = seq["name"]
        if x.get("stage") in ("lead", "researched"):
            ledger.set_stage(acc, x, "sequenced", "agent", f"sequence {seq['name']}")
        ledger.save_accounts(acc)
        print(f"{x['name']}: started {seq['name']}")
        return 0
    if a.cmd == "due":
        rows = due(_d(a.date) if a.date else None)
        if a.count:
            print(len(rows))
            return 0
        if a.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['due']}  {r['name']:<24} {r['contact']:<22} step {r['step']} {r['channel']}"
                      + (" (assisted)" if r["assisted"] else ""))
            print(f"{len(rows)} steps due", file=sys.stderr)
        return 0
    if a.cmd == "timeline":
        acc = ledger.load_accounts()
        x = ledger.find(acc, a.key)
        if not x:
            print(f"no account {a.key!r}", file=sys.stderr)
            return 1
        print(json.dumps(timeline(x), indent=2, ensure_ascii=False))
        return 0
    acc = ledger.load_accounts()
    x = ledger.find(acc, a.key)
    if not x:
        print(f"no account {a.key!r}", file=sys.stderr)
        return 1
    names = [a.contact] if a.contact else [c["name"] for c in x.get("contacts") or []]
    for n in names:
        ledger.log("stopped", account=x["key"], contact=n, reason=a.reason, by="user")
    print(f"stopped {len(names)} contact(s) at {x['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
