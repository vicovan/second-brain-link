#!/usr/bin/env python3
"""
render_sales.py - write the sales layer of the brain from the ledger. No network, no model.

    render_sales.py [--dest DIR]

Writes, under <sales layer>/ (resolved per subject - never a hardcoded folder):

    Pipeline.md              the home note: needs you · due today · booked · sent this week ·
                             replies waiting · this week by origin · blocked, and why
    pipeline.json            sbl-pipeline/1 - what Studio's Pipeline canvas draws (cards per
                             stage, today's caps, the lead shortlist, the coverage table)
    accounts/<Name>.md       one note per worked account: why, the buying team with evidence,
                             each contact's sequence timeline, signals, the last events
    leads/Leads <date>.md    the day's lead report: the one-line sweep summary, the coverage
                             table, the shortlist, knock-outs and unreachable leads with reasons

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
from paths import render_dir, surface_root, is_brain, layer  # noqa: E402

BOARD = ("target", "sequenced", "replied", "meeting", "opportunity", "won", "lost")
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


class Writer:
    def __init__(self, base):
        self.base = pathlib.Path(base)
        self.mf_path = ledger.root() / MANIFEST
        try:
            self.mf = json.loads(self.mf_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.mf = {}
        self.kept, self.written = [], 0

    def put(self, rel, text):
        p = self.base / rel
        if p.exists():
            cur = p.read_text(encoding="utf-8", errors="replace")
            if cur == text:
                return
            # pipeline.json is machine data for the board: always rewritten. A NOTE is the user's
            # once they touch it - an edited or foreign note is never overwritten.
            if rel.endswith(".md") and ((rel in self.mf and sha(cur) != self.mf[rel]) or rel not in self.mf):
                self.kept.append(rel)
                return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self.mf[rel] = sha(text)
        self.written += 1

    def close(self):
        self.mf_path.write_text(json.dumps(self.mf, indent=2, sort_keys=True), encoding="utf-8")


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
            L.append(f"| {e['ts'][:16].replace('T', ' ')} | {e['kind']} | {esc(e.get('contact'))} | {esc(det)} |")
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
        w.put(f"leads/Leads {st['merged_at']}.md", "\n".join(L).rstrip() + "\n")
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
    H = [fm({"type": "sales-pipeline", "title": "Pipeline", "tags": ["sales-pipeline"], "updated": stamp[:10],
             "level": snd.get("level")}), "", "# Pipeline", "",
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
        H += [f"## Today's leads ({len(leads)})", "", f"[[leads/Leads {st.get('merged_at')}|Open the lead report]] — "
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
    w.put("Pipeline.md", "\n".join(H).rstrip() + "\n")
    w.close()
    return w



ORIGIN_GLYPH = {"revival": "◆", "warm": "●", "dormant": "●", "intro": "◇", "cold": "○"}


def pipeline_v2(acc, by_acc, cards, sl, st, cov, stamp, setup, starter, summary, today_box, pre, today, snd):
    """The Sales Agent's pipeline file, schema sbl-pipeline/2 (pipeline_doc.py) - every account in
    the registry as one item, so the Pipeline canvas shows the whole funnel at any size."""
    S, A = pdoc.stage, pdoc.action
    doc = pdoc.new("sales", "Sales", "#d9480f")
    doc["generated"] = stamp
    doc["stages"] = [
        S("lead", "Lead", next=["target", "parked"]),
        S("target", "Target", next=["sequenced", "parked", "lost"],
          move_prompt="Research {title} for me — the buying team and a way in for each person — and make it a target."),
        S("sequenced", "Sequenced", next=["replied", "meeting", "parked", "lost"],
          move_prompt="Start the sequence that fits {title} and bring the first touch to me."),
        S("replied", "Replied", next=["meeting", "opportunity", "parked", "lost"]),
        S("meeting", "Meeting", next=["opportunity", "won", "lost"]),
        S("opportunity", "Opportunity", next=["won", "lost"]),
        S("won", "Won", "positive", gate="reason", move_prompt="Mark {title} as won."),
        S("lost", "Lost", "negative", next=["target"], gate="reason", move_prompt="Mark {title} as lost."),
        S("parked", "Parked", "parked", next=["target"], move_prompt="Park {title} for now."),
        S("out", "Knocked out", "parked"),
    ]
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
        worked = stage not in ("lead", "out", "parked", "lost") or a["key"] in shortlisted
        noted = stage != "lead" or a["key"] in shortlisted
        attrs = {"origin": a.get("origin") or "cold", "reach": a.get("reach") or "",
                 "market": (a.get("markets") or [""])[0], "segment": a.get("segment") or "",
                 "warmth": int(round(100 * float(a.get("warmth") or 0)))}
        sub = " · ".join(x for x in (", ".join(a.get("markets") or []), a.get("segment") or "") if x)
        it = pdoc.item(a["key"], a["name"], stage, sub=sub, score=a.get("score"), flags=flags or None,
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
    doc["headline"] = {"label": "meetings booked", "value": meetings, "n": sent, "period": "all time"}
    doc["stats"] = [{"label": "replies / sends", "num": replies, "den": sent, "min_n": 20},
                    {"label": "meetings / sends", "num": meetings, "den": sent, "min_n": 20}]
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
                     pdoc.lens("age", "Age in stage", "stage_since", scale="days", buckets=[3, 7, 14, 30]),
                     pdoc.lens("needs", "Needs you", "flags", scale="flag", value="needs-you")]
    doc["facets"] = [pdoc.facet("origin", "Origin", "attrs.origin", {k: {"label": k, "glyph": g} for k, g in ORIGIN_GLYPH.items()}),
                     pdoc.facet("reach", "Way in", "attrs.reach"),
                     pdoc.facet("market", "Market", "attrs.market"),
                     pdoc.facet("segment", "Segment", "attrs.segment")]
    doc["panel"] = {
        "top": ["{attrs.origin}", "{stage_label}", "score {score}", "{attrs.market}"],
        "sections": [{"type": "text", "label": "Why now", "from": "why"},
                     {"type": "people", "label": "Buying team", "from": "detail.team"},
                     {"type": "steps", "label": "Sequence", "from": "detail.steps"},
                     {"type": "evidence", "label": "Signals", "from": "detail.signals"},
                     {"type": "links", "label": "Deal history", "from": "detail.deals"}],
        "actions": [
            A("Research & add", "Research {title} for me: the buying team, a way in for each person with its evidence, and why now — then make it a target.", "primary", stages=["lead"]),
            A("Research these {n}", "Add these leads to my pipeline and research them — the buying team, a way in for each person, and why now: {titles}.", "primary", stages=["lead"], bulk=True),
            A("Find a way in", "Find me a way in at {title} — a contact form, a public profile or someone I know.", stages=["lead", "target"]),
            A("Start sequence", "Start the sequence that fits {title} and bring the first touch to me.", "primary", stages=["target"]),
            A("Answer the reply", "Work the reply from {title}.", "primary", stages=["replied", "sequenced", "meeting"], flag="needs-you"),
            A("Pause", "Pause the sequence for {title} and tell me why it is a good moment to.", stages=["sequenced"]),
            A("Brief me", "Brief me for my call with {title}.", "primary", stages=["meeting", "opportunity"]),
            A("Brief me", "Brief me on {title}: where it stands, who we are talking to, and what is next.", stages=["target", "sequenced", "replied"]),
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
    probs = pdoc.check(doc)
    if probs:
        raise SystemExit("pipeline.json would be invalid: " + "; ".join(probs[:5]))
    return doc

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest")
    a = ap.parse_args(argv)
    w = render(a.dest)
    print(f"rendered {w.written} files into {w.base}" + (f"; kept {len(w.kept)} you edited: {', '.join(w.kept[:5])}" if w.kept else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
