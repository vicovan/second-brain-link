#!/usr/bin/env python3
"""
render_brain.py - render the target records as the fundraising layer of a brain.

The ledger (targets.jsonl, events.jsonl) stays hidden in the state root. This turns it
into frontmattered notes that Obsidian and Second Brain Studio index, search and graph:

    Fundraising Dashboard.md      pipeline by status · Due · deadlines · tiers · recent
    Fundraising KPI.md            the two funnels' counts, conversions, rates at n >= 20 (kpi.py)
    Fundraising Lessons.md        what the agent learned (lessons.md + _memory/, inferred flagged)
    programs/<Name> (target).md   one per program / grant that is not screened out
    investors/<Name> (target).md  one per fund / angel / strategic / syndicate
    applications/<day>/<key>/<Name> application <day>.md   index of each application folder
    pipeline.json                 sbl-pipeline/2 with the two funnels + the floor (Studio's Runtime)
    Funding Plan.md               NOT written here - only its §0 ledger between <!-- ledger:begin/end -->
                                  markers is refreshed from `ledger.py table ledger` (R2)

    python3 render_brain.py --migrate-layout   # targets/ -> programs/ + investors/ through the manifest (aliases kept)

    python3 render_brain.py            # render to this surface
    python3 render_brain.py --quiet    # after every status change — the founder is watching

What it will not do:
- write profile/ (onboarding's), the Funding Plan (raise-plan's), or outreach drafts
  (raise-outreach's) — it only links them;
- delete anything: a record that disappears is reported, not removed;
- use the engine's _GENERATED.json — it keeps its own manifest beside the ledger, so
  build_vault.py --refresh treats these notes as user files and leaves them alone;
- shadow a note: a target is titled "<Name> (target)" and links to the existing
  organizations note when there is one, never a second note with the same title.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, render_dir, brain_layer  # noqa: E402
import ledger as L  # noqa: E402
import founder_profile as prof  # noqa: E402
from lint_claims import gates_ok  # noqa: E402
import pipeline_doc as pdoc  # noqa: E402
import kpi as KPIlib  # noqa: E402
import stages as STG  # noqa: E402
from ledger_base import Writer as _BaseWriter, replace_between, between  # noqa: E402
from paths import is_brain  # noqa: E402


def _threads():
    """The engagement ledger (raise-engage) — a sibling skill in Claude's packaging, the same
    folder in Codex's. Absent is fine: the dashboard just has no Threads section."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (here, os.path.join(here, "..", "..", "raise-engage", "scripts")):
        if os.path.isfile(os.path.join(cand, "threads.py")):
            if cand not in sys.path:
                sys.path.insert(0, os.path.abspath(cand))
            try:
                import threads  # noqa: E402
                return threads
            except Exception:
                return None
    return None

MANIFEST = "_FUNDRAISE_GENERATED.json"
DASHBOARD = "Fundraising Dashboard.md"
KPI = "Fundraising KPI.md"
LESSONS = "Fundraising Lessons.md"
PLAN = "Funding Plan.md"
PROGRAM_KINDS = ("program", "grant")          # the programs funnel; every other kind is an investor
FOLDER = {"programs": "programs", "investors": "investors"}


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


def funnel_of(rec):
    return "programs" if rec.get("kind") in PROGRAM_KINDS else "investors"


def note_rel(rec):
    """programs/<Name> (target).md or investors/<Name> (target).md - the standard layout."""
    return f"{FOLDER[funnel_of(rec)]}/{title_of(rec)}.md"
TODAY = datetime.date.today().isoformat()
GLYPH = {"screened": "📋", "verified": "✅", "out": "⛔", "queued": "⬜", "drafted": "✏️",
         "draft_ready": "📨", "filed": "📤", "contacted": "📬", "no_reply": "⏳",
         "replied": "💬", "meeting": "🤝", "passed": "✖️", "accepted": "🎉",
         "rejected": "✖️", "term_sheet": "📝", "withdrawn": "↩️"}
TIER_NAME = {1: "Tier 1 — dated cohort doors", 2: "Tier 2 — cold path, exact thesis",
             3: "Tier 3 — home turf", 4: "Tier 4 — warm-intro builds"}


def safe(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name or "").strip() or "untitled"


def yaml_scalar(v):
    if v is None:
        return '""'
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s.startswith("[[") or re.search(r'[:#\[\]{}&*!|>\'"%@`]', s) or s != s.strip():
        return '"' + s.replace('"', '\\"') + '"'
    return s


def frontmatter(pairs, tags):
    out = ["---"] + [f"{k}: {yaml_scalar(v)}" for k, v in pairs]
    out.append("tags: [" + ", ".join(tags) + "]")
    return "\n".join(out + ["---"]) + "\n\n"


