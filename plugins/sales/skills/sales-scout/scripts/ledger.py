#!/usr/bin/env python3
"""
ledger.py - the Sales Agent's records: the account registry and the event log.

Two files in the state root (inside a brain: <brain>/.plugins/sales/, hidden from the tree):

    accounts.jsonl   one account per line - every company any source ever named. A lead the
                     scout found is stage `lead`; approving it makes it a `target`.
    events.jsonl     append-only, one event per line. THE source of truth for what happened:
                     what was sent, blocked, gated, approved, replied, booked, lost. Stages,
                     sequences, caps and KPIs are all computed from it.

Nothing here talks to the network or to a model.

    ledger.py upsert < accounts.json            merge accounts (a list, or one object)
    ledger.py get KEY                            one account, JSON
    ledger.py list [--stage S] [--json]          the registry
    ledger.py set KEY FIELD VALUE                one field (VALUE may be JSON)
    ledger.py contact KEY --name N [--role R] [--role-source URL] [--email E]
                     [--email-source brain|public-page|reply|pattern-unverified]
                     [--profile-url U] [--channels email,linkedin] [--person-note P]
                     [--tie-via NAME] [--tie-strength N] [--tz Europe/Berlin] [--region eu]
    ledger.py stage KEY TO [--by agent|user] [--reason TEXT]
    ledger.py log KIND [--account KEY] [--contact NAME] [--channel C] [--by agent|user]
                     [--data JSON]               any other event
    ledger.py approve --batch ID [--by user]     the owner approved a send batch
    ledger.py deny --batch ID --reason TEXT      ... or denied it, and why
    ledger.py events [--account KEY] [--kind K] [--days N] [--json]
    ledger.py count KIND [--days N]              an integer: sent|replies|meetings|opportunities|won|...
    ledger.py kpi [--json]                       counts by origin / segment / channel / step
    ledger.py suppress VALUE --reason TEXT       add to profile/suppression.md (append-only)
    ledger.py export --contact NAME              everything held on one person (a DSAR answer)
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, profile_dir  # noqa: E402

STAGES = ("lead", "target", "sequenced", "replied", "meeting", "opportunity", "won", "lost", "parked")
ORIGINS = ("revival", "warm", "dormant", "intro", "cold")
EMAIL_SOURCES = ("brain", "public-page", "reply", "pattern-unverified")
# Events that end a sequence for that contact (stop-on-reply and friends).
STOPS = ("replied", "unsubscribed", "bounced", "meeting_booked", "stopped")
OUTCOME_KINDS = {
    "sent": ("sent",), "replies": ("replied",), "meetings": ("meeting_booked",),
    "opportunities": ("stage:opportunity",), "won": ("stage:won",), "lost": ("stage:lost",),
    "blocked": ("send_blocked",), "gated": ("gated",), "sourced": ("sourced",),
}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def root():
    r = state_root()
    r.mkdir(parents=True, exist_ok=True)
    return r


def key_of(name="", domain=""):
    d = (domain or "").lower().strip()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    d = re.sub(r"^www\.", "", d)
    if d and "." in d:
        return d
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def name_key(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


# ------------------------------------------------------------------ accounts

def _acc_file():
    return root() / "accounts.jsonl"


def load_accounts():
    out = {}
    f = _acc_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line) if line.strip() else None
            except ValueError:
                d = None
            if isinstance(d, dict) and d.get("key"):
                out[d["key"]] = d
    return out


def save_accounts(acc):
    f = _acc_file()
    tmp = f.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(v, ensure_ascii=False, sort_keys=True) + "\n"
                           for v in sorted(acc.values(), key=lambda d: d["key"])), encoding="utf-8")
    tmp.replace(f)


def find(acc, ref):
    """By key, by domain, by exact name key, then by a safe containment match."""
    if not ref:
        return None
    if ref in acc:
        return acc[ref]
    k = key_of(ref, ref if "." in ref else "")
    if k in acc:
        return acc[k]
    nk = name_key(ref)
    for v in acc.values():
        if name_key(v.get("name")) == nk:
            return v
    for v in acc.values():
        vk = name_key(v.get("name"))
        if nk and vk and (nk in vk or vk in nk) and min(len(nk), len(vk)) >= 5:
            return v
    return None


def _merge_list(a, b, ident):
    out = list(a or [])
    seen = {ident(x) for x in out}
    for x in b or []:
        i = ident(x)
        if i not in seen:
            out.append(x)
            seen.add(i)
    return out


def merge_contact(old, new):
    """A contact seen twice keeps the better evidence: a brain/public address beats a pattern."""
    rank = {"brain": 3, "reply": 3, "public-page": 2, "pattern-unverified": 0, "": -1, None: -1}
    out = dict(old)
    for k, v in new.items():
        if v in (None, "", []):
            continue
        if k in ("email", "email_source"):
            continue
        if k == "channels":
            out[k] = sorted(set(out.get(k) or []) | set(v))
        else:
            out[k] = v
    if new.get("email") and rank.get(new.get("email_source"), 0) >= rank.get(old.get("email_source"), -1):
        out["email"], out["email_source"] = new["email"], new.get("email_source") or "public-page"
    return out


def upsert(acc, rec, today=None):
    """Merge one account record. Returns (account, is_new)."""
    today = today or datetime.date.today().isoformat()
    name = (rec.get("name") or rec.get("company") or "").strip()
    if not name and not rec.get("domain"):
        return None, False
    cur = find(acc, rec.get("key") or "") or find(acc, rec.get("domain") or "") or find(acc, name)
    is_new = cur is None
    if is_new:
        k = rec.get("key") or key_of(name, rec.get("domain", ""))
        cur = acc[k] = {"key": k, "name": name or k, "stage": "lead", "first_seen": today,
                        "sources": [], "signals": [], "contacts": [], "markets": []}
    for f, v in rec.items():
        if f in ("key", "contacts", "signals", "sources", "markets") or v in (None, "", []):
            continue
        if f == "stage" and cur.get("stage") not in (None, "lead"):
            continue                                    # a merge never moves a worked account
        if f == "origin" and cur.get("origin") in ("revival", "warm", "intro") and v == "cold":
            continue                                    # warm evidence is never downgraded
        cur[f] = v
    cur["sources"] = sorted(set(cur.get("sources") or []) | set(rec.get("sources") or []))
    cur["markets"] = sorted(set(cur.get("markets") or []) | set(rec.get("markets") or []))
    cur["signals"] = _merge_list(cur.get("signals"), rec.get("signals"),
                                 lambda s: (s.get("kind"), (s.get("url") or s.get("what") or "").lower()))
    for c in rec.get("contacts") or []:
        if not c.get("name"):
            continue
        hit = next((x for x in cur.get("contacts", []) if name_key(x.get("name")) == name_key(c["name"])), None)
        if hit:
            cur["contacts"][cur["contacts"].index(hit)] = merge_contact(hit, c)
        else:
            cur.setdefault("contacts", []).append(dict(c))
    cur["last_seen"] = today
    return cur, is_new


# ------------------------------------------------------------------ events

def _ev_file():
    return root() / "events.jsonl"


def log(kind, account="", contact="", channel="", by="agent", **data):
    ev = {"ts": data.pop("ts", None) or now_iso(), "kind": kind}
    for k, v in (("account", account), ("contact", contact), ("channel", channel), ("by", by)):
        if v:
            ev[k] = v
    ev.update({k: v for k, v in data.items() if v not in (None, "")})
    f = _ev_file()
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")
    return ev


def events(account=None, kind=None, days=None, contact=None):
    out = []
    f = _ev_file()
    if not f.exists():
        return out
    cutoff = None
    if days is not None:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line) if line.strip() else None
        except ValueError:
            e = None
        if not isinstance(e, dict):
            continue
        if account and e.get("account") != account:
            continue
        if contact and name_key(e.get("contact")) != name_key(contact):
            continue
        if kind and e.get("kind") != kind:
            continue
        if cutoff and str(e.get("ts", "")) < cutoff:
            continue
        out.append(e)
    return out


def set_stage(acc, a, to, by="agent", reason=""):
    if to not in STAGES:
        raise SystemExit(f"unknown stage {to}; one of {', '.join(STAGES)}")
    if to in ("won", "lost") and by != "user":
        raise SystemExit("won / lost are the owner's call - pass --by user only when they said so")
    frm = a.get("stage", "lead")
    if frm == to:
        return None
    a["stage"] = to
    a["stage_since"] = datetime.date.today().isoformat()
    return log("stage", account=a["key"], by=by, **{"from": frm, "to": to, "reason": reason})


def count(kind, days=None):
    evs = events(days=days)
    wanted = OUTCOME_KINDS.get(kind, (kind,))
    n = 0
    for e in evs:
        for w in wanted:
            if w.startswith("stage:"):
                if e.get("kind") == "stage" and e.get("to") == w[6:]:
                    n += 1
            elif e.get("kind") == w and not e.get("dry_run"):
                n += 1
    return n


def kpi():
    """Counts by origin / segment / channel / step. Rates only where n >= 20 sends."""
    acc = load_accounts()
    evs = events()
    rows = {}

    def bump(dim, val, field):
        r = rows.setdefault(dim, {}).setdefault(val or "-", {"sent": 0, "replied": 0, "meetings": 0})
        r[field] += 1

    for e in evs:
        if e.get("dry_run"):
            continue
        a = acc.get(e.get("account") or "", {})
        field = {"sent": "sent", "replied": "replied", "meeting_booked": "meetings"}.get(e.get("kind"))
        if not field:
            continue
        bump("origin", a.get("origin"), field)
        bump("segment", a.get("segment"), field)
        if e.get("channel"):
            bump("channel", e.get("channel"), field)
        if e.get("step") is not None:
            bump("step", str(e.get("step")), field)
    for dim in rows.values():
        for r in dim.values():
            r["reply_rate"] = round(r["replied"] / r["sent"], 3) if r["sent"] >= 20 else None
            r["meeting_rate"] = round(r["meetings"] / r["sent"], 3) if r["sent"] >= 20 else None
    by_stage = {}
    for a in acc.values():
        by_stage[a.get("stage", "lead")] = by_stage.get(a.get("stage", "lead"), 0) + 1
    return {"stages": by_stage, "dims": rows, "totals": {k: count(k) for k in ("sent", "replies", "meetings", "opportunities", "won")}}


def suppress(value, reason):
    p = pathlib.Path(profile_dir()) / "suppression.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# Do not contact\n\nAppend-only. One line each: `- value — reason — date`.\n\n",
                     encoding="utf-8")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(f"- {value.strip()} — {reason.strip() or 'asked'} — {datetime.date.today().isoformat()}\n")
    log("suppressed", value=value.strip(), reason=reason)


# ------------------------------------------------------------------ CLI

def _out(obj, as_json=True):
    print(json.dumps(obj, indent=2, ensure_ascii=False) if as_json else obj)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("upsert")
    g = sub.add_parser("get"); g.add_argument("key")
    g = sub.add_parser("list"); g.add_argument("--stage"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("set"); g.add_argument("key"); g.add_argument("field"); g.add_argument("value")
    g = sub.add_parser("contact"); g.add_argument("key")
    for f in ("name", "role", "role-source", "email", "email-source", "profile-url", "channels",
              "person-note", "tie-via", "tie-strength", "tz", "region"):
        g.add_argument("--" + f, default="")
    g = sub.add_parser("stage"); g.add_argument("key"); g.add_argument("to")
    g.add_argument("--by", default="agent"); g.add_argument("--reason", default="")
    g = sub.add_parser("log"); g.add_argument("kind")
    for f in ("account", "contact", "channel"):
        g.add_argument("--" + f, default="")
    g.add_argument("--by", default="agent"); g.add_argument("--data", default="{}")
    g = sub.add_parser("approve"); g.add_argument("--batch", required=True); g.add_argument("--by", default="user")
    g = sub.add_parser("deny"); g.add_argument("--batch", required=True); g.add_argument("--reason", required=True)
    g = sub.add_parser("events"); g.add_argument("--account"); g.add_argument("--kind")
    g.add_argument("--days", type=float); g.add_argument("--contact"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("count"); g.add_argument("kind"); g.add_argument("--days", type=float)
    g = sub.add_parser("kpi"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("suppress"); g.add_argument("value"); g.add_argument("--reason", default="")
    g = sub.add_parser("export"); g.add_argument("--contact", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "upsert":
        data = json.load(sys.stdin)
        recs = data if isinstance(data, list) else [data]
        acc = load_accounts()
        new = 0
        for r in recs:
            cur, is_new = upsert(acc, r)
            new += bool(is_new)
        save_accounts(acc)
        print(f"{len(recs)} records -> {new} new accounts; registry holds {len(acc)}", file=sys.stderr)
        return 0
    if a.cmd == "get":
        acc = load_accounts()
        x = find(acc, a.key)
        if not x:
            print(f"no account {a.key!r}", file=sys.stderr)
            return 1
        _out(x)
        return 0
    if a.cmd == "list":
        acc = load_accounts()
        rows = [v for v in acc.values() if not a.stage or v.get("stage") == a.stage]
        rows.sort(key=lambda v: (-(v.get("score") or 0), v["name"].lower()))
        if a.json:
            _out(rows)
        else:
            for v in rows:
                print(f"{v.get('score') or '-':>4}  {v.get('stage','lead'):<11} {v.get('origin') or '-':<8} {v['name']}  [{v['key']}]")
            print(f"{len(rows)} accounts", file=sys.stderr)
        return 0
    if a.cmd == "set":
        acc = load_accounts()
        x = find(acc, a.key)
        if not x:
            print(f"no account {a.key!r}", file=sys.stderr)
            return 1
        if a.field in ("stage",):
            print("use `ledger.py stage` - a stage change is an event", file=sys.stderr)
            return 2
        try:
            val = json.loads(a.value)
        except ValueError:
            val = a.value
        x[a.field] = val
        save_accounts(acc)
        log("set", account=x["key"], field=a.field)
        return 0
    if a.cmd == "contact":
        acc = load_accounts()
        x = find(acc, a.key)
        if not x or not a.name:
            print("need an existing account and --name", file=sys.stderr)
            return 1
        if a.email_source and a.email_source not in EMAIL_SOURCES:
            print(f"--email-source must be one of {EMAIL_SOURCES}", file=sys.stderr)
            return 2
        c = {"name": a.name, "role": a.role, "role_source": a.role_source, "email": a.email,
             "email_source": a.email_source or ("public-page" if a.email else ""),
             "profile_url": a.profile_url, "channels": [s for s in a.channels.split(",") if s],
             "person_note": a.person_note, "tie_via": a.tie_via,
             "tie_strength": int(a.tie_strength) if a.tie_strength.isdigit() else None,
             "tz": a.tz, "region": a.region}
        upsert(acc, {"key": x["key"], "name": x["name"], "contacts": [c]})
        save_accounts(acc)
        return 0
    if a.cmd == "stage":
        acc = load_accounts()
        x = find(acc, a.key)
        if not x:
            print(f"no account {a.key!r}", file=sys.stderr)
            return 1
        ev = set_stage(acc, x, a.to, a.by, a.reason)
        save_accounts(acc)
        print(f"{x['name']}: {ev['from'] if ev else a.to} -> {a.to}")
        return 0
    if a.cmd == "log":
        try:
            data = json.loads(a.data)
        except ValueError:
            print("--data must be JSON", file=sys.stderr)
            return 2
        _out(log(a.kind, a.account, a.contact, a.channel, a.by, **data))
        return 0
    if a.cmd == "approve":
        log("approved", batch=a.batch, by=a.by)
        return 0
    if a.cmd == "deny":
        log("denied", batch=a.batch, by="user", reason=a.reason)
        return 0
    if a.cmd == "events":
        evs = events(a.account, a.kind, a.days, a.contact)
        if a.json:
            _out(evs)
        else:
            for e in evs:
                print(f"{e['ts']}  {e['kind']:<16} {e.get('account',''):<24} {e.get('contact','')}")
        return 0
    if a.cmd == "count":
        print(count(a.kind, a.days))
        return 0
    if a.cmd == "kpi":
        k = kpi()
        if a.json:
            _out(k)
        else:
            t = k["totals"]
            print(f"sent {t['sent']} · replies {t['replies']} · meetings {t['meetings']} · "
                  f"opportunities {t['opportunities']} · won {t['won']}")
            for dim, vals in k["dims"].items():
                print(f"\n{dim}")
                for v, r in sorted(vals.items(), key=lambda x: -x[1]["sent"]):
                    rate = f"{r['reply_rate']:.0%}" if r["reply_rate"] is not None else "n<20"
                    print(f"  {v:<22} sent {r['sent']:>4}  replied {r['replied']:>3}  meetings {r['meetings']:>3}  reply rate {rate}")
        return 0
    if a.cmd == "suppress":
        suppress(a.value, a.reason)
        print(f"suppressed {a.value}")
        return 0
    if a.cmd == "export":
        acc = load_accounts()
        held = []
        for v in acc.values():
            for c in v.get("contacts") or []:
                if name_key(c.get("name")) == name_key(a.contact):
                    held.append({"account": v["name"], **c})
        _out({"contact": a.contact, "records": held, "events": events(contact=a.contact)})
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
