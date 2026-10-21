#!/usr/bin/env python3
"""
render_sales.py - write the sales layer of the brain from the ledger. No network, no model.

    render_sales.py [--dest DIR]

Writes, under <sales layer>/ (resolved per subject - never a hardcoded folder):

    Sales Dashboard.md       the living overview (alias "Pipeline"): needs you · due today · booked ·
                             sent this week · this week by origin · blocked, and why
    Sales KPI.md             the accounts funnel: counts, conversions, rates at n >= 20 (kpi.py)
    Sales Lessons.md         what the agent remembers (_memory/, inferred items flagged)
    pipeline.json            sbl-pipeline/2 with the funnel + the floor (Studio's Runtime)
    accounts/<Name>.md       one note per worked account: why, the buying team with evidence,
                             each contact's sequence timeline, signals, the last events
    reports/Sell today <date>.md   the dated daily note (alias "Leads <date>"): the sweep summary,
                             the coverage table, the shortlist with strategy · angle · best channel.
                             When daily.py opened it first, only its "New today" section is refreshed.
    outreach/<date>/<key>/   every sent step (and every drafted one in a batch) as a note

    render_sales.py --migrate-layout   Pipeline.md -> Sales Dashboard.md, leads/ -> reports/, old stage ids

Everything is derived from accounts.jsonl + events.jsonl + the scout state, so a re-render
with no new events is byte-identical. A note the user edited (its hash no longer matches the
manifest, _SALES_GENERATED.json in the state root) is left alone and listed in the output.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402
import scout  # noqa: E402
import pipeline_doc as pdoc  # noqa: E402
import sequence  # noqa: E402
import kpi as KPIlib  # noqa: E402
import stages as STG  # noqa: E402
from ledger_base import Writer as _BaseWriter, replace_between  # noqa: E402
from paths import render_dir, surface_root, is_brain, layer  # noqa: E402

BOARD = ("researched", "sequenced", "contacted", "replied", "meeting", "trial", "won", "lost")
DASHBOARD = "Sales Dashboard.md"
KPI = "Sales KPI.md"
LESSONS = "Sales Lessons.md"
DAILY_SCHEMA = "sbl-daily/1"
TODAY = datetime.date.today().isoformat()


def contract():
    """The plugin's own studio.json (the sbl-agent/1 contract: funnels, floor, layout)."""
    here = pathlib.Path(__file__).resolve()
    for d in [here.parent] + list(here.parents):
        sj = d / "studio.json"
        if sj.is_file():
            try:
                return json.loads(sj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                break
    return {}
SOCIAL = ("linkedin_invite", "linkedin_dm", "x_dm", "whatsapp")
GLYPH = {"revival": "◆", "warm": "●", "dormant": "●", "intro": "◇", "cold": "○"}
REACH_GLYPH = {"warm": "🟢 warm", "intro": "🟢 intro", "public": "🟢 public", "form": "🟡 form",
               "social": "🟡 social", "pattern": "🔴 guessed address", "handoff": "⛔ no way in yet"}
MANIFEST = "_SALES_GENERATED.json"


def safe(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip() or "Account"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def esc(s):
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def fm(d):
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            out.append(f"{k}:")
            out += [f"  - {json.dumps(x, ensure_ascii=False) if isinstance(x, str) and (':' in x or '[' in x) else x}" for x in v]
        elif v in (None, ""):
            out.append(f"{k}:")
        elif isinstance(v, str) and (v.startswith("[[") or ":" in v or v.startswith(("-", "*", "#", "{"))):
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    return "\n".join(out)


class Writer(_BaseWriter):
    """The shared R6 writer (ledger_base.Writer). pipeline.json is machine data: always rewritten.
    A NOTE is the seller's once they touch it - an edited or foreign note is never overwritten; the
    fresh render lands beside it as <name>.new.md and the path is listed in `kept`."""

    def __init__(self, base):
        super().__init__(base, ledger.root() / MANIFEST, quiet=True)
        self.base = self.root

    def put(self, rel, text):
        self.text(rel, text, machine=not str(rel).endswith(".md"))

    @property
    def written(self):
        return self.wrote

    def close(self):
        self.finish()


def brain_link(rel_note):
    """[[note|Name]] for a brain note path (without .md), when it is inside the brain."""
    if not rel_note:
        return ""
    name = rel_note.rsplit("/", 1)[-1]
    return f"[[{rel_note}|{name}]]" if "/" in rel_note else f"[[{name}]]"


def org_link(name):
    s = surface_root()
    if is_brain(s) and (s / layer(s, "orgs") / f"{safe(name)}.md").is_file():
        return f"[[{safe(name)}]]"
    return ""


def last_ts(evs):
    return max((e.get("ts", "") for e in evs), default="")


def next_step(tl):
    best = None
    for name, c in (tl.get("contacts") or {}).items():
        for s in c["steps"]:
            if s.get("status") in ("due", "upcoming") and s.get("date"):
                cand = (s["date"], name, s)
                if best is None or cand[0] < best[0]:
                    best = cand
                break
    if not best:
        return None
    d, name, s = best
    return {"channel": s["channel"], "due": d, "label": f"{name} · step {s['n']} {s['channel']}"}


def needs_you(a, evs):
    """An open gate for this account, or a reply nobody answered yet."""
    rep = [e for e in evs if e.get("kind") == "replied"]
    ans = [e for e in evs if e.get("kind") in ("answered", "meeting_booked")]
    if rep and (not ans or rep[-1]["ts"] > ans[-1]["ts"]):
        return "reply waiting — " + (rep[-1].get("reply_class") or "read it")
    gated = [e for e in evs if e.get("kind") == "gated"]
    closed = [e for e in evs if e.get("kind") in ("sent", "approved", "denied", "answered")]
    if gated and (not closed or gated[-1]["ts"] > closed[-1]["ts"]):
        return "approval waiting"
    return ""


def panel(a, tl=None):
    """What Studio's account panel draws: the buying team with evidence, each contact's steps,
    the dated signals and the deal history - ids, names and URLs only, nothing private."""
    reach_word = {"brain": "address from your brain", "public-page": "published address", "reply": "address from their reply",
                  "pattern-unverified": "guessed address — never sent"}
    team = []
    for c in (a.get("contacts") or [])[:8]:
        team.append({"name": c.get("name"), "role": c.get("role") or "", "evidence": c.get("role_source") or ("your brain" if c.get("person_note") else ""),
                     "note": (c["person_note"] + ".md") if c.get("person_note") else "",
                     "tie": c.get("tie_strength") or 0, "possible": c.get("tie") == "possible", "via": c.get("tie_via") or "",
                     "address": reach_word.get(c.get("email_source") or "", ""),
                     "profile": "linkedin.com/in/" in (c.get("profile_url") or "")})
    steps = {}
    for name, c in ((tl or {}).get("contacts") or {}).items():
        steps[name] = {"stopped": c.get("stopped") or "",
                       "steps": [{"n": x["n"], "channel": x["channel"], "kind": x["kind"], "status": x["status"],
                                  "date": x.get("date") or "", "why": x.get("why") or "", "assisted": bool(x.get("assisted"))}
                                 for x in c["steps"]]}
    sig = sorted(a.get("signals") or [], key=lambda x: str(x.get("seen") or ""), reverse=True)[:6]
    return {"team": team, "sequence": (tl or {}).get("sequence") or "", "steps": steps,
            "signals": [{"kind": x.get("kind"), "label": x.get("what"), "url": x.get("url") if str(x.get("url") or "").startswith("https://") else "",
                         "seen": x.get("seen")} for x in sig],
            "deals": [d + ".md" for d in a.get("deal_history") or []],
            "form": bool((a.get("form") or {}).get("url")), "knocked_out": a.get("knocked_out") or ""}


def account_note(a, evs, tl):
    warm = next((c for c in a.get("contacts") or [] if c.get("person_note")), None)
    meta = {"type": "sales-account", "title": a["name"],
            "tags": ["sales-account", f"sales/stage/{a.get('stage', 'lead')}", f"sales/origin/{a.get('origin') or 'cold'}"],
            "org": org_link(a["name"]), "stage": a.get("stage", "lead"), "origin": a.get("origin") or "cold",
            "score": a.get("score"), "fit": a.get("fit"), "warmth": a.get("warmth"), "reach": a.get("reach"),
            "segment": a.get("segment", ""), "markets": a.get("markets") or [], "domain": a.get("domain", ""),
            "sequence": a.get("sequence", ""), "first_seen": a.get("first_seen", ""), "key": a["key"]}
    L = [fm(meta), "", f"# {a['name']}", ""]
    if a.get("why"):
        L += [f"**Why now:** {a['why']}", ""]
    if a.get("knocked_out"):
        L += [f"> [!warning] Knocked out — {a['knocked_out']}", ""]
    terms = [f"fit {a.get('fit')}", f"signal {a.get('signal')}", f"warmth {a.get('warmth')}",
             f"reach {REACH_GLYPH.get(a.get('reach'), a.get('reach') or '?')}"]
    L += [f"Score **{a.get('score', '—')}** — " + " · ".join(terms), ""]
    if a.get("deal_history"):
        L += ["**Deal history:** " + ", ".join(brain_link(d) for d in a["deal_history"]), ""]
    L += ["## Buying team", "", "| Contact | Role | Evidence | Tie | Reach |", "|---|---|---|---|---|"]
    for c in a.get("contacts") or []:
        who = brain_link(c["person_note"]) if c.get("person_note") else esc(c["name"])
        ev = c.get("role_source") or ("your brain" if c.get("person_note") else "—")
        tie = f"{c.get('tie_strength')}/5" if c.get("tie_strength") else "—"
        if c.get("tie") == "possible":
            tie += " (name match only)"
        if c.get("tie_via"):
            tie += f" · via {esc(c['tie_via'])}"
        addr = {"brain": "✉ from your brain", "public-page": "✉ published", "reply": "✉ from their reply",
                "pattern-unverified": "✕ guessed — never sent"}.get(c.get("email_source") or "", "")
        prof_ = "in profile" if "linkedin.com/in/" in (c.get("profile_url") or "") else ""
        L.append(f"| {who} | {esc(c.get('role'))} | {esc(ev)} | {tie} | {' · '.join(x for x in (addr, prof_) if x) or '—'} |")
    if not a.get("contacts"):
        L.append("| _no named buyer yet_ | | | | |")
    if (a.get("form") or {}).get("url"):
        L += ["", f"Contact form: {a['form']['url']}"]
    if tl.get("contacts"):
        L += ["", f"## Sequence — {tl['sequence']} (started {tl['started']})", ""]
        for name, c in tl["contacts"].items():
            L.append(f"**{esc(name)}**" + (f" — stopped: {c['stopped']}" if c.get("stopped") else ""))
            for s in c["steps"]:
                mark = {"sent": "✓", "due": "⏳", "upcoming": "·", "waiting": "…", "skipped": "–", "stopped": "■"}[s["status"]]
                when = s.get("date") or s.get("why") or ""
                L.append(f"- {mark} {s['n']} {s['channel']} {s['kind']} — {s['status']}"
                         + (f" {when}" if when else "") + (" (you press Send)" if s.get("assisted") else ""))
            L.append("")
    if a.get("signals"):
        L += ["## Signals", ""]
        for s in sorted(a["signals"], key=lambda s: str(s.get("seen") or ""), reverse=True)[:12]:
            src = s.get("url") or ""
            link = (brain_link(src) if src and not src.startswith("http") else (f"[source]({src})" if src else ""))
            L.append(f"- {s.get('seen') or '?'} · {s.get('kind')} · {esc(s.get('what'))} {link}".rstrip())
        L.append("")
    shown = [e for e in evs if e.get("kind") != "guard"]       # a guard verdict is echoed by its outcome
    if shown:
        L += ["## Ledger", "", "| When | Event | Who | Detail |", "|---|---|---|---|"]
        for e in shown[-15:]:
            det = e.get("rule") or e.get("subject") or e.get("reason") or e.get("to") or e.get("sequence") or ""
            L.append(f"| {str(e.get('ts') or e.get('at') or '')[:16].replace('T', ' ')} | {e.get('kind') or 'stage'} | {esc(e.get('contact'))} | {esc(det)} |")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def render(dest=None):
    base = pathlib.Path(dest) if dest else render_dir()
    w = Writer(base)
    acc = ledger.load_accounts()
    evs = ledger.events()
    snd = prof.sending()
    st = scout.load_state()
    by_acc = {}
    for e in evs:
        by_acc.setdefault(e.get("account") or "", []).append(e)
    today = datetime.date.today()
    tz_today = today.isoformat()
    # pipeline.json speaks in BRAIN-relative paths (what Studio opens); notes in the layer
    # link layer-relative, which Obsidian resolves.
    pre = base.name + "/" if is_brain(base.parent) else ""
    cards, needs = [], []
    for a in sorted(acc.values(), key=lambda v: v["name"].lower()):
        stage = a.get("stage", "lead")
        if stage == "lead":
            continue
        mine = by_acc.get(a["key"], [])
        tl = sequence.timeline(a, today, mine, snd)
        rel = f"accounts/{safe(a['name'])}.md"
        w.put(rel, account_note(a, mine, tl))
        nx = next_step(tl) if tl else None
        flag = needs_you(a, mine)
        warm = next((c for c in a.get("contacts") or [] if c.get("person_note") and (c.get("tie_strength") or 0) >= 3), None)
        card = {"id": a["key"], "title": a["name"], "note": pre + rel, "stage": stage, "origin": a.get("origin") or "cold",
                "score": a.get("score"), "fit": a.get("fit"), "warmth": a.get("warmth"), "reach": a.get("reach"),
                "why": a.get("why", ""), "segment": a.get("segment", ""),
                "channels": sorted({ch for c in a.get("contacts") or [] for ch in c.get("channels") or []}),
                "flags": ["needs-you"] if flag else [], "needs": flag}
        if warm:
            card["warm"] = {"label": f"via {warm['name']}", "note": warm["person_note"] + ".md"}
        if nx:
            card["next"] = nx
        card["panel"] = panel(a, tl)
        cards.append(card)
        if flag:
            needs.append((a, flag))
    # today
    sent_today = [e for e in evs if e.get("kind") == "sent" and not e.get("dry_run") and e.get("ts", "")[:10] == tz_today]
    today_box = {"sent": sum(1 for e in sent_today if e.get("channel") == "email"),
                 "cap": prof.as_int(snd.get("cap.email"), 25),
                 "social_sent": sum(1 for e in sent_today if e.get("channel") in SOCIAL),
                 "social_cap": prof.as_int(snd.get("cap.linkedin_invite"), 10) + prof.as_int(snd.get("cap.linkedin_dm"), 15),
                 "forms": sum(1 for e in sent_today if e.get("channel") == "form"),
                 "replies_waiting": sum(1 for _, f in needs if f.startswith("reply waiting")),
                 "approvals_waiting": sum(1 for _, f in needs if f == "approval waiting"),
                 "meetings": sum(1 for c in cards if c["stage"] == "meeting"),
                 "level": snd.get("level"), "social_auto": prof.on(snd.get("social_auto"))}
    # leads
    try:
        sl = json.loads((ledger.root() / "last_shortlist.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sl = {}
    leads = []
    for x in sl.get("shortlist") or []:
        a = acc.get(x["key"], {})
        if a.get("stage", "lead") != "lead":
            continue
        warm = next((c for c in a.get("contacts") or [] if c.get("person_note")), None)
        sig = sorted(a.get("signals") or [], key=lambda s: str(s.get("seen") or ""), reverse=True)[:3]
        leads.append({"id": x["key"], "title": x["name"], "score": x.get("score"), "market": ", ".join(x.get("markets") or []),
                      "reach": x.get("reach"), "origin": x.get("origin"), "new": bool(x.get("new")),
                      "signals": [{"kind": s.get("kind"), "label": s.get("what"), "url": s.get("url"), "seen": s.get("seen")} for s in sig],
                      "warm": {"label": warm["name"], "note": warm["person_note"] + ".md"} if warm else None,
                      "why": x.get("why") or "", "note": pre + f"accounts/{safe(x['name'])}.md", "panel": panel(a)})
    cov = [{"market": m, "sources": len(c["sources"]), "qualified": c["qualified"], "state": c.get("verdict"),
            "names": sorted(c["sources"])} for m, c in sorted((st.get("coverage") or {}).items())]
    stamp = max(last_ts(evs), st.get("merged_at") or "")
    setup = prof.missing()
    starter = bool(sl.get("starter"))
    summary = scout.summary_line(st) + (f", {len(leads)} shortlisted" if st else "")
    if starter:
        summary = (f"From your brain only — {len(leads)} accounts you already have a way into"
                   + ("" if not setup else "; set up your profile to sweep the web for more"))
    pj = pipeline_v2(acc, by_acc, cards, sl, st, cov, stamp, setup, starter, summary, today_box, pre, today, snd)
    w.put("pipeline.json", pdoc.dumps(pj))
    # the lead report
    if sl and st.get("merged_at"):
        head = (f"> {summary}." if starter else
                f"> {scout.summary_line(st)}, {len(leads)} shortlisted (floor {sl.get('floor')}, target {sl.get('target')}).")
        L = [fm({"type": "sales-leads", "title": f"Leads {st['merged_at']}", "tags": ["sales-leads"],
                 "date": st["merged_at"]}), "", f"# Leads — {st['merged_at']}", "",
             head, "",
             "## Coverage", "", scout.coverage_table(st), "", "## Shortlist", "",
             "| Score | Account | Market | Why now | Way in |", "|---|---|---|---|---|"]
        for x in sl.get("shortlist") or []:
            L.append(f"| {x.get('score')} | [[accounts/{safe(x['name'])}|{esc(x['name'])}]] | {esc(', '.join(x.get('markets') or []))} | "
                     f"{esc(x.get('why'))} | {REACH_GLYPH.get(x.get('reach'), x.get('reach'))} |")
        if not sl.get("shortlist"):
            L.append("| — | _nothing cleared the floor today_ | | | |")
        if len(sl.get("shortlist") or []) < (sl.get("target") or 0):
            L += ["", "_A thin day. The answer is more sources, never a wider ICP or a lower floor._"]
        for title, key in (("Knocked out", "knocked_out"), ("No reachable buyer yet", "unreachable"),
                           ("Still open from earlier", "still_open")):
            rows = sl.get(key) or []
            if rows:
                L += ["", f"## {title} ({len(rows)})", ""]
                L += [f"- {esc(x['name'])} — {esc(x.get('knocked_out') or x.get('why') or REACH_GLYPH.get(x.get('reach'), ''))}"
                      for x in rows[:40]]
        day = str(st["merged_at"])[:10]
        daily = base / "reports" / f"Sell today {day}.md"
        if daily.is_file() and merge_into_daily(daily, "\n".join(L)):
            pass            # daily.py opened the note first: only its "New today" section was refreshed
        else:
            L[0] = fm({"type": "sales-daily", "title": f"Sell today {day}", "tags": ["sales-daily"], "date": day,
                       "aliases": [f"Leads {st['merged_at']}"]})
            L[2] = f"# Sell today {day}"
            w.put(f"reports/Sell today {day}.md", "\n".join(L).rstrip() + "\n")
        # shortlisted leads get a note too, so the report's links resolve
        for x in sl.get("shortlist") or []:
            a = acc.get(x["key"])
            if a and a.get("stage", "lead") == "lead":
                w.put(f"accounts/{safe(a['name'])}.md", account_note(a, by_acc.get(a["key"], []), {}))
    # the home note
    k = ledger.kpi()
    week = [e for e in evs if e.get("kind") == "sent" and not e.get("dry_run")
            and e.get("ts", "")[:10] >= (today - datetime.timedelta(days=7)).isoformat()]
    due_rows = sequence.due(today)
    blocked, seen_b = [], set()
    for e in evs:
        if e.get("kind") != "send_blocked" or e.get("ts", "")[:10] < (today - datetime.timedelta(days=7)).isoformat():
            continue
        bk = (e["ts"][:10], e.get("account"), e.get("contact"), e.get("rule"))
        if bk not in seen_b:                    # the same refusal re-checked is one line, not many
            seen_b.add(bk)
            blocked.append(e)
    booked = [c for c in cards if c["stage"] == "meeting"]
    H = [fm({"type": "sales-dashboard", "title": "Sales Dashboard", "tags": ["sales-dashboard"], "updated": stamp[:10],
             "level": snd.get("level"), "aliases": ["Pipeline"]}), "", "# Sales Dashboard", "",
         *([f"Today: [[Sell today {today.isoformat()}]] · [[Sales KPI]] · [[Sales Lessons]]", ""]
           if (base / "reports" / f"Sell today {today.isoformat()}.md").is_file() else ["[[Sales KPI]] · [[Sales Lessons]]", ""]),
         f"Autonomy **{snd.get('level')}** · social steps **{'on' if prof.on(snd.get('social_auto')) else 'off (you press Send)'}** · "
         f"today ✉ {today_box['sent']}/{today_box['cap']} · social {today_box['social_sent']}", "",
         *(["## Start here", "",
             "Your profile is not set up yet, so this is a preview from your brain alone. Ask the Sales Agent "
             "**\"Set me up\"** — it reads this brain and your deck first and asks only the decisions.", ""]
            + [f"- [ ] {g}" for g in setup] + [""] if setup else []),
         "| Needs you | Due today | Booked | Sent this week |", "|---|---|---|---|",
         f"| {len(needs)} | {len(due_rows)} | {len(booked)} | {sum(1 for e in week if e.get('channel') == 'email')} ✉ · "
         f"{sum(1 for e in week if e.get('channel') in SOCIAL)} social · {sum(1 for e in week if e.get('channel') == 'form')} forms |", ""]
    if needs:
        H += ["## Needs you", ""] + [f"- [[accounts/{safe(a['name'])}|{esc(a['name'])}]] — {esc(f)}" for a, f in needs] + [""]
    if due_rows:
        H += ["## Due today", "", "| Account | Contact | Step | Channel |", "|---|---|---|---|"]
        H += [f"| [[accounts/{safe(r['name'])}|{esc(r['name'])}]] | {esc(r['contact'])} | {r['step']} {r['kind']} | {r['channel']}"
              + (" (you send)" if r["assisted"] else "") + " |" for r in due_rows[:40]] + [""]
    if booked:
        H += ["## Meetings", ""] + [f"- [[accounts/{safe(c['title'])}|{esc(c['title'])}]]" for c in booked] + [""]
    if leads:
        H += [f"## Today's leads ({len(leads)})", "", f"[[Sell today {str(st.get('merged_at'))[:10]}]] — "
              f"{summary}.", ""]
    H += ["## This week by origin", "", "| Origin | Sent | Replied | Meetings | Reply rate |", "|---|---|---|---|---|"]
    for o, r in sorted((k["dims"].get("origin") or {}).items()):
        rate = f"{r['reply_rate']:.0%}" if r["reply_rate"] is not None else "counts only (n < 20)"
        H.append(f"| {o} | {r['sent']} | {r['replied']} | {r['meetings']} | {rate} |")
    if not k["dims"].get("origin"):
        H.append("| — | 0 | 0 | 0 | counts only (n < 20) |")
    if blocked:
        H += ["", f"## Blocked this week ({len(blocked)}) — why", ""]
        H += [f"- {e['ts'][:10]} {esc(acc.get(e.get('account'), {}).get('name') or e.get('account'))} · {esc(e.get('contact'))} — {esc(e.get('rule'))}"
              for e in blocked[-20:]]
    w.put(DASHBOARD, "\n".join(H).rstrip() + "\n")
    write_outreach(w, acc, evs)
    w.put(KPI, kpi_note(pj, evs))
    w.put(LESSONS, lessons_note())
    w.close()
    return w


def merge_into_daily(path, body):
    """The dated note daily.py opened FIRST (schema sbl-daily/1) keeps its Status / Goal / the model's
    words; the lead report goes into its `## New today` section between markers (R2)."""
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return False
    head = txt.split("---", 2)[1] if txt.startswith("---") else ""
    if f"schema: {DAILY_SCHEMA}" not in head:
        return False
    body = re.sub(r"\A\ufeff?\s*---\s*\n.*?\n---[ \t]*\n", "", body, count=1, flags=re.S)
    body = re.sub(r"\A\s*#\s+.*\n", "", body, count=1).strip("\n")
    if "## New today" in txt and "<!-- new-today:begin -->" not in txt:
        pat = re.compile(r"(^## New today\n)(.*?)(?=^## |^Back to \[\[|\Z)", re.S | re.M)
        new = pat.sub(lambda m: m.group(1) + "\n<!-- new-today:begin -->\n" + body + "\n<!-- new-today:end -->\n\n", txt, count=1)
    else:
        new = replace_between(txt, "new-today", body, heading="New today")
    if new != txt:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    return True


def write_outreach(w, acc, evs):
    """outreach/<date>/<account key>/ - one note per sent step (the evidence: channel, contact, subject,
    message id) and per drafted step waiting in a batch. Bodies come from the batch notes."""
    drafts = {}
    bdir = ledger.root() / "batches"
    if bdir.is_dir():
        for bp in sorted(bdir.glob("*.json")):
            try:
                data = json.loads(bp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for it in data.get("items") or []:
                if it.get("verdict") == "BLOCK":
                    continue
                drafts.setdefault((it.get("account"), it.get("contact"), it.get("channel"), it.get("step")), (bp.stem, it))
    for e in evs:
        if e.get("kind") != "sent" or e.get("dry_run"):
            continue
        key = e.get("account") or ""
        a = acc.get(key, {})
        day = str(e.get("ts") or "")[:10] or TODAY
        step = e.get("step")
        title = f"Step {step or '?'} · {e.get('channel')} · {safe(e.get('contact') or '')}"
        meta = {"type": "sales-outreach", "title": f"{safe(a.get('name') or key)} · {title}", "tags": ["sales-outreach"],
                "account": a.get("name") or key, "contact": e.get("contact") or "", "channel": e.get("channel") or "",
                "step": step, "sent": str(e.get("ts") or "")[:16], "batch": e.get("batch") or ""}
        body = [fm(meta), "", f"# {safe(a.get('name') or key)} — {title}", "",
                f"**Sent** {str(e.get('ts') or '')[:16].replace('T', ' ')} from the seller's own {e.get('channel')}"
                + (f" · batch {e.get('batch')}" if e.get("batch") else "") + (f" · subject *{esc(e.get('subject'))}*" if e.get("subject") else ""), ""]
        if e.get("message_id"):
            body.append(f"Message id: `{e['message_id']}`")
        if e.get("evidence"):
            body += ["", "Evidence: " + esc(e["evidence"])]
        d = drafts.get((key, e.get("contact"), e.get("channel"), step))
        if d and d[1].get("body"):
            body += ["", "```text", str(d[1]["body"]).rstrip(), "```"]
        body += ["", f"Back to [[{safe(a.get('name') or key)}]] · [[Sales Dashboard]]"]
        w.put(f"outreach/{day}/{key}/{safe(title)}.md", "\n".join(body).rstrip() + "\n")
        drafts.pop((key, e.get("contact"), e.get("channel"), step), None)
    for (key, contact, channel, step), (bid, it) in sorted(drafts.items(), key=lambda x: str(x)):
        a = acc.get(key or "", {})
        title = f"Draft step {step or '?'} · {channel} · {safe(contact or '')}"
        meta = {"type": "sales-outreach", "title": f"{safe(a.get('name') or key)} · {title}", "tags": ["sales-outreach", "draft"],
                "account": a.get("name") or key, "contact": contact or "", "channel": channel or "", "step": step, "batch": bid}
        body = [fm(meta), "", f"# {safe(a.get('name') or key)} — {title}", "", f"**Draft** — waiting in [[Batch {bid}]]; never sent until approved.", ""]
        if it.get("subject"):
            body.append(f"**Subject:** {esc(it['subject'])}")
        if it.get("body"):
            body += ["", "```text", str(it["body"]).rstrip(), "```"]
        body += ["", f"Back to [[{safe(a.get('name') or key)}]] · [[Sales Dashboard]]"]
        w.put(f"outreach/{TODAY}/{key}/{safe(title)}.md", "\n".join(body).rstrip() + "\n")


def kpi_events(evs):
    """The ledger's stage moves as kpi.py reads them: {key, from, to, at}."""
    return [{"key": e.get("account"), "from": e.get("from"), "to": e.get("to"), "at": str(e.get("ts") or "")[:10]}
            for e in evs if e.get("kind") == "stage"]


def kpi_note(doc, evs):
    k = KPIlib.compute(doc, kpi_events(evs), today=TODAY, signals=["origin", "segment", "channel", "step", "signal"])
    old = ledger.kpi()
    t = old["totals"]
    extra = ["## Touches", "", f"sent **{t['sent']}** · replies **{t['replies']}** · meetings **{t['meetings']}** · trials **{t.get('trials', t.get('opportunities', 0))}** · won **{t['won']}**", ""]
    for dim, vals in old["dims"].items():
        extra += [f"### By {dim} (sends)", "", f"| {dim} | sent | replied | meetings | reply rate |", "|---|---|---|---|---|"]
        for v, r in sorted(vals.items(), key=lambda x: -x[1]["sent"]):
            rate = f"{r['reply_rate']:.0%}" if r["reply_rate"] is not None else "counts only (n < 20)"
            extra.append(f"| {v} | {r['sent']} | {r['replied']} | {r['meetings']} | {rate} |")
        extra.append("")
    return KPIlib.markdown(k, "Sales", title="Sales KPI", extra="\n".join(extra), tags=["sales"])


def lessons_note():
    body = ""
    try:
        import memory as M  # noqa: PLC0415
        root = ledger.root()
        brain = str(root.parent.parent) if root.parent.name == ".plugins" else None
        items = M.recall("sales", None, 4000, stamp=False, brain=brain)
        body = "\n".join("- " + M.recall_line(it) for it in items)
    except Exception:  # noqa: BLE001
        body = ""
    return (fm({"type": "synthesis", "title": "Sales Lessons", "tags": ["sales", "lessons"], "updated": TODAY}) + "\n\n# Sales Lessons\n\n"
            "> What outcomes taught this agent (`_memory/`, scope `sales`). Inferred items are flagged; edit or remove them in Studio's Memory manager.\n\n"
            + (body or "_Nothing learned yet._") + "\n\nBack to [[Sales Dashboard]]\n")


def migrate_layout(dest=None, dry_run=False):
    """The standard layout THROUGH the manifest (a note the seller edited stays where it is and is
    listed): Pipeline.md -> Sales Dashboard.md (alias Pipeline), leads/Leads <date>.md ->
    reports/Sell today <date>.md (alias Leads <date>); then the ledger's old stage ids."""
    base = pathlib.Path(dest) if dest else render_dir()
    moves = []
    if (base / "Pipeline.md").is_file():
        moves.append(("Pipeline.md", DASHBOARD, "Pipeline"))
    for p_ in sorted((base / "leads").glob("Leads *.md")) if (base / "leads").is_dir() else []:
        day = p_.stem[len("Leads "):][:10]
        moves.append((f"leads/{p_.name}", f"reports/Sell today {day}.md", p_.stem))
    w = Writer(base)
    rep_ = w.migrate_layout(moves, dry_run=dry_run)
    for a_, b_ in rep_["moved"]:
        print(f"{'would move' if dry_run else 'move'}  {a_} -> {b_}")
    for left in rep_["left"]:
        print(f"LEFT (edited by you): {left}")
    for a_, b_, why in rep_["skipped"]:
        print(f"SKIPPED {a_} -> {b_} ({why})")
    mig = {"changed": 0} if dry_run else ledger.migrate()
    print(f"{len(rep_['moved'])} moved, {len(rep_['left'])} left, {len(rep_['skipped'])} skipped; "
          f"{mig['changed']} account(s) re-staged. Nothing was deleted.")
    return 0



ORIGIN_GLYPH = {"revival": "◆", "warm": "●", "dormant": "●", "intro": "◇", "cold": "○"}


def pipeline_v2(acc, by_acc, cards, sl, st, cov, stamp, setup, starter, summary, today_box, pre, today, snd):
    """The Sales Agent's pipeline file, schema sbl-pipeline/2 (pipeline_doc.py) - every account in
    the registry as one item, so the Pipeline canvas shows the whole funnel at any size."""
    S, A = pdoc.stage, pdoc.action
    doc = pdoc.new("sales", "Sales", "#d9480f")
    doc["generated"] = stamp
    NEXT = {"lead": ["researched", "nurture"], "researched": ["sequenced", "nurture", "lost"],
            "sequenced": ["contacted", "replied", "nurture", "lost"], "contacted": ["replied", "meeting", "nurture", "lost"],
            "replied": ["meeting", "trial", "nurture", "lost"], "meeting": ["trial", "won", "lost"], "trial": ["won", "lost"],
            "lost": ["researched"], "nurture": ["researched"]}
    PROMPT = {"researched": "Research {title} for me — the buying team, a way in for each person, the strategy and the reach-out mix.",
              "sequenced": "Start the sequence that fits {title} and bring the first touch to me.",
              "won": "Mark {title} as won.", "lost": "Mark {title} as lost.", "nurture": "Park {title} as not now.",
              "trial": "Record that {title} started a trial."}
    c = contract()
    funnels = []
    for f in c.get("funnels") or []:
        stages = [S(x["id"], x.get("label") or x["id"].title(), x.get("role", "open"), next=NEXT.get(x["id"], []),
                    gate=x.get("gate", "none"), move_prompt=PROMPT.get(x["id"], "Move {title} to {stage_label}."))
                  for x in f["stages"]]
        funnels.append(pdoc.funnel(f["id"], f["label"], f["item"], f["success"], stages, f.get("success2")))
    doc["funnels"] = funnels
    doc["floor"] = [pdoc.floor_group(g["id"], g["label"], g["stages"], g.get("funnel")) for g in (c.get("floor") or [])]
    shortlisted = {x.get("key") for x in (sl.get("shortlist") or [])}
    card_by = {c["id"]: c for c in cards}
    items = []
    for a in sorted(acc.values(), key=lambda v: v["name"].lower()):
        stage = a.get("stage", "lead")
        if stage == "lead" and a.get("knocked_out"):
            stage = "out"
        c = card_by.get(a["key"], {})
        flags = list(c.get("flags") or [])
        if a["key"] in shortlisted:
            flags.append("shortlist")
        if a.get("new"):
            flags.append("new")
        worked = stage not in ("lead", "out", "nurture", "lost") or a["key"] in shortlisted
        noted = stage != "lead" or a["key"] in shortlisted
        mine = by_acc.get(a["key"], [])
        sent = [e for e in mine if e.get("kind") == "sent" and not e.get("dry_run")]
        sig = sorted(a.get("signals") or [], key=lambda x: str(x.get("seen") or ""), reverse=True)
        attrs = {"origin": a.get("origin") or "cold", "reach": a.get("reach") or "",
                 "market": (a.get("markets") or [""])[0], "segment": a.get("segment") or "",
                 "warmth": int(round(100 * float(a.get("warmth") or 0))),
                 "channel": (sent[0].get("channel") if sent else (a.get("channels") or [""])[0]) or "",
                 "step": str(max((int(e.get("step") or 0) for e in sent), default=0) or ""),
                 "signal": (sig[0].get("kind") if sig else "") or "", "strategy": a.get("strategy") or "",
                 "angle": a.get("angle") or "", "offer": a.get("offer") or "", "day": str(a.get("first_seen") or "")[:10]}
        attrs = {k: v for k, v in attrs.items() if v not in ("", None)}
        sub = " · ".join(x for x in (", ".join(a.get("markets") or []), a.get("segment") or "") if x)
        it = pdoc.item(a["key"], a["name"], stage, funnel="accounts", sub=sub, score=a.get("score"), flags=flags or None,
                       needs=c.get("needs") or None, why=a.get("knocked_out") or a.get("why") or None,
                       note=(pre + f"accounts/{safe(a['name'])}.md") if noted else None,
                       attrs=attrs, next=c.get("next"), stage_since=a.get("stage_since") or a.get("first_seen"),
                       updated=a.get("last_seen"))
        if worked:
            it["detail"] = c.get("panel") or panel(a)
        items.append(it)
    doc["items"] = items
    sent = sum(1 for es in by_acc.values() for e in es if e.get("kind") == "sent" and not e.get("dry_run"))
    replies = sum(1 for es in by_acc.values() for e in es if e.get("kind") == "replied")
    meetings = sum(1 for es in by_acc.values() for e in es if e.get("kind") == "meeting_booked")
    trials = sum(1 for a in acc.values() if a.get("stage") in ("trial", "won"))
    doc["headline"] = {"label": "trials", "value": trials, "n": sent, "period": "all time"}
    doc["throughput"] = pdoc.throughput((c.get("throughput") or {}).get("label") or "touches / day",
                                        [e.get("ts") for es in by_acc.values() for e in es if e.get("kind") == "sent" and not e.get("dry_run")], today.isoformat())
    doc["stats"] = [{"label": "replies / sends", "num": replies, "den": sent, "min_n": 20},
                    {"label": "meetings / sends", "num": meetings, "den": sent, "min_n": 20},
                    {"label": "trials / meetings", "num": trials, "den": meetings, "min_n": 20}]
    notices = []
    if setup:
        notices.append({"level": "warn", "text": "Profile not set up — " + ("a preview from your brain only" if starter else "set it up to sweep the web"),
                        "action": A("Set me up", "Set up or update my sales profile — read this brain and my deck first, then ask me only the decisions.")})
    for c in cov:
        if c.get("state") in ("failure", "partial"):
            notices.append({"level": "warn", "text": f"{c['market']} searched by {c['sources']} source" + ("" if c["sources"] == 1 else "s"),
                            "action": A("Widen", f"Widen the lead sweep for {c['market']} until at least three sources were searched, then show me the coverage table.")})
    if today_box.get("approvals_waiting"):
        notices.append({"level": "info", "text": f"{today_box['approvals_waiting']} approval(s) waiting",
                        "action": A("Review", "Show me what is waiting for my approval.")})
    doc["notices"] = notices
    doc["lenses"] = [pdoc.lens("score", "Score", "score", domain=[0, 100]),
                     pdoc.lens("warmth", "Warmth", "attrs.warmth", domain=[0, 100]),
                     pdoc.lens("age", "Age", "stage_since", scale="days", buckets=[3, 7, 14, 30]),
                     pdoc.lens("needs", "Needs you", "flags", scale="flag", value="needs-you"),
                     pdoc.lens("today", "New today", "attrs.day", scale="flag", value=today.isoformat())]
    doc["facets"] = [pdoc.facet("origin", "Origin", "attrs.origin", {k: {"label": k, "glyph": g} for k, g in ORIGIN_GLYPH.items()}),
                     pdoc.facet("reach", "Way in", "attrs.reach"),
                     pdoc.facet("market", "Market", "attrs.market"),
                     pdoc.facet("segment", "Segment", "attrs.segment"),
                     pdoc.facet("channel", "Channel", "attrs.channel"), pdoc.facet("strategy", "Strategy", "attrs.strategy")]
    doc["panel"] = {
        "top": ["{attrs.origin}", "{stage_label}", "score {score}", "{attrs.market}"],
        "sections": [{"type": "text", "label": "Why now", "from": "why"},
                     {"type": "people", "label": "Buying team", "from": "detail.team"},
                     {"type": "steps", "label": "Sequence", "from": "detail.steps"},
                     {"type": "evidence", "label": "Signals", "from": "detail.signals"},
                     {"type": "links", "label": "Deal history", "from": "detail.deals"}],
        "actions": [
            A("Research & add", "Research {title} for me: the buying team, a way in for each person with its evidence, why now, the strategy (try · use · buy · partner) and the reach-out mix — then make it researched.", "primary", stages=["lead"]),
            A("Research these {n}", "Add these leads to my pipeline and research them — the buying team, a way in for each person, and why now: {titles}.", "primary", stages=["lead"], bulk=True),
            A("Find a way in", "Find me a way in at {title} — a contact form, a public profile or someone I know.", stages=["lead", "researched"]),
            A("Start sequence", "Start the sequence that fits {title} and bring the first touch to me.", "primary", stages=["researched"]),
            A("Answer the reply", "Work the reply from {title}.", "primary", stages=["replied", "sequenced", "contacted", "meeting"], flag="needs-you"),
            A("Pause", "Pause the sequence for {title} and tell me why it is a good moment to.", stages=["sequenced", "contacted"]),
            A("Brief me", "Brief me for my call with {title}.", "primary", stages=["meeting", "trial"]),
            A("Brief me", "Brief me on {title}: where it stands, who we are talking to, and what is next.", stages=["researched", "sequenced", "contacted", "replied"]),
            A("Started a trial", "Record that {title} started a trial.", "primary", stages=["meeting"]),
            A("Reconsider", "Look at {title} again — why it was knocked out, and whether that still holds.", stages=["out"]),
        ],
    }
    doc["actions"] = [A("Find me leads", "Find me leads: run today’s sweep and show me the coverage table and the shortlist.", "primary"),
                      A("Send what’s due", "Send what's due today, within my caps, and bring anything gated to me as one batch."),
                      A("Work my replies", "Work my replies.")]
    # what the home note and the older Studio read (kept beside the schema)
    doc["summary"] = summary
    doc["today"] = today_box
    doc["coverage"] = cov
    doc["setup"] = setup
    doc["starter"] = starter
    STG.apply(doc, pathlib.Path(render_dir()) / "profile")       # the seller's labels / hidden stages
    probs = pdoc.check(doc)
    if probs:
        raise SystemExit("pipeline.json would be invalid: " + "; ".join(probs[:5]))
    return doc

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--migrate-layout", action="store_true", help="the standard layout + the ledger's stage ids (nothing deleted)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.migrate_layout:
        return migrate_layout(a.dest, a.dry_run)
    w = render(a.dest)
    print(f"rendered {w.written} files into {w.base}" + (f"; kept {len(w.kept)} you edited: {', '.join(w.kept[:5])}" if w.kept else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
