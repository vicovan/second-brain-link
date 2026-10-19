#!/usr/bin/env python3
"""
lead_score.py - knock-outs, reachability and the score. Deterministic, no network, no model.

    lead_score.py score [--all]          score every lead (stage `lead`; --all: every account)
    lead_score.py shortlist [--n N] [--include-seen] [--json]
                                         the day's shortlist: leads above the floor, best first,
                                         up to the daily target - never padded below the floor
    lead_score.py why KEY                the score of one account, term by term

The score (0-100), every term shown on the card:

    score = 100 x (0.30 fit + 0.30 signal + 0.20 warmth + 0.20 reach)

    fit     market, role, industry and size against icp.md (an unknown counts half)
    signal  sum of weight(kind) x recency decay (half-life icp `half_life_days`), capped at 1
    warmth  the strongest tie: strength/5 x recency (0 for a pure cold lead)
    reach   the best way in:  green 1.0 · yellow 0.6 · red 0.2 · handoff 0

Knock-outs come off BEFORE scoring, each with its rule: the seller's own exclusions and
competitors, the do-not-contact list, existing customers (a won deal in the brain or in the
ledger), excluded markets, and a size outside the band when `size_strict: on`.

The reach ladder (a lead is only a lead when there is a way in):

    green  warm      a brain tie (strength >= 3) with an address or a profile
    green  intro     a connector who knows someone there
    green  public    a business address published on a public page (the page is kept)
    yellow form      the company's own contact or demo form
    yellow social    a public LinkedIn or X profile only
    red    pattern   only a guessed address - never sent, at any level
    handoff          nothing yet - "find me a way in"
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402

REACH = {"warm": ("green", 1.0), "intro": ("green", 1.0), "public": ("green", 1.0),
         "form": ("yellow", 0.6), "social": ("yellow", 0.6), "pattern": ("red", 0.2),
         "handoff": ("handoff", 0.0)}
REACH_ORDER = ("warm", "intro", "public", "form", "social", "pattern", "handoff")


def _date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def reach_of(a):
    """The best way into the account, and the contact it runs through."""
    best, via = "handoff", ""
    for c in a.get("contacts") or []:
        options = []
        es = c.get("email_source") or ""
        if c.get("person_note") and (c.get("tie_strength") or 0) >= 3 and (c.get("email") or c.get("profile_url")) \
                and c.get("tie") != "possible":
            options.append("warm")
        if c.get("tie_via"):
            options.append("intro")
        if c.get("email") and es in ("public-page", "brain", "reply"):
            options.append("public")
        if c.get("profile_url") and re.search(r"linkedin\.com/in/|x\.com/|twitter\.com/", c["profile_url"]):
            options.append("social")
        if c.get("email") and es == "pattern-unverified":
            options.append("pattern")
        for o in options:
            if REACH_ORDER.index(o) < REACH_ORDER.index(best):
                best, via = o, c.get("name", "")
    if (a.get("form") or {}).get("url") and REACH_ORDER.index("form") < REACH_ORDER.index(best):
        best, via = "form", (a.get("form") or {}).get("url")
    return best, via


def won_accounts(brain=None):
    """Customers already: a won deal in the brain's pipeline layer, or `won` in the ledger."""
    names = set()
    try:
        import warm_rank  # noqa: PLC0415
        from paths import brain_at_cwd  # noqa: PLC0415
        b = brain or brain_at_cwd()
        if b:
            for d in warm_rank.deals(b):
                if d["account"] and warm_rank.WON.search(d["stage"] or ""):
                    names.add(ledger.name_key(d["account"]))
    except Exception:                                     # noqa: BLE001 - a brainless run still scores
        pass
    for a in ledger.load_accounts().values():
        if a.get("stage") == "won":
            names.add(ledger.name_key(a.get("name")))
    return names


