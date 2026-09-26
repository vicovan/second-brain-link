#!/usr/bin/env python3
"""
render_brain.py - render the target records as the fundraising layer of a brain.

The ledger (targets.jsonl, events.jsonl) stays hidden in the state root. This turns it
into frontmattered notes that Obsidian and Second Brain Studio index, search and graph:

    Fundraising Dashboard.md      pipeline by status · Due · deadlines · tiers · recent
    Fundraising KPI.md            reply / meeting rates by tier, kind, channel
    targets/<Name> (target).md    one per record that is not screened out
    applications/<day>/<key>/<Name> application <day>.md   index of each application folder

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

MANIFEST = "_FUNDRAISE_GENERATED.json"
DASHBOARD = "Fundraising Dashboard.md"
KPI = "Fundraising KPI.md"
PLAN = "Funding Plan.md"
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


class Writer:
    """Writes only what changed, and remembers what it wrote."""

    def __init__(self, root, quiet=False):
        self.root, self.quiet, self.man, self.wrote, self.same = pathlib.Path(root), quiet, {}, 0, 0

    def text(self, rel, body):
        p = self.root / rel
        self.man[str(rel)] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        try:
            if p.is_file() and p.read_text(encoding="utf-8") == body:
                self.same += 1
                return
        except OSError:
            pass
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        self.wrote += 1
        if not self.quiet:
            print(f"  + {rel}", file=sys.stderr)


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


def dashboard(recs, known):
    live = [r for r in recs if r["status"] != "out"]
    counts = {}
    for r in recs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    plan_exists = (render_dir() / PLAN).is_file()
    fm = frontmatter([("type", "fundraising-dashboard"), ("title", "Fundraising Dashboard"),
                      ("updated", TODAY), ("targets", len(recs))],
                     ["fundraising", "dashboard"])
    out = [fm, "# Fundraising Dashboard\n",
           (f"The plan: [[Funding Plan]] · " if plan_exists else "No plan yet — ask the agent to build one · ")
           + "[[Fundraising KPI]]\n",
           "## Pipeline\n", "| Status | Count |\n|---|---|"]
    for s in L.STATUSES:
        if counts.get(s):
            out.append(f"| {GLYPH.get(s, '')} {s.replace('_', ' ')} | {counts[s]} |")
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


def kpi_note():
    k = None
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        L.cmd_kpi(None)
    k = json.loads(buf.getvalue())
    fm = frontmatter([("type", "fundraising-kpi"), ("title", "Fundraising KPI"), ("updated", TODAY)],
                     ["fundraising", "kpi"])
    out = [fm, "# Fundraising KPI\n",
           f"**{k['touched']}** targets contacted or applied to · replied **{k['replied']}** · "
           f"meetings **{k['meetings']}** · accepted **{k['accepted']}** · term sheets **{k['term_sheets']}**\n"]
    for dim, rows in k["by"].items():
        if not rows:
            continue
        out.append(f"## By {dim}\n\n| {dim} | n | replied | meeting |\n|---|---|---|---|")
        out += [f"| {g} | {v['n']} | {v['replied']} | {v['meeting']} |" for g, v in rows.items()]
        out.append("")
    lessons = state_root() / "lessons.md"
    if lessons.is_file():
        out.append("## Lessons\n\n" + lessons.read_text(encoding="utf-8"))
    return "\n".join(out) + "\n"


def render(dest=None, quiet=False):
    dest = pathlib.Path(dest) if dest else render_dir()
    recs = list(L.load().values())
    evs = L.events()
    w = Writer(dest, quiet)
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
    exists = existing_stems | app_titles
    for r in live:
        w.text(f"targets/{title_of(r)}.md",
               target_note(r, [e for e in evs if e["key"] == r["key"]], exists))
    w.text(DASHBOARD, dashboard(recs, known))
    w.text(KPI, kpi_note())

    mdir = state_root()
    mdir.mkdir(parents=True, exist_ok=True)
    mf = mdir / MANIFEST
    old = {}
    try:
        old = json.loads(mf.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        pass
    gone = [k for k in old if k not in w.man]
    mf.write_text(json.dumps({"schema": 1, "generated": TODAY, "dest": str(dest),
                              "files": w.man}, indent=1, ensure_ascii=False), encoding="utf-8")
    if not quiet:
        print(f"\n{w.wrote} written · {w.same} unchanged · {len(live)} targets rendered "
              f"({len(recs) - len(live)} screened out, listed on the dashboard) -> {dest}",
              file=sys.stderr)
        if gone:
            print(f"{len(gone)} note(s) no longer rendered, left in place: "
                  + ", ".join(gone[:5]), file=sys.stderr)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    render(a.dest, a.quiet)


if __name__ == "__main__":
    main()