def cell(v):
    return str(v if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")


class Writer(_BaseWriter):
    """The shared R6 writer (ledger_base.Writer): a note the founder edited is kept and the fresh
    render lands beside it as <name>.new.md; machine files are always rewritten; the manifest
    (`_FUNDRAISE_GENERATED.json`, beside the ledger) remembers what was rendered."""

    def __init__(self, root, manifest_path, quiet=False):
        super().__init__(root, manifest_path, quiet)


def title_of(rec):
    return f"{safe(rec['name'])} (target)"


_ORG_CACHE = {}


def org_note(rec):
    """The existing organizations note for this target, if the brain has one."""
    d = brain_layer("orgs")
    if d is None:
        return None
    # Match the real filename case-sensitively: macOS says "Betaworks.md" exists when the
    # note is "betaworks.md", and a link built from the wrong case does not resolve.
    want = f"{safe(rec['name'])}.md"
    global _ORG_CACHE
    if _ORG_CACHE.get("dir") != str(d):
        try:
            _ORG_CACHE = {"dir": str(d), "names": {n.lower(): n for n in os.listdir(d)}}
        except OSError:
            _ORG_CACHE = {"dir": str(d), "names": {}}
    real = _ORG_CACHE["names"].get(want.lower())
    return real[:-3] if real else None


def money(rec):
    lo, hi = L.cash_range(rec)
    if lo is None and hi is None:
        return "—"
    f = lambda x: f"{x / 1e6:g}M" if x >= 1e6 else f"{x / 1e3:g}K"  # noqa: E731
    return f"up to {f(hi)}" if lo is None else (f(lo) if lo == hi else f"{f(lo)}–{f(hi)}")


def target_note(rec, evs, exists):
    org = org_note(rec)
    fm = frontmatter([("type", "fundraising-target"), ("title", title_of(rec)),
                      ("kind", rec["kind"]), ("status", rec["status"]),
                      ("tier", rec.get("tier")), ("fit", rec.get("fit")),
                      ("url", rec.get("url") or ""),
                      ("organization", f"[[{org}]]" if org else ""),
                      ("updated", rec.get("updated"))],
                     ["fundraising", "fundraising/target", f"fundraising/{rec['kind']}",
                      f"fundraising/status/{rec['status'].replace('_', '-')}"])
    out = [fm, f"# {rec['name']}\n",
           f"{GLYPH.get(rec['status'], '')} **{rec['status'].replace('_', ' ')}** · "
           f"{rec['kind']} · tier {rec.get('tier') or '—'} · fit {rec.get('fit') or '—'}"
           + (f" · [site]({rec['url']})" if rec.get("url") else "") + "\n"]
    if org:
        out.append(f"Organization note: [[{org}]]\n")
    if rec.get("why"):
        out.append(f"**Why this one:** {rec['why']}\n")
    if rec.get("out_reason"):
        out.append(f"> [!warning] Screened out — {rec['out_reason']}\n")
    if rec.get("people"):
        out.append("## People\n")
        for p in rec["people"]:
            out.append(f"- {p.get('name')}" + (f" — {p['role']}" if p.get("role") else "")
                       + (f" — {p['why']}" if p.get("why") else ""))
        out.append("")
    out.append("## Claims\n\n| Field | Value | Stamp | Source | Checked |\n|---|---|---|---|---|")
    for f, c in sorted(rec["claims"].items()):
        v = c.get("v")
        if isinstance(v, dict):
            v = ", ".join(f"{k} {x}" for k, x in v.items())
        src = c.get("src") or ""
        src = f"[link]({src})" if str(src).startswith("http") else src
        stale = " ⏳" if f in L.stale_claims(rec) else ""
        out.append(f"| {f} | {cell(v)} | {c.get('stamp', '⚠')}{stale} | {cell(src)} | {cell(c.get('at'))} |")
    if not rec["claims"]:
        out.append("| — | nothing verified yet | 📋 | — | — |")
    out.append("\n## Filter verdicts\n\n| Filter | Verdict | Why |\n|---|---|---|")
    for f, v in rec.get("verdicts", {}).items():
        out.append(f"| {f} | {v.get('v')} | {cell(v.get('why'))} |")
    if rec.get("origin_text"):
        out.append("\n## What the lists said (unverified)\n")
        out += [f"- {t}" for t in rec["origin_text"]]
        out.append(f"\n_Sources: {', '.join(rec.get('origin') or [])}_")
    if rec.get("apps") or rec.get("drafts"):
        out.append("\n## Work\n")
        for a in rec.get("apps") or []:
            day = a.split("/")[1] if a.count("/") >= 2 else ""
            t = f"{safe(rec['name'])} application {day}"
            out.append(f"- Application: [[{t}]]" if t in exists else f"- Application folder: `{a}`")
        for d in rec.get("drafts") or []:
            stem = pathlib.Path(d.get("path", "")).stem
            link = f"[[{stem}]]" if stem in exists else f"`{d.get('path')}`"
            gm = " · Gmail draft ✓" if d.get("gmail_draft_id") else ""
            out.append(f"- {d.get('channel', 'email')} draft ({d.get('at')}): {link}{gm}")
    if rec.get("next"):
        out.append(f"\n**Next:** {rec['next'].get('action')} — due {rec['next'].get('due')}")
    if evs:
        out.append("\n## History\n")
        out += [f"- {e['at'][:10]} · {e.get('from') or '∅'} → {e['to']} ({e['by']})"
                + (f" — {e['note']}" if e.get("note") else "") for e in evs[-15:]]
    return "\n".join(out) + "\n"


def app_note(rec, rel, folder):
    day = rel.split("/")[1]
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.endswith(" application " + day + ".md")) \
        if folder.is_dir() else []
    gates = {}
    try:
        gates = json.loads((folder / "gates.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    state = "no lint yet" if not gates else ("green" if gates.get("ok") else "RED — stopped")
    fm = frontmatter([("type", "fundraising-application"),
                      ("title", f"{safe(rec['name'])} application {day}"),
                      ("target", f"[[{title_of(rec)}]]"), ("status", rec["status"]),
                      ("date", day), ("gates", state)],
                     ["fundraising", "fundraising/application"])
    out = [fm, f"# {rec['name']} — application {day}\n",
           f"Target: [[{title_of(rec)}]] · status **{rec['status']}** · gates **{state}**\n",
           "## Files in this folder\n"]
    out += [f"- `{f}`" for f in files] or ["- (empty — drafting in progress)"]
    for r in gates.get("red", []):
        out.append(f"\n> [!warning] {r}")
    return "\n".join(out) + "\n"


def scan_packages(dest, by_key):
    """[{key, name, day, dir, rel, ok, why, score, band, verdict, mailto, to}] — newest first."""
    out = []
    base = pathlib.Path(dest) / "outreach"
    if not base.is_dir():
        return out
    for d in sorted(base.glob("*/*"), key=lambda p: (p.parent.name, p.name), reverse=True):
        if not d.is_dir() or d.name not in by_key:
            continue
        ok, why = gates_ok(d)
        fit = prof.frontmatter((d / "fit.md").read_text(encoding="utf-8")) if (d / "fit.md").is_file() else {}
        em = prof.frontmatter((d / "email.md").read_text(encoding="utf-8")) if (d / "email.md").is_file() else {}
        try:
            g = json.loads((d / "gates.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            g = {}
        out.append({"key": d.name, "name": by_key[d.name]["name"], "day": d.parent.name, "dir": d,
                    "rel": f"outreach/{d.parent.name}/{d.name}", "ok": ok, "why": why,
                    "score": fit.get("score"), "band": fit.get("band"),
                    "verdict": (g.get("review") or {}).get("verdict"),
                    "flag": (g.get("review") or {}).get("flag"),
                    "mailto": str(em.get("mailto") or ""), "to": str(em.get("to") or "")})
    return out


def package_note(rec, pk):
    files = sorted(p.name for p in pk["dir"].iterdir()
                   if p.is_file() and " package " not in p.name) if pk["dir"].is_dir() else []
    state = "PASS" if pk["ok"] else "not ready — " + pk["why"]
    fm = frontmatter([("type", "fundraising-package"), ("title", f"{safe(rec['name'])} package {pk['day']}"),
                      ("target", f"[[{title_of(rec)}]]"), ("status", rec["status"]), ("date", pk["day"]),
                      ("fit", pk["score"]), ("review", pk["verdict"] or ""), ("gates", "PASS" if pk["ok"] else "FAIL")],
                     ["fundraising", "fundraising/package"])
    out = [fm, f"# {rec['name']} — package {pk['day']}\n",
           f"Target: [[{title_of(rec)}]] · status **{rec['status'].replace('_', ' ')}** · fit **{pk['score'] or '—'}**"
           f" ({pk['band'] or 'not scored'}) · review **{pk['verdict'] or 'not run'}**"
           + (" ⚑ flagged" if pk.get("flag") else "") + f" · gates **{state}**\n"]
    if pk["ok"] and pk["mailto"]:
        ask = "sbl-ask:" + L_quote(f"I sent the {rec['name']} email")
        out.append(f"[✉ Open in Mail — pre-filled]({pk['mailto']})   ·   [✓ I sent it]({ask})\n")
        out.append("Opens a new message in your own mail app — **nothing is sent until you press Send**.\n")
    elif pk["ok"]:
        out.append("Ready — no email address; send through the fund's own path (see `email.md`).\n")
    out.append("## Files in this package\n")
    out += [f"- `{f}`" for f in files] or ["- (empty — being prepared)"]
    return "\n".join(out) + "\n"


def L_quote(s):
    from urllib.parse import quote
    return quote(s, safe="")


def dashboard(recs, known, packages=()):
    live = [r for r in recs if r["status"] != "out"]
    counts = {}
    for r in recs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    plan_exists = (render_dir() / PLAN).is_file()
    fm = frontmatter([("type", "fundraising-dashboard"), ("title", "Fundraising Dashboard"),
                      ("updated", TODAY), ("targets", len(recs))],
                     ["fundraising", "dashboard"])
    today_note = f"Raise today {TODAY}"
    out = [fm, "# Fundraising Dashboard\n",
           (f"Today: [[{today_note}]] · " if (render_dir() / "reports" / f"{today_note}.md").is_file() else "")
           + (f"The plan: [[Funding Plan]] · " if plan_exists else "No plan yet — ask the agent to build one · ")
           + "[[Fundraising KPI]] · [[Fundraising Lessons]] · [[Memory — Fundraising Agent]] (what the agent remembers; [[Review]] for its inferences)\n",
           "## Pipeline\n", "| Status | Count |\n|---|---|"]
    for s in L.STATUSES:
        if counts.get(s):
            out.append(f"| {GLYPH.get(s, '')} {s.replace('_', ' ')} | {counts[s]} |")
    ready = [p for p in packages if p["ok"]]
    waiting = [p for p in packages if not p["ok"]]
    out.append("\n## Ready to send\n")
    if ready:
        out.append("Each button opens a **new message in your mail app**, pre-filled — you press Send. "
                   "Then tell the agent, or press ✓ in the package note.\n")
        out.append("| Target | Fit | Review | Package | Mail |\n|---|---|---|---|---|")
        for p in ready:
            r = next(x for x in recs if x["key"] == p["key"])
            mail = f"[✉ Open in Mail]({p['mailto']})" if p["mailto"] else "form / no address"
            out.append(f"| [[{title_of(r)}]] | {p['score'] or '—'} | {p['verdict'] or '—'}"
                       + (" ⚑" if p.get("flag") else "") + f" | [[{safe(r['name'])} package {p['day']}]] | {mail} |")
    else:
        out.append("Nothing has passed its gates yet.")
    if waiting:
        out.append(f"\n### Being prepared ({len(waiting)})\n\n| Target | Fit | What it is waiting on |\n|---|---|---|")
        for p in waiting:
            r = next(x for x in recs if x["key"] == p["key"])
            out.append(f"| [[{title_of(r)}]] | {p['score'] or '—'} | {cell(p['why'])[:120]} |")
    T = _threads()
    if T is not None:
        trs = list(T.load().values())
        todo = [t for t in trs if t["status"] == "drafted"]
        if trs:
            out.append(f"\n## Threads to comment on\n")
            if todo:
                out.append("Open the thread, paste the comment, post it yourself — then press ✓ in the note.\n")
                out.append("| Thread | Fit | Comment | Open |\n|---|---|---|---|")
                for t in sorted(todo, key=lambda t: (-(t.get("fit") or 0), t["id"])):
                    note = pathlib.Path(t["note"]).stem if t.get("note") else ""
                    out.append(f"| {cell(T.note_title(t))[:80]} | {t.get('fit') or '—'} | "
                               + (f"[[{note}]]" if note else "—") + f" | [↗ thread]({t['url']}) |")
            else:
                out.append("No unposted comments.")
            posted = sum(1 for t in trs if t["status"] == "posted")
            out.append(f"\n{posted} posted · {sum(1 for t in trs if t['status'] == 'found')} found, not drafted · "
                       f"{sum(1 for t in trs if t['status'] == 'skipped')} skipped")
    due = L.due_items(14)
    out.append("\n## Due\n")
    if due:
        out.append("| When | What | Target |\n|---|---|---|")
        for d in due:
            when = "today" if d["days"] <= 0 else f"in {d['days']}d ({d['due']})"
            what = d["type"] + ("" if d.get("year_confirmed", True) else " ⚠ year unconfirmed")
            t = next((r for r in recs if r["key"] == d["key"]), None)
            out.append(f"| {when} | {what} | [[{title_of(t)}]] |" if t and title_of(t) in known
                       else f"| {when} | {what} | {cell(d['name'])} |")
    else:
        out.append("Nothing due in the next 14 days.")
    for tier in (1, 2, 3, 4):
        rows = sorted([r for r in live if r.get("tier") == tier],
                      key=lambda r: (-(r.get("fit") or 0), r["name"]))
        if not rows:
            continue
        out.append(f"\n## {TIER_NAME[tier]}\n\n| Target | Status | Fit | Cheque | Why |\n|---|---|---|---|---|")
        for r in rows:
            out.append(f"| [[{title_of(r)}]] | {GLYPH.get(r['status'], '')} {r['status']} | "
                       f"{r.get('fit') or '—'} | {money(r)} | {cell(r.get('why'))[:120]} |")
    untiered = [r for r in live if not r.get("tier")]
    if untiered:
        out.append(f"\n## Not yet tiered ({len(untiered)})\n\n| Target | Status | Stamp | From |\n|---|---|---|---|")
        for r in sorted(untiered, key=lambda r: r["name"].lower())[:200]:
            best = max((L.STAMPS.get(c.get("stamp"), 0) for c in r["claims"].values()), default=1)
            stamp = {3: "✅", 2: "3P", 1: "📋", 0: "⚠"}[best]
            out.append(f"| [[{title_of(r)}]] | {r['status']} | {stamp} | {cell(', '.join(r.get('origin') or []))} |")
    outs = [r for r in recs if r["status"] == "out"]
    if outs:
        out.append(f"\n## Screened out ({len(outs)})\n\n| Target | Filter that removed it |\n|---|---|")
        for r in sorted(outs, key=lambda r: (r.get("out_reason") or "", r["name"])):
            out.append(f"| {cell(r['name'])} | {cell(r.get('out_reason'))} |")
    evs = L.events()[-12:]
    if evs:
        out.append("\n## Recent\n")
        out += [f"- {e['at'][:16].replace('T', ' ')} · {e['key']} · {e.get('from') or '∅'} → {e['to']} ({e['by']})"
                for e in reversed(evs)]
    return "\n".join(out) + "\n"


def kpi_note(doc, evs):
    """`Fundraising KPI.md` from the shared kpi.py over the two funnels (R2: numbers from scripts)."""
    k = KPIlib.compute(doc, evs, today=TODAY, signals=["origin", "kind", "tier", "channel", "angle"])
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        L.cmd_kpi(None)
    old = json.loads(buf.getvalue() or "{}")
    extra = [f"## Touched", "", f"**{old.get('touched', 0)}** targets contacted or applied to · replied **{old.get('replied', '0/0')}** · "
             f"meetings **{old.get('meetings', '0/0')}** · accepted **{old.get('accepted', 0)}** · term sheets **{old.get('term_sheets', 0)}**"]
    return KPIlib.markdown(k, "Fundraising", title="Fundraising KPI", extra="\n".join(extra), tags=["fundraising"])


def lessons_note():
    """The readable mirror of what the agent learned: lessons.md (ledger.py add-lesson) + _memory/."""
    body = []
    lessons = state_root() / "lessons.md"
    if lessons.is_file():
        body += ["## Lessons recorded", "", lessons.read_text(encoding="utf-8").strip(), ""]
    try:
        import memory as M  # noqa: PLC0415
        root = state_root()
        brain = str(root.parent.parent) if root.parent.name == ".plugins" else None
        items = M.recall("fundraising", None, 4000, stamp=False, brain=brain)
        if items:
            body += ["## What the agent remembers (inferred items are flagged)", ""] + ["- " + M.recall_line(it) for it in items] + [""]
    except Exception:  # noqa: BLE001
        pass
    fm = frontmatter([("type", "synthesis"), ("title", "Fundraising Lessons"), ("updated", TODAY)], ["fundraising", "lessons"])
    return fm + "# Fundraising Lessons\n\n> What outcomes taught this agent. Edit or remove any inferred item in Studio's Memory manager.\n\n" \
        + ("\n".join(body) if body else "_Nothing learned yet._\n") + "\nBack to [[Fundraising Dashboard]]\n"


def refresh_plan_ledger(dest):
    """The Funding Plan's §0 table between <!-- ledger:begin --> / <!-- ledger:end --> markers is
    script-rendered (`ledger.py table ledger`); the rest of the plan is the model's and never touched."""
    plan = pathlib.Path(dest) / PLAN
    if not plan.is_file():
        return False
    txt = plan.read_text(encoding="utf-8")
    if between(txt, "ledger") is None:
        return False
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        L.cmd_table(type("A", (), {"which": "ledger", "kind": None})())
    new = replace_between(txt, "ledger", buf.getvalue().rstrip("\n"))
    if new != txt:
        tmp = plan.with_name(plan.name + ".tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, plan)
    return True


def render(dest=None, quiet=False):
    dest = pathlib.Path(dest) if dest else render_dir()
    recs = list(L.load().values())
    evs = L.events()
    mdir = state_root()
    mdir.mkdir(parents=True, exist_ok=True)
    w = Writer(dest, mdir / MANIFEST, quiet)
    live = [r for r in recs if r["status"] != "out"]
    known = {title_of(r) for r in live}
    existing_stems = {p.stem for p in dest.rglob("*.md")} if dest.is_dir() else set()
    app_titles = set()
    for r in live:
        for rel in r.get("apps") or []:
            folder = dest / rel
            if folder.is_dir():
                day = rel.split("/")[1]
                t = f"{safe(r['name'])} application {day}"
                w.text(f"{rel}/{t}.md", app_note(r, rel, folder))
                app_titles.add(t)
    by_key = {r["key"]: r for r in live}
    packages = scan_packages(dest, by_key)
    for pk in packages:
        t = f"{safe(by_key[pk['key']]['name'])} package {pk['day']}"
        w.text(f"{pk['rel']}/{t}.md", package_note(by_key[pk["key"]], pk))
        app_titles.add(t)
    exists = existing_stems | app_titles
    for r in live:
        w.text(note_rel(r), target_note(r, [e for e in evs if e["key"] == r["key"]], exists))
    w.text(DASHBOARD, dashboard(recs, known, packages))
    doc = write_pipeline(w, dest, recs, evs, exists)
    if doc:
        w.text(KPI, kpi_note(doc, evs))
    w.text(LESSONS, lessons_note())
    refresh_plan_ledger(dest)

    gone = w.finish({"dest": str(dest)})
    if not quiet:
        print(f"\n{w.wrote} written · {w.same} unchanged · {len(w.kept)} kept (yours) · {len(live)} targets rendered "
              f"({len(recs) - len(live)} screened out, listed on the dashboard) -> {dest}",
              file=sys.stderr)
        if w.kept:
            print("kept as you edited them (fresh render beside as .new.md): " + ", ".join(w.kept[:5]), file=sys.stderr)
        if gone:
            print(f"{len(gone)} note(s) no longer rendered, left in place: "
                  + ", ".join(gone[:5]), file=sys.stderr)
    return w



# ---------------------------------------------------------------- the Pipeline canvas
# Studio's Pipeline canvas draws every agent's pipeline.json (schema sbl-pipeline/2, built and
# checked by pipeline_doc.py). Fundraising's: every target - fund, program, angel - as one item,
# in the ledger's own statuses, with its stamped claims, people, applications and drafts.
FR_LABEL = {"screened": "Screened", "verified": "Verified", "queued": "Queued", "drafted": "Drafted",
            "draft_ready": "Draft ready", "filed": "Filed", "contacted": "Contacted", "no_reply": "No reply",
            "replied": "Replied", "meeting": "Meeting", "term_sheet": "Term sheet", "accepted": "Accepted",
            "passed": "Passed", "rejected": "Rejected", "out": "Screened out", "withdrawn": "Withdrawn"}
FR_ROLE = {"term_sheet": "positive", "accepted": "positive", "passed": "negative", "rejected": "negative",
           "out": "parked", "withdrawn": "parked"}
FR_PROMPT = {
    "verified": "Verify {title} on its own site and stamp every claim.",
    "queued": "Queue {title} for this week.",
    "drafted": "Draft the application or email for {title}.",
    "draft_ready": "Finish the {title} draft so it is ready for me to send.",
    "filed": "File my application to {title}.",
    "no_reply": "Mark {title} as no reply yet.",
    "replied": "Record that {title} replied.",
    "meeting": "Record that {title} gave me a meeting.",
    "term_sheet": "Record a term sheet from {title}.",
    "accepted": "Record that {title} accepted me.",
    "passed": "Record that {title} passed.",
    "rejected": "Record that {title} rejected the application.",
    "withdrawn": "Withdraw {title}.",
    "screened": "Re-screen {title} against my filter chain.",
    "out": "Screen {title} out.",
}


def write_pipeline(w, dest, recs, evs, exists):
    S, A = pdoc.stage, pdoc.action
    dest = pathlib.Path(dest)
    pre = dest.name + "/" if is_brain(dest.parent) else ""
    doc = pdoc.new("fundraising", "Fundraising", "#0f9d74")
    # the two funnels (programs · investors) are the contract's: fixed IDs, roles, gates; the labels
    # per funnel ("Found", "Angle") come from there too; `next` from the ledger's own table
    c = contract()
    funnels = []
    for f in c.get("funnels") or []:
        ids = {x["id"] for x in f["stages"]}
        stages = []
        for x in f["stages"]:
            sid = x["id"]
            nxt = sorted(y for y in L.TRANSITIONS.get(sid, set()) if y != sid and y in ids)
            stages.append(S(sid, x.get("label") or FR_LABEL.get(sid, sid), x.get("role", "open"), next=nxt, gate=x.get("gate", "none"),
                            move_prompt=FR_PROMPT.get(sid, "Move {title} to {stage_label}."), collapsed=bool(x.get("collapsed"))))
        funnels.append(pdoc.funnel(f["id"], f["label"], f["item"], f["success"], stages, f.get("success2")))
    doc["funnels"] = funnels
    doc["floor"] = [pdoc.floor_group(g["id"], g["label"], g["stages"], g.get("funnel")) for g in (c.get("floor") or [])]
    known_stage = {f["id"]: {x["id"] for x in f["stages"]} for f in funnels}
    last_ev = {}
    for e in evs:
        last_ev[e["key"]] = e.get("at")
    items = []
    today = datetime.date.today()
    for r in sorted(recs, key=lambda x: x["name"].lower()):
        st = r["status"] if r["status"] in FR_LABEL else "screened"
        dl, yc = L.deadline_of(r)
        dl_days = (dl - today).days if dl else None
        stale = L.stale_claims(r)
        flags, needs = [], ""
        if st == "draft_ready":
            flags, needs = ["needs-you"], "A draft is ready — send it yourself, then say “I sent it”"
        elif dl_days is not None and 0 <= dl_days <= 7 and st in ("queued", "drafted", "verified"):
            flags, needs = ["needs-you"], f"Deadline in {dl_days} day{'s' if dl_days != 1 else ''}" + ("" if yc else " (year not confirmed)")
        elif r.get("next") and str(r["next"].get("due") or "")[:10] <= today.isoformat() and st not in ("out", "withdrawn", "passed", "rejected"):
            flags, needs = ["needs-you"], f"Due: {r['next'].get('action')}"
        if stale and st not in ("out", "withdrawn"):
            flags.append("stale")
        title = title_of(r)
        fid = funnel_of(r)
        if st not in known_stage.get(fid, {st}):
            st = "screened"
        attrs = {"kind": r.get("kind") or "", "tier": f"Tier {r['tier']}" if r.get("tier") else "untiered",
                 "deadline_days": dl_days if dl_days is not None else None, "stale": len(stale),
                 "origin": (r.get("origin") or [""])[0], "channel": (r["drafts"][-1].get("channel") if r.get("drafts") else ("form" if r.get("apps") else "")),
                 "angle": r.get("angle") or "", "day": str(r.get("created") or "")[:10]}
        sub = " · ".join(x for x in (r.get("kind") or "", f"tier {r['tier']}" if r.get("tier") else "",
                                     f"deadline {dl.isoformat()}" if dl else "") if x)
        it = pdoc.item(r["key"], r["name"], st, funnel=fid, sub=sub or None, score=r.get("fit"), flags=flags or None, needs=needs or None,
                       why=r.get("out_reason") or r.get("why") or None, url=r.get("url") or None,
                       note=(pre + note_rel(r)) if st != "out" else None,
                       attrs={k: v for k, v in attrs.items() if v is not None},
                       next={"label": r["next"].get("action"), "due": r["next"].get("due")} if r.get("next") else None,
                       stage_since=str(last_ev.get(r["key"]) or r.get("updated") or "")[:10] or None,
                       updated=r.get("updated"))
        if FR_ROLE.get(st) not in ("parked", "negative"):
            claims = []
            for f, c in sorted((r.get("claims") or {}).items()):
                v = c.get("v")
                if isinstance(v, dict):
                    v = ", ".join(f"{k} {x}" for k, x in v.items())
                claims.append({"label": f"{f}: {v}", "stamp": (c.get("stamp") or "⚠") + (" ⏳" if f in stale else ""),
                               "url": c.get("src") if str(c.get("src") or "").startswith("http") else "", "seen": (c.get("at") or "")[:10]})
            people = [{"name": p.get("name"), "role": p.get("role") or "", "evidence": p.get("why") or ""} for p in (r.get("people") or []) if p.get("name")]
            work = []
            for a in r.get("apps") or []:
                day = a.split("/")[1] if a.count("/") >= 2 else ""
                t = f"{safe(r['name'])} application {day}"
                if t in exists:
                    work.append({"label": "Application " + day, "note": pre + f"{a}/{t}.md"})
            for d in r.get("drafts") or []:
                stem = pathlib.Path(d.get("path", "")).stem
                if stem in exists and d.get("path"):
                    # a draft's path may already be brain-relative ("46-fundraising/outreach/…"):
                    # never prefix the layer twice
                    dp = str(d["path"])
                    work.append({"label": f"{d.get('channel', 'email')} draft {str(d.get('at') or '')[:10]}",
                                 "note": dp if (pre and dp.startswith(pre)) else pre + dp})
            hist = [{"label": f"{e.get('from') or '∅'} → {e['to']}", "status": "done", "date": str(e.get("at") or "")[:10]}
                    for e in evs if e["key"] == r["key"]][-8:]
            it["detail"] = {"claims": claims, "people": people, "work": work, "history": hist}
        items.append(it)
    doc["items"] = items
    count = lambda *xs: sum(1 for r in recs if r["status"] in xs)  # noqa: E731
    reached = count("filed", "contacted", "no_reply", "replied", "meeting", "term_sheet", "accepted", "passed", "rejected")
    meetings = count("meeting", "term_sheet", "accepted")
    doc["headline"] = {"label": "meetings", "value": meetings, "n": reached, "period": "all time"}
    doc["throughput"] = pdoc.throughput((c.get("throughput") or {}).get("label") or "filed + drafted / day",
                                        [e.get("at") for e in evs if e.get("to") in ("filed", "drafted", "draft_ready")], TODAY)
    doc["stats"] = [{"label": "replies or better / reached", "num": count("replied", "meeting", "term_sheet", "accepted"), "den": reached, "min_n": 20},
                    {"label": "meetings / reached", "num": meetings, "den": reached, "min_n": 20}]
    doc["lenses"] = [pdoc.lens("fit", "Fit", "score", domain=[40, 100]),
                     pdoc.lens("deadline", "Days to deadline", "attrs.deadline_days", domain=[0, 60]),
                     pdoc.lens("age", "Age", "stage_since", scale="days", buckets=[3, 7, 14, 30]),
                     pdoc.lens("needs", "Needs you", "flags", scale="flag", value="needs-you"),
                     pdoc.lens("today", "New today", "attrs.day", scale="flag", value=TODAY)]
    doc["facets"] = [pdoc.facet("kind", "Kind", "attrs.kind"), pdoc.facet("tier", "Tier", "attrs.tier"),
                     pdoc.facet("origin", "Origin", "attrs.origin"), pdoc.facet("channel", "Channel", "attrs.channel")]
    doc["panel"] = {
        "top": ["{attrs.kind}", "{stage_label}", "{attrs.tier}", "fit {score}"],
        "sections": [{"type": "text", "label": "Why this one", "from": "why"},
                     {"type": "evidence", "label": "Claims (✅ own site · 3P · 📋 desk · ⚠ unverified)", "from": "detail.claims"},
                     {"type": "people", "label": "People", "from": "detail.people"},
                     {"type": "links", "label": "Applications and drafts", "from": "detail.work"},
                     {"type": "steps", "label": "History", "from": "detail.history"}],
        "actions": [
            A("Verify on its own site", "Verify {title} on its own site and stamp every claim.", "primary", stages=["screened"]),
            A("Apply", "Apply to {title}: find the real form, draft every answer from my profile, lint it, fill it and finish the way my autonomy setting says.", "primary", stages=["queued", "verified"]),
            A("Draft the email", "Draft the email to {title} as a package — brief, fit, draft, lint, review. Drafts only; I send.", stages=["queued", "verified"]),
            A("I sent it", "I sent the {title} email.", "primary", stages=["draft_ready"]),
            A("Draft the follow-up", "Draft the follow-up to {title}.", "primary", stages=["contacted", "no_reply", "filed"]),
            A("Record a reply", "I heard back from {title} — I will paste it or tell you what happened.", stages=["contacted", "no_reply", "filed", "replied"]),
            A("Prep me", "Prep me for my meeting with {title} from the target note and my stories.", "primary", stages=["meeting"]),
            A("Re-verify stale claims", "Re-verify the stale claims on {title}.", stages=["verified", "queued", "drafted"], flag="stale"),
            A("Re-queue", "Re-queue {title} — ask me what changed first.", stages=["passed", "rejected", "withdrawn"]),
            A("Screen these {n}", "Verify these {n} targets on their own sites and tier them: {titles}.", "primary", stages=["screened"], bulk=True),
        ],
    }
    doc["actions"] = [A("Run today's raise", "Run today's raise: new programs and investors, screened, applied and drafted within my level, and what's due.", "primary"),
                      A("Build my funding plan", "Build my funding plan: screen every target, verify the survivors, write the dated plan."),
                      A("What's due?", "What's due? Follow-ups, deadlines in the next two weeks, claims to re-verify.")]
    doc["generated"] = max([str(r.get("updated") or "") for r in recs] + [""])
    STG.apply(doc, dest / "profile")          # the founder's labels / hidden stages (profile/stages.json)
    probs = pdoc.check(doc)
    if probs:
        print("  ! pipeline.json not written: " + "; ".join(probs[:3]), file=sys.stderr)
        return None
    w.text("pipeline.json", pdoc.dumps(doc), machine=True)
    return doc

def migrate_layout(dest=None, dry_run=False):
    """targets/<Name> (target).md -> programs/ or investors/ by kind, THROUGH the manifest: a note
    still matching its rendered sha moves and gets `aliases: [<old title>]`; one the founder edited
    stays where it is and is listed. Nothing is deleted; the old folder stays until empty."""
    dest = pathlib.Path(dest) if dest else render_dir()
    recs = L.load()
    moves = []
    for r in recs.values():
        old = f"targets/{title_of(r)}.md"
        if (dest / old).is_file():
            moves.append((old, note_rel(r), title_of(r)))
    w = Writer(dest, state_root() / MANIFEST, quiet=True)
    rep_ = w.migrate_layout(moves, dry_run=dry_run)
    for a_, b_ in rep_["moved"]:
        print(f"{'would move' if dry_run else 'move'}  {a_} -> {b_}", file=sys.stderr)
    for left in rep_["left"]:
        print(f"LEFT (edited by you): {left}", file=sys.stderr)
    for a_, b_, why in rep_["skipped"]:
        print(f"SKIPPED {a_} -> {b_} ({why})", file=sys.stderr)
    print(f"{len(rep_['moved'])} moved, {len(rep_['left'])} left, {len(rep_['skipped'])} skipped. Nothing was deleted.", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--migrate-layout", action="store_true", help="targets/ -> programs/ + investors/ (aliases kept)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.migrate_layout:
        return migrate_layout(a.dest, a.dry_run)
    render(a.dest, a.quiet)


if __name__ == "__main__":
    main()