def knockout(a, icp_s, supp, customers):
    nk, dom = ledger.name_key(a.get("name")), (a.get("domain") or "").lower()
    for term in prof.as_list(icp_s.get("exclude")) + prof.as_list(icp_s.get("competitors")):
        t = term.lower()
        if t and (ledger.name_key(t) == nk or (len(t) >= 4 and t in (a.get("name") or "").lower())):
            return f"excluded: {term}"
    for d in prof.as_list(icp_s.get("exclude_domains")):
        if dom and (dom == d.lower() or dom.endswith("." + d.lower())):
            return f"excluded domain: {d}"
    for s in supp:
        if (dom and (s == dom or s.endswith("@" + dom))) or ledger.name_key(s) == nk:
            return "on the do-not-contact list"
    if nk in customers:
        return "already a customer"
    bad_m = {m.lower() for m in prof.as_list(icp_s.get("exclude_markets"))}
    if bad_m and any((m or "").lower() in bad_m for m in a.get("markets") or []):
        return "excluded market"
    if prof.on(icp_s.get("size_strict")):
        size = prof.as_int(a.get("size"), 0)
        lo, hi = prof.as_int(icp_s.get("size_min"), 0), prof.as_int(icp_s.get("size_max"), 0)
        if size and ((lo and size < lo) or (hi and size > hi)):
            return f"size {size} outside {lo}-{hi}"
    return ""


def fit_of(a, icp_s, mk):
    parts = []
    if mk:
        ms = a.get("markets") or []
        parts.append(0.5 if not ms else (1.0 if any(m in mk for m in ms) else 0.0))   # unknown counts half
    roles = prof.as_list(icp_s.get("buyer_roles")) + prof.as_list(icp_s.get("need_roles")) \
        + prof.as_list(icp_s.get("champion_roles"))
    if roles:
        rx = re.compile("|".join(re.escape(r) for r in roles), re.I)
        hit = any(rx.search(s.get("what") or "") for s in a.get("signals") or [] if s.get("kind") in ("hiring", "exec_hire")) \
            or any(rx.search(c.get("role") or "") for c in a.get("contacts") or [])
        parts.append(1.0 if hit else 0.4)
    inds = prof.as_list(icp_s.get("industries"))
    own = " ".join(str(a.get(k) or "") for k in ("industry", "about")).lower()
    sig = " ".join(s.get("what") or "" for s in a.get("signals") or []).lower()
    if inds:
        if any(i.lower() in own or i.lower() in sig for i in inds):
            parts.append(1.0)
        else:
            parts.append(0.3 if own.strip() else 0.5)      # a stated other industry is a miss; silence is unknown
    lo, hi = prof.as_int(icp_s.get("size_min"), 0), prof.as_int(icp_s.get("size_max"), 0)
    size = prof.as_int(a.get("size"), 0)
    if lo or hi:
        parts.append(0.5 if not size else (1.0 if (not lo or size >= lo) and (not hi or size <= hi) else 0.0))
    return round(sum(parts) / len(parts), 3) if parts else 0.5


def signal_of(a, icp_s, today):
    w = prof.weights(icp_s)
    hl = max(1.0, float(prof.as_int(icp_s.get("half_life_days"), 30)))
    tot = 0.0
    for s in a.get("signals") or []:
        d = _date(s.get("seen")) or today
        age = max(0, (today - d).days)
        kind = s.get("kind") or "news"
        # a tie or a lost deal is history, not news: it ages over a year, not a month
        h = 365.0 if kind in ("brain", "revival") else hl
        tot += w.get(kind, 1.0) * (0.5 ** (age / h))
    return round(min(1.0, tot / 6.0), 3)


def warmth_of(a, today):
    if a.get("warmth") is not None and a.get("origin") != "cold":
        return float(a["warmth"])
    best = 0.0
    for c in a.get("contacts") or []:
        s = c.get("tie_strength") or 0
        if not s or c.get("tie") == "possible":
            continue
        d = _date(c.get("last_contact"))
        rec = 0.5 ** (((today - d).days if d else 365) / 365.0)
        best = max(best, min(1.0, s / 5.0) * max(0.1, rec))
    return round(best, 3)


def score_one(a, icp_s, mk, supp, customers, today):
    ko = knockout(a, icp_s, supp, customers)
    if ko:
        a["knocked_out"], a["score"] = ko, 0
        return a
    a.pop("knocked_out", None)
    fit, sig, warm = fit_of(a, icp_s, mk), signal_of(a, icp_s, today), warmth_of(a, today)
    r, via = reach_of(a)
    colour, rv = REACH[r]
    a.update({"fit": fit, "signal": sig, "warmth": warm, "reach": r, "reach_colour": colour,
              "reach_via": via, "score": int(round(100 * (0.30 * fit + 0.30 * sig + 0.20 * warm + 0.20 * rv)))})
    tops = sorted(a.get("signals") or [], key=lambda s: str(s.get("seen") or ""), reverse=True)[:2]
    a["why"] = " · ".join(f"{s.get('what') or s.get('kind')} ({s.get('seen') or '?'})" for s in tops)
    return a


def score_all(include_all=False, today=None):
    today = today or datetime.date.today()
    icp_s = prof.icp()
    mk, supp, customers = prof.markets(icp_s), prof.suppression(), won_accounts()
    acc = ledger.load_accounts()
    n = 0
    for a in acc.values():
        if include_all or a.get("stage", "lead") == "lead":
            score_one(a, icp_s, mk, supp, customers, today)
            n += 1
    ledger.save_accounts(acc)
    return acc, n


def shortlist(acc, n=None, include_seen=False):
    icp_s = prof.icp()
    floor = prof.as_int(icp_s.get("floor"), 60)
    target = n or prof.as_int(icp_s.get("daily_target"), 10)
    leads = [a for a in acc.values() if a.get("stage", "lead") == "lead"]
    ko = [a for a in leads if a.get("knocked_out")]
    live = [a for a in leads if not a.get("knocked_out")]
    unreachable = [a for a in live if a.get("reach") == "handoff"]
    pool = [a for a in live if a.get("reach") != "handoff" and (include_seen or a.get("new") or not a.get("reviewed"))]
    pool.sort(key=lambda a: (-(a.get("score") or 0), a["name"].lower()))
    above = [a for a in pool if (a.get("score") or 0) >= floor]
    return {"floor": floor, "target": target, "shortlist": above[:target],
            "below_floor": len(pool) - len(above), "knocked_out": ko, "unreachable": unreachable,
            "still_open": [a for a in live if a.get("reviewed") and a.get("reach") != "handoff"]}


def _brief(a):
    return {k: a.get(k) for k in ("key", "name", "score", "fit", "signal", "warmth", "reach",
                                  "reach_colour", "reach_via", "origin", "markets", "why", "knocked_out", "new")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("score"); g.add_argument("--all", action="store_true")
    g = sub.add_parser("shortlist"); g.add_argument("--n", type=int); g.add_argument("--include-seen", action="store_true")
    g.add_argument("--json", action="store_true")
    g = sub.add_parser("why"); g.add_argument("key")
    a = ap.parse_args(argv)
    if a.cmd == "score":
        acc, n = score_all(a.all)
        print(f"scored {n} accounts", file=sys.stderr)
        return 0
    if a.cmd == "shortlist":
        acc, _ = score_all()
        s = shortlist(acc, a.n, a.include_seen)
        out = {"floor": s["floor"], "target": s["target"], "below_floor": s["below_floor"],
               "shortlist": [_brief(x) for x in s["shortlist"]],
               "knocked_out": [_brief(x) for x in s["knocked_out"]],
               "unreachable": [_brief(x) for x in s["unreachable"]],
               "still_open": [_brief(x) for x in s["still_open"]]}
        (ledger.root() / "last_shortlist.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                                           encoding="utf-8")
        if a.json:
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            for x in out["shortlist"]:
                print(f"{x['score']:>4}  {x['reach']:<7} {x['origin'] or '-':<8} {x['name']}  — {x['why']}")
            short = len(out["shortlist"]) < out["target"]
            print(f"{len(out['shortlist'])} shortlisted (floor {out['floor']}, target {out['target']})"
                  + (" — a thin day; widen the SOURCES, never the ICP or the floor" if short else "")
                  + f" · {len(out['knocked_out'])} knocked out · {len(out['unreachable'])} with no way in yet",
                  file=sys.stderr)
        return 0
    acc = ledger.load_accounts()
    x = ledger.find(acc, a.key)
    if not x:
        print(f"no account {a.key!r}", file=sys.stderr)
        return 1
    icp_s = prof.icp()
    score_one(x, icp_s, prof.markets(icp_s), prof.suppression(), won_accounts(), datetime.date.today())
    print(json.dumps(_brief(x), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
