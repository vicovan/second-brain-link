#!/usr/bin/env python3
"""
analyze.py — turn a built brain into GOAL-DRIVEN value: per-goal analysis notes,
an Obsidian dashboard, and Obsidian-Copilot custom prompts.

This runs AFTER build_vault.py, over an already-built brain — re-runnable in
seconds without rebuilding the 20k notes, because it only reads the lightweight
frontmatter of the rendered notes (people tagged #person carry company / role /
status / strength / last_contact / url). Deterministic, zero API cost: it ranks
and groups your own data, and emits ready-to-run AI PROMPTS for the judgment parts
(drafting asks / intros) rather than fabricating them.

Usage:
  python3 analyze.py <brain-dir> --goals fundraising,bd,jobsearch,datamining
        [--icp "<who you sell to>"] [--thesis "<what you raise for>"]
        [--copilot-dir <obsidian copilot custom-prompts folder>]
        [--graph-config <vault>/.obsidian/graph.json]

Outputs into <brain-dir>:
  95-goals/<goal>.md      — ranked tables + an AI prompt, per chosen goal
  Dashboard.md            — tag-based Dataview queries (work in any vault layout)
  _DATA_POINTS.md         — catalog of every node type + relation + which SOURCE
                            enriched each field (the data-mining map of the brain)
  _GRAPH.md               — how to read the cross-source global graph + its legend
  copilot-prompts/*.md    — /commands for the Obsidian Copilot plugin
and links them from Home.md. `--copilot-dir` also copies the prompts into your
configured Copilot custom-prompts folder; `--graph-config` merges source/type
color groups into your Obsidian graph (preserving your settings, writing a .bak)
so the global graph is colored by source + type.

Goals are a registry (GOALS) — add a builder to support a new goal; the skill's
goal menu maps to these keys. Every entity note carries `source/<name>` + type
tags (set by the builder), which power the dashboard's by-source tables, the graph
colors, and the field-enrichment-by-source matrix in _DATA_POINTS.md.
"""
import argparse
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# subject-aware layout — a company brain uses company-named folders
# (30-content, 85-locations, 40-pipeline, …). Detect the subject from the built
# brain on disk (00-org/ ⇒ company) and resolve every layer folder through
# build_vault.layout_for — analyze never hardcodes a variant folder name
# (a test guards this, same as for the builder).
# ---------------------------------------------------------------------------

_LAYOUTS = {}


def brain_layout(brain: Path):
    """Return (subject, {layer_key: folder}) for a BUILT brain dir."""
    key = str(brain)
    if key not in _LAYOUTS:
        from build_vault import layout_for
        subject = "company" if (brain / "00-org").is_dir() else "person"
        _LAYOUTS[key] = (subject, layout_for(subject))
    return _LAYOUTS[key]


def _L(brain: Path, key: str):
    """Folder name for a layer KEY under this brain's subject variant."""
    return brain_layout(brain)[1][key]


# ---------------------------------------------------------------------------
# lightweight frontmatter reader (stdlib only — no YAML dependency)
# ---------------------------------------------------------------------------

_FM = re.compile(r"\A---\n(.*?)\n---", re.S)


def _scalar(fm_text, key):
    """Pull a scalar frontmatter value by key; strip quotes and [[wikilink]] braces."""
    # [ \t]* not \s* — \s would swallow the newline and grab the NEXT line's value
    # when this key is empty (e.g. an empty `company:` followed by `role: …`).
    m = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*)$", fm_text)
    if not m:
        return ""
    v = m.group(1).strip().strip('"').strip()
    return v[2:-2] if v.startswith("[[") and v.endswith("]]") else v


def read_people(brain: Path):
    """Read every 10-people/*.md note's frontmatter into dicts. Returns a list of
    {name, company, role, status, strength, last_contact, url, sources_text}."""
    people = []
    pdir = brain / _L(brain, "people")
    if not pdir.is_dir():
        return people
    for p in pdir.rglob("*.md"):
        m = _FM.search(p.read_text(encoding="utf-8", errors="replace"))
        if not m:
            continue
        fm = m.group(1)
        try:
            strength = int(_scalar(fm, "strength") or 0)
        except ValueError:
            strength = 0
        people.append({
            "name": _scalar(fm, "title") or p.stem,
            "company": _scalar(fm, "company"),
            "role": _scalar(fm, "role"),
            "status": (_scalar(fm, "status") or "").lower(),
            "strength": strength,
            "last_contact": _scalar(fm, "last_contact"),
            "url": _scalar(fm, "url"),
            "location": _scalar(fm, "location"),
            "connected_on": _scalar(fm, "connected_on"),
            "dept_name": _scalar(fm, "dept"),
            # company-structure tags the adapters emit (dept/<slug> from
            # LinkedIn-Company Department / Workspace Org Unit; channel/<slug>
            # from Slack channel membership) — the org-chart substrate the
            # company goals (onboarding, whoknows) group by.
            "depts": re.findall(r"dept/([a-z0-9\-]+)", fm),
            "channels": re.findall(r"channel/([a-z0-9\-]+)", fm),
        })
    return people


def read_applied(brain: Path):
    """Parse the synthesis layer's `target-companies.md` 'Where you've actually
    applied' list → {company: application_count}. Empty if there's no career data."""
    f = brain / _L(brain, "synthesis") / "target-companies.md"
    out = Counter()
    if not f.is_file():
        return out
    in_applied = False
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            in_applied = "applied" in line.lower()
            continue
        if in_applied:
            m = re.match(r"-\s*\[\[([^\]]+)\]\]\s*\((\d+)\)", line.strip())
            if m:
                out[m.group(1)] = int(m.group(2))
    return out


def _iter_fm(folder: Path):
    """Yield (path, frontmatter_text) for every .md note under `folder`."""
    if not folder.is_dir():
        return
    for p in folder.rglob("*.md"):
        m = _FM.search(p.read_text(encoding="utf-8", errors="replace"))
        if m:
            yield p, m.group(1)


def _count_bullets(path: Path):
    """Count markdown list items in a file (for aggregate notes like interests.md)."""
    if not path.is_file():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
               if ln.lstrip().startswith(("- ", "* ")))


def scan_layer(brain: Path, folder: str, exclude=()):
    """Scan a per-note layer (e.g. 10-people) → (note_count, source→count Counter,
    set of populated frontmatter field names). Sources come from the automatic
    `source/<name>` tags every entity note carries, so this reports which export
    contributed each data point — the basis for the 'field enrichment by source'
    matrix."""
    src, fields, n = Counter(), set(), 0
    for p, fm in _iter_fm(brain / folder):
        if p.name in exclude:
            continue
        n += 1
        for s in re.findall(r"source/([a-z0-9_\-]+)", fm):
            src[s] += 1
        for key in ("company", "role", "url", "status", "strength", "last_contact",
                    "handles", "email", "phone", "lat", "lng", "address", "category",
                    "kind", "industry", "size", "domain", "dept", "connected_on",
                    "first_contact", "location", "alt_company"):
            if _scalar(fm, key):
                fields.add(key)
    return n, src, fields


def needs_mapping(brain: Path):
    """Pull the '_COVERAGE.md' self-adapt backlog: files the harvester rescued but
    that still want a precise mapping (the self-improvement to-do for new sources)."""
    f = brain / "_COVERAGE.md"
    out = []
    if not f.is_file():
        return out
    grab = False
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("## "):
            grab = "needs a mapping" in ln.lower()
            continue
        if grab and ln.strip().startswith("- "):
            out.append(ln.strip()[2:])
    return out


def _link(name):
    return f"[[{name}]]"


def _by_strength(rows):
    """Sort people most-valuable-first: strength desc, then most-recent contact."""
    return sorted(rows, key=lambda r: (r["strength"], r["last_contact"]), reverse=True)


# ---------------------------------------------------------------------------
# goal builders — each returns (filename, markdown). Deterministic ranking +
# a ready AI prompt for the judgment part.
# ---------------------------------------------------------------------------

INVESTOR_SIGNALS = ("ventures", "venture", "capital", "partners", " vc", "vc ",
                    "fund", "accelerator", "angel", "equity", "investments")
KNOWN_FUNDS = ("greylock", "antler", "antai", "plug and play", "sequoia", "a16z",
               "andreessen", "accel", "index ventures", "balderton", "seedcamp",
               "techstars", "y combinator", "500 ", "speedinvest", "earlybird",
               "point nine", "creandum", "northzone", "atomico", "kima", "founders fund")
DM_ROLE_SIGNALS = ("founder", "co-founder", "ceo", "cto", "coo", "cfo", "cmo",
                   "cpo", "chief", "vp", "vice president", "head of", "head ",
                   "owner", "managing director", "director", "president", "partner")


def _is_investor(company):
    c = (company or "").lower()
    if not c:
        return False
    return any(s in c for s in INVESTOR_SIGNALS) or any(k in c for k in KNOWN_FUNDS)


def _is_decision_maker(role):
    r = (role or "").lower()
    return any(s in r for s in DM_ROLE_SIGNALS)


def _table(rows, cols):
    """Render a small markdown table from rows (list of tuples) + header cols."""
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build_fundraising(brain, people, ctx):
    """Investors/accelerators already in your network → who connects you there."""
    inv = defaultdict(list)
    for pp in people:
        if _is_investor(pp["company"]):
            inv[pp["company"]].append(pp)
    ranked = sorted(inv.items(),
                    key=lambda kv: (max((x["strength"] for x in kv[1]), default=0), len(kv[1])),
                    reverse=True)
    lines = ["---", "type: goal", "tags: [goal, fundraising]", "---", "",
             "# 💰 Fundraising — paths into investors in your network", ""]
    if ctx.get("thesis"):
        lines += [f"> Thesis: {ctx['thesis']}", ""]
    if not ranked:
        lines += ["_No investor/accelerator-shaped companies detected in your network yet._"]
    else:
        lines += [f"**{len(ranked)} investor/accelerator orgs** appear in your network. "
                  "Strongest connection first:", ""]
        for company, ppl in ranked[:40]:
            best = _by_strength(ppl)
            lines.append(f"### {_link(company)} — {len(ppl)} contact(s)")
            rows = [(_link(x["name"]), x["role"] or "—", x["strength"],
                     x["status"] or "—", x["last_contact"] or "—") for x in best[:8]]
            lines.append(_table(rows, ["Who", "Role", "Strength", "Status", "Last contact"]))
            lines.append("")
    lines += ["## ▶ Ask your AI to act", "",
              "> Using the people above (and `00-me/identity.md` for my voice), pick the "
              "5 strongest warm paths to an investor who'd back "
              f"{ctx.get('thesis') or 'a company like mine'}, and draft a short, specific "
              "intro-request to each connector in my voice (≤90 words). Flag any I've gone "
              "quiet on (status: dormant) and suggest a natural reason to reconnect first."]
    return "fundraising.md", "\n".join(lines)


def build_bd(brain, people, ctx):
    """Warm + dormant decision-makers (your sales/BD/partnership surface)."""
    dms = [p for p in people if _is_decision_maker(p["role"]) and p["company"]]
    warm = _by_strength([p for p in dms if p["status"] == "warm"])
    dormant = _by_strength([p for p in dms if p["status"] == "dormant" and p["strength"] >= 3])
    lines = ["---", "type: goal", "tags: [goal, bd]", "---", "",
             "# 🤝 Sales / BD — decision-makers you already know", ""]
    if ctx.get("icp"):
        lines += [f"> Ideal customer/partner profile (ICP): {ctx['icp']}", ""]
    lines += [f"**{len(dms)} decision-makers** (founder/CXO/VP/head/owner/director) in your "
              f"network — {len(warm)} warm, {len(dormant)} dormant & strong.", ""]
    lines += ["## Warm decision-makers", ""]
    rows = [(_link(p["name"]), p["role"], _link(p["company"]), p["strength"], p["last_contact"] or "—")
            for p in warm[:40]]
    lines.append(_table(rows, ["Who", "Role", "Company", "Strength", "Last contact"]) if rows
                 else "_None yet._")
    lines += ["", "## Dormant but strong (reconnect candidates)", ""]
    rows = [(_link(p["name"]), p["role"], _link(p["company"]), p["strength"], p["last_contact"] or "—")
            for p in dormant[:40]]
    lines.append(_table(rows, ["Who", "Role", "Company", "Strength", "Last contact"]) if rows
                 else "_None yet._")
    lines += ["", "## ▶ Ask your AI to act", "",
              "> From the decision-makers above, shortlist those who best fit my ICP "
              f"({ctx.get('icp') or 'describe your ideal customer/partner'}). For the top 10, "
              "give a one-line 'why now' and a non-salesy opener in my voice. Prioritise dormant "
              "strong ties I can credibly re-approach."]
    return "sales-bd.md", "\n".join(lines)


def build_jobsearch(brain, people, ctx):
    """Companies you've targeted/applied to × people you already know there."""
    applied = read_applied(brain)
    by_company = defaultdict(list)
    for p in people:
        if p["company"]:
            by_company[p["company"]].append(p)
    lines = ["---", "type: goal", "tags: [goal, jobsearch]", "---", "",
             "# 🎯 Job search — warm intros into companies you're targeting", ""]
    if applied:
        lines += ["Companies you've actually applied to, with people you already know there "
                  "(stop cold-applying — get referred):", ""]
        shown = 0
        for company, n in applied.most_common(40):
            contacts = _by_strength(by_company.get(company, []))
            if not contacts:
                lines.append(f"### {_link(company)} — applied {n}× · ⚠️ no known contact yet")
                continue
            shown += 1
            lines.append(f"### {_link(company)} — applied {n}× · {len(contacts)} known contact(s)")
            rows = [(_link(x["name"]), x["role"] or "—", x["strength"], x["status"] or "—",
                     x["last_contact"] or "—") for x in contacts[:6]]
            lines.append(_table(rows, ["Who", "Role", "Strength", "Status", "Last contact"]))
            lines.append("")
        if not shown:
            lines.append("_You have applications but no overlapping contacts at those companies "
                         "yet — see the dashboard to find adjacent people._")
    else:
        lines += ["_No application history found (LinkedIn job-application data not present). "
                  "Use the dashboard's company clusters to target where you already have ties._"]
    lines += ["## ▶ Ask your AI to act", "",
              "> For each target company above where I have a contact, pick the single best "
              "person to ask for a referral (highest strength, most recent contact), and draft "
              "a short warm-intro request in my voice (see `00-me/identity.md`). Where I've applied "
              "but know no one, suggest the closest adjacent contact (same industry/cluster)."]
    return "job-search.md", "\n".join(lines)


def build_datamining(brain, people, ctx):
    """Data-mining playbook: deterministic 'plays' over the whole graph (densest
    company clusters, multi-source-confirmed people, message correspondents,
    mirror-vs-stated gaps), each ending in a ready AI prompt. The exhaustive
    catalog of every data point + relation lives in `_DATA_POINTS.md`."""
    clusters = Counter(p["company"] for p in people if p["company"]).most_common(15)
    mirror_dir = _L(brain, "mirror")
    # multi-source-confirmed = a person whose note carries ≥2 source/* tags
    multi = []
    for p, fm in _iter_fm(brain / _L(brain, "people")):
        srcs = sorted(set(re.findall(r"source/([a-z0-9_\-]+)", fm)))
        if len(srcs) >= 2:
            multi.append((_scalar(fm, "title") or p.stem, srcs))
    correspondents = [p for p in people if p["last_contact"]]
    dms = [p for p in people if _is_decision_maker(p["role"]) and p["company"]]
    lines = ["---", "type: goal", "tags: [goal, datamining]", "---", "",
             "# ⛏️ Data mining — patterns worth pulling out of the graph", "",
             "See **`_DATA_POINTS.md`** for the full catalog of every data point and "
             "relation. The plays below are deterministic starting points.", "",
             f"- **{len(people)}** people · **{len(correspondents)}** you've actually "
             f"messaged (have a last-contact date) · **{len(dms)}** decision-makers.",
             f"- **{len(multi)}** people confirmed across ≥2 sources (your highest-confidence "
             "nodes — same human seen on multiple networks).", ""]
    lines += ["## Densest company clusters (where your network concentrates)", ""]
    lines += [f"- {_link(c)} — {n} people" for c, n in clusters] or ["_No company data._"]
    lines += ["", "## Multi-source-confirmed people (highest confidence)", ""]
    lines += [f"- {_link(n)} — {', '.join(s)}" for n, s in multi[:30]] or \
             ["_No one is confirmed across multiple sources yet._"]
    lines += ["", "## ▶ Ask your AI to act", "",
              "> Using `_DATA_POINTS.md` (the data-point & relation catalog) and the #person "
              "frontmatter, surface the 10 non-obvious insights in my network I'd most want to "
              "know for my goals — e.g. clusters I underuse, strong ties in target industries, "
              f"people the algorithms ({mirror_dir}) and I disagree about. Cite note titles."]
    return "data-mining.md", "\n".join(lines)


# ---------------------------------------------------------------------------
# the data-point & relation catalog — a map of EVERY node type, the relations
# between them, and which source enriched which field. Re-runnable; written to
# `_DATA_POINTS.md` at the brain root (like _SUMMARY.md / _COVERAGE.md).
# ---------------------------------------------------------------------------

def build_data_catalog(brain: Path, people):
    """Render `_DATA_POINTS.md`: entity inventory + relation inventory + a
    field-enrichment-by-source matrix + the tag taxonomy + a self-improvement
    backlog + a Mermaid schema + a 'mineable questions' catalog."""
    subject, lay = brain_layout(brain)
    PPL, ORG, PLC = lay["people"], lay["orgs"], lay["places"]
    VOI, MIR, SRCH, LRN = lay["voice"], lay["mirror"], lay["search"], lay["learning"]
    ppl_n, ppl_src, ppl_fields = scan_layer(brain, PPL)
    org_n, org_src, _ = scan_layer(brain, ORG)
    plc_n, plc_src, _ = scan_layer(brain, PLC, exclude=("places.md",))
    post_n, post_src, _ = scan_layer(brain, f"{VOI}/posts")
    interests = _count_bullets(brain / VOI / "interests.md")
    reactions = _count_bullets(brain / VOI / "reactions.md")
    comments = _count_bullets(brain / VOI / "comments.md")
    searches = _count_bullets(brain / SRCH / "search-log.md")
    # company brains log meetings beside events; meetings.md is absent on personal
    events = _count_bullets(brain / LRN / "events.md") + \
             _count_bullets(brain / LRN / "meetings.md")
    mirror = _count_bullets(brain / MIR / "inferences.md") + \
             _count_bullets(brain / MIR / "ad-profile.md")
    # company: deals/campaigns are first-class pipeline notes (one note each)
    deal_n, deal_src, _ = (scan_layer(brain, lay["career"])
                           if subject == "company" else (0, Counter(), set()))
    corr = sum(1 for p in people if p["last_contact"])
    warm = sum(1 for p in people if p["status"] == "warm")
    dormant = sum(1 for p in people if p["status"] == "dormant")
    cold = sum(1 for p in people if p["status"] == "cold")
    works_at = sum(1 for p in people if p["company"])
    all_src = set(ppl_src) | set(org_src) | set(plc_src) | set(post_src)

    L = ["---", "type: catalog", "tags: [catalog, data-points]", "---", "",
         "# 🧭 Data points & relations — what's in this brain and how it connects", "",
         "A map of every **node type**, the **relations** between them, and which "
         "**source** enriched each field — so you (or an AI agent) can mine the graph. "
         "Regenerated by `analyze.py`. Open the global **graph** (see `_GRAPH.md`) to see "
         "all of this visually; everything is tagged for filtering.", "",
         "## Data points (nodes)", "",
         _table([
             ("People", ppl_n, f"`{PPL}/`", "name, company, role, status, strength, last_contact, url, handles"),
             ("Organizations", org_n, f"`{ORG}/`", "name, category, url, known_contacts"),
         ] + ([("Deals & campaigns", deal_n, f"`{lay['career']}/`", "name, kind, date, value")]
              if subject == "company" else []) + [
             ("Places", plc_n, f"`{PLC}/`", "name, kind, lat/lng, address"),
             ("Posts", post_n, f"`{VOI}/posts/`", "text, date, kind, source"),
             ("Comments", comments, f"`{VOI}/comments.md`", "text, date (aggregate)"),
             ("Reactions", reactions, f"`{VOI}/reactions.md`", "kind → count (aggregate)"),
             ("Interests", interests, f"`{VOI}/interests.md`", "topic/page → count (aggregate)"),
             ("Mirror inferences", mirror, f"`{MIR}/`", "ad-interests, advertisers, predictions (aggregate)"),
             ("Events & meetings" if subject == "company" else "Events", events,
              f"`{LRN}/`", "name, date, attendees (aggregate)"),
             ("Searches", searches, f"`{SRCH}/search-log.md`", "query (aggregate)"),
         ], ["Node type", "Count", "Where", "Key fields"]), "",
         "## Relations (edges)", "",
         _table([
             ("person —works_at→ org", works_at, "`#person` `company`", "people with a company"),
             ("you —knows→ person", f"{warm}/{dormant}/{cold}", "`status`", "warm / dormant / cold"),
             ("you —messaged→ person", corr, "`last_contact`", "people you've actually contacted"),
             ("you —reacted→ content", reactions, f"`{VOI}`", "reaction tally"),
             ("you —commented→ content", comments, f"`{VOI}`", "your comments"),
             ("you —interested_in→ topic", interests, f"`{VOI}/interests`", "pages/topics you follow"),
             ("you —checked_in/saved→ place", plc_n, f"`{PLC}`", "places (lat/lng → Map View)"),
             ("you —invited_to→ event", events, f"`{LRN}`", "events + meetings"),
             ("algorithm —infers→ you", mirror, f"`{MIR}`", "the platforms' model of you"),
         ], ["Relation", "Count", "Tag / field", "Meaning"]), ""]

    # field-enrichment-by-source matrix
    L += ["## Field enrichment by source", "",
          "Which export contributed each kind of data point (from the automatic "
          "`source/<name>` tags). Adding a new source should light up new cells here — "
          "if it doesn't, the mapping is leaving data on the table.", "",
          _table([
              (f"People ({PPL})", ", ".join(f"{s} ({n})" for s, n in ppl_src.most_common()) or "—"),
              (f"Orgs ({ORG})", ", ".join(f"{s} ({n})" for s, n in org_src.most_common()) or "—"),
              (f"Places ({PLC})", ", ".join(f"{s} ({n})" for s, n in plc_src.most_common()) or "—"),
              (f"Posts ({VOI})", ", ".join(f"{s} ({n})" for s, n in post_src.most_common()) or "—"),
          ] + ([(f"Deals ({lay['career']})",
                 ", ".join(f"{s} ({n})" for s, n in deal_src.most_common()) or "—")]
               if subject == "company" else []),
              ["Node type", "Sources (count)"]), "",
          f"_Populated person fields: {', '.join(sorted(ppl_fields)) or 'none'}._", ""]

    # tag taxonomy
    L += ["## Tag taxonomy (for the graph / Bases / Dataview)", "",
          "- `source/<name>` — every node, by origin: " +
          (", ".join(f"`source/{s}`" for s in sorted(all_src)) or "_none_"),
          "- type — `person` · `company` · `place` · `post` · `mirror` · `events` · `reputation`",
          "- semantic — `person/friend|follower|request` · `place/check-in|city|home` · "
          "`company/facebook-page|group|connected-app` · `mirror/inference|ad-segment`", ""]

    # self-improvement backlog
    backlog = needs_mapping(brain)
    L += ["## Improvement opportunities (self-adapt backlog)", ""]
    if backlog:
        L += ["Files the harvester rescued but that still want a precise mapping "
              "(close these to enrich the graph further):", ""]
        L += [f"- {b}" for b in backlog[:30]]
    else:
        L += ["_No files are awaiting a mapping — coverage is clean._"]
    L += [""]

    # schema graph
    L += ["## Schema (Mermaid)", "", "```mermaid", "graph LR",
          "  YOU((You))", "  YOU --> P[People]", "  YOU --> V[Voice: posts/comments/reactions]",
          "  YOU --> I[Interests]", "  YOU --> PL[Places]", "  YOU --> E[Events]",
          f"  YOU --> M[{MIR}: how algorithms see you]", "  P -->|works_at| O[Organizations]",
          "  P -.->|message signal| YOU", "```", "",
          "## Mineable questions", "",
          "- Which company clusters do I have the most ties in — and which am I underusing?",
          "- Who is confirmed across ≥2 sources (highest-confidence contacts)?",
          f"- Where do the algorithms ({MIR}) and my stated positioning disagree?",
          "- Which dormant strong ties sit at target-industry companies?",
          "- Which places cluster geographically (open Map View)?",
          "", "_See `95-goals/data-mining.md` for ready plays, and the `/mine` Copilot command._"]
    return "\n".join(L)


def _read_places(brain: Path):
    """Read the places layer's notes → list of {name, kind, address}. The taste
    signal for personalization (saved / reviewed / checked-in spots across sources)."""
    out = []
    for p, fm in _iter_fm(brain / _L(brain, "places")):
        if p.name == "places.md":
            continue
        out.append({"name": _scalar(fm, "title") or p.stem,
                    "kind": _scalar(fm, "kind"), "address": _scalar(fm, "address")})
    return out


def _top_bullets(path: Path, n=25):
    """First n list items of an aggregate note (e.g. interests.md), bullet stripped."""
    out = []
    if path.is_file():
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = ln.lstrip()
            if s.startswith(("- ", "* ")):
                out.append(re.sub(r"\s*\(\d+\)\s*$", "", s[2:].strip()))
            if len(out) >= n:
                break
    return out


def build_personalization(brain, people, ctx):
    """Solve the personalization cold-start: turn your real taste signal (places you
    saved/checked-into, interests you follow, how the algorithms profile you) into
    ready 'recommend me X' prompts grounded in YOUR history — not generic popularity."""
    _, lay = brain_layout(brain)
    places = _read_places(brain)
    by_kind = Counter(p["kind"] or "place" for p in places)
    interests = _top_bullets(brain / lay["voice"] / "interests.md", 25)
    mirror = _top_bullets(brain / lay["mirror"] / "inferences.md", 15)
    lines = ["---", "type: goal", "tags: [goal, personalization]", "---", "",
             "# 🧭 For me — personalized recommendations from my own history", "",
             "Your brain already knows your taste. These prompts ground recommendations in "
             "**your real data** (places you've saved/checked into, interests you follow, the "
             "algorithmic mirror) — solving the cold-start problem a fresh app can't.", "",
             f"**Taste signal:** {len(places)} places "
             f"({', '.join(f'{k} {v}' for k, v in by_kind.most_common(6)) or '—'}) · "
             f"{len(interests)} tracked interests.", ""]
    if places:
        lines += ["## A sample of places you've kept", ""]
        lines += [f"- {_link(p['name'])}" + (f" · _{p['kind']}_" if p["kind"] else "")
                  + (f" — {p['address']}" if p["address"] else "") for p in places[:20]]
        lines += [""]
    if interests:
        lines += ["## What you follow (interest signal)", "",
                  ", ".join(interests[:25]), ""]
    if mirror:
        lines += ["## How the algorithms profile you (the mirror)", "",
                  ", ".join(mirror[:15]), ""]
    lines += ["## ▶ Ready prompts (paste into Obsidian Copilot / your agent)", "",
              f"Each is grounded in `{lay['places']}/`, `{lay['voice']}/interests.md`, "
              f"and `{lay['mirror']}/`:", "",
              "- **Coffee/food:** \"Knowing my taste from my second brain, find me coffee shops "
              "(or restaurants) in **{city}** I'd actually like — match the kinds of places I "
              "already save, and say why each fits.\"",
              "- **Hotels/stays:** \"Recommend a hotel in **{city}** for a {work/leisure} trip "
              "that fits my style, based on the places and neighborhoods I gravitate to.\"",
              "- **Things to do:** \"Suggest things to do this {weekend/evening} in **{city}** "
              "tuned to my interests and past check-ins — not generic tourist lists.\"",
              "- **Where next:** \"Given where I've already been and what I follow, suggest "
              "destinations I should visit in **{month}** and why each suits me.\"",
              "- **Gifts/buys:** \"From my interests and the brands/pages I follow, suggest "
              "things I'd genuinely want.\"", "",
              "> Use the `/for-me` Copilot command for any of these in one click."]
    return "personalization.md", "\n".join(lines)


def _group_tag(people, key):
    """Group people by a structure tag list ('depts' or 'channels') → {slug: [p…]}."""
    groups = defaultdict(list)
    for pp in people:
        for slug in pp.get(key) or []:
            groups[slug].append(pp)
    return groups


def build_onboarding(brain, people, ctx):
    """Company goal: onboard a new hire (or a new agent) onto the Company Brain —
    who to meet, which teams exist, where the conversations happen. Grounded in
    the dept/channel structure tags + message-signal strength; zero API cost."""
    depts = _group_tag(people, "depts")
    chans = _group_tag(people, "channels")
    key_people = _by_strength([p for p in people if _is_decision_maker(p["role"])
                               or p["strength"] >= 3])
    lines = ["---", "type: goal", "tags: [goal, onboarding, company]", "---", "",
             "# 🧭 Onboarding — get productive on this Company Brain fast", ""]
    if key_people:
        lines += ["## People to meet first",
                  "", "Decision-makers and the most-connected colleagues:", ""]
        rows = [(_link(x["name"]), x["role"] or "—",
                 ", ".join(x.get("depts") or []) or "—", x["strength"])
                for x in key_people[:15]]
        lines.append(_table(rows, ["Who", "Role", "Team", "Strength"]))
        lines.append("")
    if depts:
        lines += ["## Teams and where people sit", ""]
        rows = [(d, len(ppl),
                 ", ".join(_link(x["name"]) for x in _by_strength(ppl)[:4]))
                for d, ppl in sorted(depts.items(), key=lambda kv: -len(kv[1]))]
        lines.append(_table(rows[:20], ["Team", "Headcount", "Key people"]))
        lines.append("")
    if chans:
        lines += ["## Where the conversations happen", "",
                  "Channels by membership (join the busy ones first):", ""]
        rows = [(f"#{c}", len(ppl),
                 ", ".join(_link(x["name"]) for x in _by_strength(ppl)[:4]))
                for c, ppl in sorted(chans.items(), key=lambda kv: -len(kv[1]))]
        lines.append(_table(rows[:20], ["Channel", "Members", "Most active"]))
        lines.append("")
    if not (depts or chans or key_people):
        lines += ["_No org-structure signal yet — rebuild with a LinkedIn Company, "
                  "Google Workspace, or Slack export to populate teams/channels._", ""]
    lines += ["## ▶ Ask your AI to act", "",
              "> Using the teams, channels, and people above (and `30-voice/` for how "
              "this company writes), draft my week-one onboarding plan: the 5 people "
              "to meet (with why + an intro line each), the 3 channels/docs to read "
              "first, and the questions a new joiner should ask each team."]
    return "onboarding.md", "\n".join(lines)


def build_whoknows(brain, people, ctx):
    """Company goal: the who-knows-what / who-owns-what expertise map — the
    institutional-memory question every Company Brain exists to answer."""
    depts = _group_tag(people, "depts")
    chans = _group_tag(people, "channels")
    # expertise clusters from role keywords (deterministic, no inference)
    topics = defaultdict(list)
    for pp in people:
        for w in re.findall(r"[a-zA-Z]{4,}", (pp["role"] or "").lower()):
            if w not in ("head", "lead", "senior", "junior", "staff", "chief",
                         "director", "manager", "officer", "president", "vice"):
                topics[w].append(pp)
    ranked_topics = sorted(((t, ppl) for t, ppl in topics.items() if len(ppl) >= 1),
                           key=lambda kv: -len(kv[1]))
    lines = ["---", "type: goal", "tags: [goal, whoknows, company]", "---", "",
             "# 🔎 Who knows what — the expertise & ownership map", ""]
    if ranked_topics:
        lines += ["## By discipline (from roles)", ""]
        rows = [(t.title(), len(ppl),
                 ", ".join(_link(x["name"]) for x in _by_strength(ppl)[:5]))
                for t, ppl in ranked_topics[:20]]
        lines.append(_table(rows, ["Topic", "People", "Who"]))
        lines.append("")
    if depts:
        lines += ["## By team", ""]
        for d, ppl in sorted(depts.items(), key=lambda kv: -len(kv[1]))[:15]:
            best = _by_strength(ppl)
            lines.append(f"### {d} — {len(ppl)} people")
            rows = [(_link(x["name"]), x["role"] or "—", x["strength"]) for x in best[:8]]
            lines.append(_table(rows, ["Who", "Role", "Strength"]))
            lines.append("")
    if chans:
        lines += ["## By channel (where each topic is discussed)", ""]
        rows = [(f"#{c}", len(ppl),
                 ", ".join(_link(x["name"]) for x in _by_strength(ppl)[:5]))
                for c, ppl in sorted(chans.items(), key=lambda kv: -len(kv[1]))[:20]]
        lines.append(_table(rows, ["Channel", "Members", "Ask"]))
        lines.append("")
    if not (ranked_topics or depts or chans):
        lines += ["_No expertise signal yet — rebuild with company exports "
                  "(LinkedIn Company / Workspace / Slack) to populate this map._", ""]
    lines += ["## ▶ Ask your AI to act", "",
              "> When I ask \"who knows X?\" or \"who owns Y?\", answer from the map "
              "above plus each person's note in `10-people/` — name the best person, "
              "their team and channel, one backup, and how warm my path to them is "
              "(status/strength). If nobody fits, say so honestly."]
    return "whoknows.md", "\n".join(lines)


GOALS = {
    "fundraising": build_fundraising,
    "bd": build_bd,
    "jobsearch": build_jobsearch,
    "datamining": build_datamining,
    "personalization": build_personalization,
    "onboarding": build_onboarding,
    "whoknows": build_whoknows,
}

# ---------------------------------------------------------------------------
# dashboard — tag-based Dataview so queries resolve whether the brain is opened
# as its own vault OR indexed as a subfolder of a larger vault.
# ---------------------------------------------------------------------------

def build_dashboard(brain, people, goals):
    """Write Dashboard.md: headline counts + Dataview tables keyed by #tag.
    Requires the Dataview plugin; degrades to readable text without it."""
    warm = sum(1 for p in people if p["status"] == "warm")
    dormant = sum(1 for p in people if p["status"] == "dormant")
    strong = sum(1 for p in people if p["strength"] >= 3)
    clusters = Counter(p["company"] for p in people if p["company"]).most_common(15)
    L = ["---", "type: dashboard", "tags: [dashboard]", "---", "",
         "# 📊 Brain dashboard", "",
         f"**{len(people)}** people · **{warm}** warm · **{dormant}** dormant · "
         f"**{strong}** strong ties (strength ≥3).", "",
         "> Needs the **Dataview** plugin (Community plugins). Queries use `#tags`, so they "
         "work whether you open this brain folder as its own vault or as a subfolder.", "",
         "## Strongest relationships", "", "```dataview",
         "TABLE role AS Role, company AS Company, strength, last_contact",
         "FROM #person WHERE strength >= 3 SORT strength DESC, last_contact DESC LIMIT 50",
         "```", "",
         "## Warm contacts", "", "```dataview",
         "TABLE company AS Company, role AS Role, last_contact",
         'FROM #person WHERE status = "warm" SORT last_contact DESC', "```", "",
         "## Dormant but strong (reconnect)", "", "```dataview",
         "TABLE company AS Company, role AS Role, strength, last_contact",
         'FROM #person WHERE status = "dormant" AND strength >= 3 SORT strength DESC', "```", "",
         "## Network by company", "", "```dataview",
         "TABLE length(rows) AS People FROM #person WHERE company "
         "GROUP BY company SORT length(rows) DESC LIMIT 30", "```", ""]
    if any(g == "fundraising" for g in goals):
        L += ["## Investors / accelerators in network", "", "```dataview",
              'TABLE company AS Org, role AS Role, strength FROM #person '
              'WHERE contains(lower(company), "capital") OR contains(lower(company), "ventures") '
              'OR contains(lower(company), "partners") SORT strength DESC', "```", ""]
    L += ["## People by source (cross-network coverage)", "", "```dataview",
          "TABLE length(rows) AS People FROM #person "
          'FLATTEN file.etags AS tag WHERE startswith(tag, "#source/") '
          "GROUP BY tag SORT length(rows) DESC", "```", ""]
    if any(g == "datamining" for g in goals):
        L += ["## Data mining — multi-source-confirmed people (highest confidence)", "",
              "```dataview",
              "TABLE company AS Company, role AS Role, file.etags AS Tags FROM #person "
              'FLATTEN length(filter(file.etags, (t) => startswith(t, "#source/"))) AS nsrc '
              "WHERE nsrc >= 2 SORT nsrc DESC LIMIT 50", "```",
              "", "Full catalog of every data point + relation → [[_DATA_POINTS]]. "
              "Plays → [[data-mining]].", ""]
    L += ["## Top company clusters (static snapshot)", ""]
    L += [f"- {_link(c)} — {n}" for c, n in clusters]
    L += ["", "## Places", "",
          f"Your saved/reviewed locations live in `{_L(brain, 'places')}/` (each note has "
          "`lat`/`lng`). Install the **Map View** community plugin to see them on a map.", "",
          "**See it all connected:** open the global **Graph view** (colored by source + type — "
          "see [[_GRAPH]]) and the data-point catalog [[_DATA_POINTS]].", "",
          "See goal workspaces in `95-goals/`. For open-ended questions, use **Obsidian "
          "Copilot → Vault QA**, or the `/commands` in `copilot-prompts/`."]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Obsidian-Copilot custom prompts — one markdown file per /command. The plugin
# treats the filename as the command and the body as the template; {} asks the
# user for input, {activeNote}/{selection} inject context, and Vault QA grounds
# answers in the whole brain.
# ---------------------------------------------------------------------------

COPILOT_PROMPTS = {
    "warm-intro": (
        "Find me a warm introduction into {} (a company or person) using my second brain.\n\n"
        "My network notes are tagged #person with frontmatter: company, role, status "
        "(warm/dormant/cold), strength (1-5), last_contact. Identify the people I already know "
        "who can introduce me there, ranked by strength then recency. For the top 3, draft a "
        "short, specific intro-request message in my voice (tone: see [[identity]] and "
        "[[positions-i-hold]]). Keep each under 90 words. Flag anyone I've gone quiet on."),
    "investor-paths": (
        "Act as my fundraising strategist over my second brain. I'm raising for: {}.\n\n"
        "From people tagged #person, find investors/accelerators in my network (companies whose "
        "name contains Ventures/Capital/Partners/VC/Accelerator, or known funds). Rank the paths "
        "by connection strength and recency. For the 5 strongest, draft a concise, specific ask "
        "in my voice and note any second-degree intro through someone I'm close to."),
    "reconnect": (
        "Help me reconnect with {selection}.\n\n"
        "Using their #person note (role, company, last_contact, strength) and my voice "
        "([[identity]]), draft a warm, non-salesy message that references our history and gives a "
        "genuine reason to reconnect now. Under 90 words. If context is thin, ask me one question "
        "first."),
    "job-fit": (
        "I'm exploring a role at {}. Using my second brain: who do I already know there or in the "
        "same industry (people tagged #person), ranked by strength? Draft a referral-request "
        "message to the single best contact in my voice ([[identity]]), and summarise how my "
        "experience maps to that company."),
    "ask-my-network": (
        "Answer using my whole second brain (Vault QA): {}.\n\n"
        "Prefer concrete people/companies/places from my notes over generic advice. Cite the note "
        "titles you used. If the answer needs relationship strength or recency, use the #person "
        "frontmatter (strength, status, last_contact)."),
    "for-me": (
        "Knowing me from my second brain, recommend: {}.\n\n"
        "Examples: 'coffee shops in Lisbon', 'a hotel in Dubai for a work trip', 'things to do "
        "this weekend', 'where should I travel in October'. Ground every pick in MY real data — "
        "the places I've saved/checked into (`85-places/`, each with kind + lat/lng), the "
        "interests/pages I follow (`30-voice/interests.md`), and how the algorithms profile me "
        "(`50-mirror/`). Infer my taste (cuisines, brands, neighborhoods, cities I frequent) and "
        "explain WHY each suggestion fits me. This is cold-start personalization from history, "
        "not generic popularity — prefer specifics over safe defaults."),
    "mine": (
        "Mine my second brain for non-obvious patterns about: {}.\n\n"
        "Use `_DATA_POINTS.md` (the catalog of every node type + relation + which source enriched "
        "each field) and the `#source/*` / `#person` / `#place` / `#mirror` tags. Look across "
        "sources: who appears on multiple networks (highest confidence), which company/place "
        "clusters concentrate my network, and where the algorithmic mirror (50-mirror) disagrees "
        "with how I describe myself. Return ranked, specific findings citing note titles — not "
        "generic advice."),
}


def write_copilot_prompts(dest: Path, lay=None):
    """Write the /command prompt files into `dest` (created if missing). The
    prompt bodies are written in person-variant folder wording; `lay`
    (layer_key → folder) rewrites those folder names for company brains — a
    person layout maps every name to itself, so output is unchanged there."""
    dest.mkdir(parents=True, exist_ok=True)
    for name, body in COPILOT_PROMPTS.items():
        if lay:
            body = (body.replace("85-places", lay["places"])
                        .replace("30-voice", lay["voice"])
                        .replace("50-mirror", lay["mirror"]))
        (dest / f"{name}.md").write_text(body + "\n", encoding="utf-8")
    return len(COPILOT_PROMPTS)


# ---------------------------------------------------------------------------
# the cross-source Obsidian graph — color the global Graph view by source + type
# so every data point from every network is visible and filterable at a glance.
# Driven by the `source/<name>` + type tags every note now carries.
# ---------------------------------------------------------------------------

# a stable palette (Obsidian stores colors as a packed 0xRRGGBB int)
_GRAPH_COLORS = {
    "source/linkedin": 0x0A66C2, "source/facebook": 0x1877F2, "source/instagram": 0xE1306C,
    "source/google": 0x34A853, "source/slack": 0x611F69,
    "tag/person": 0x4C8BF5, "tag/company": 0xF4B400, "tag/place": 0x0F9D58,
    "tag/mirror": 0xDB4437, "tag/post": 0x9E9E9E, "tag/events": 0xAB47BC,
}


def _graph_groups():
    """The color-group list this tool manages (source first so a multi-source node
    colors by source; then type fallbacks). Each: {query, color:{a,rgb}}."""
    groups = []
    for q, rgb in _GRAPH_COLORS.items():
        if q.startswith("source/"):
            query = f"tag:#{q}"
        else:                                  # tag/<type> → tag:#<type>
            query = f"tag:#{q.split('/', 1)[1]}"
        groups.append({"query": query, "color": {"a": 1, "rgb": rgb}})
    return groups


def write_graph_config(graph_json: Path):
    """Merge our source/type color groups into an Obsidian `.obsidian/graph.json`,
    PRESERVING the user's existing settings and any unmanaged color groups. Writes
    a `.bak` first. Returns a status string. Never deletes user config."""
    import json
    graph_json = Path(graph_json).expanduser()
    data = {}
    if graph_json.is_file():
        try:
            data = json.loads(graph_json.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        graph_json.with_suffix(graph_json.suffix + ".bak").write_text(
            json.dumps(data, indent=2), encoding="utf-8")
    managed = {g["query"] for g in _graph_groups()}
    existing = [g for g in data.get("colorGroups", [])
                if isinstance(g, dict) and g.get("query") not in managed]
    data["colorGroups"] = existing + _graph_groups()
    graph_json.parent.mkdir(parents=True, exist_ok=True)
    graph_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"{len(_graph_groups())} color groups merged into {graph_json}"


def write_graph_guide(brain: Path):
    """Write `_GRAPH.md` — how to read the cross-source global graph + the legend."""
    _, lay = brain_layout(brain)
    legend = "\n".join(
        f"- **{q}** → " + ("source: " + q.split('/', 1)[1] if q.startswith("source/")
                            else "type: " + q.split('/', 1)[1])
        for q in _GRAPH_COLORS)
    body = ["---", "type: guide", "tags: [guide, graph]", "---", "",
            "# 🕸️ The graph — all your data points, all sources, one picture", "",
            "Open Obsidian's **Graph view** (the constellation icon, or ⌘/Ctrl-G) to see every "
            "node — people, organizations, places, posts — and how they connect. The links are "
            "real wikilinks (e.g. a person → their company); the **colors** are by source and "
            "type, driven by the tags every note carries.", "",
            "## Color legend", "", legend, "",
            "## Useful graph filters (type in the graph search box)", "",
            "- `tag:#source/facebook` — only Facebook-derived nodes (swap the source name)",
            "- `tag:#person and tag:#source/linkedin` — people from LinkedIn",
            f"- `tag:#mirror` — how the algorithms model you ({lay['mirror']})",
            f"- `path:{lay['people']}` — just your network · "
            f"`path:{lay['places']}` — just places",
            "- `tag:#place/check-in` — Facebook check-ins", "",
            "> Tip: if colors don't show, run `analyze.py … --graph-config <vault>/.obsidian/graph.json` "
            "to install the color groups (it preserves your existing graph settings and writes a `.bak`).",
            "",
            "## For agents — traverse the graph, don't scan the vault", "",
            "`graph.json` at this brain's root (schema `sbl-graph/1`) is the machine-readable "
            "graph: `nodes` (id = note path without `.md`, with layer/type/sources/strength), "
            "typed weighted `edges` (`works_at`, `member_of`, `attended`, `purchased_from`, "
            "`correlated`, `linked` — `w` ∈ (0,1]), and ordered `layers`. The efficient answer "
            "workflow:", "",
            "1. Resolve the entities in the question to node ids (match `title`).",
            "2. Look up their edges; follow `works_at`/`correlated` first (highest signal), "
            "then high-`w` edges outward 1–2 hops.",
            "3. Read ONLY the notes on that activated path (id + `.md`), frontmatter first.",
            "4. Cite what you used as `[[wikilinks]]`.", "",
            "This is spreading activation over the real graph — never read all notes. "
            "(Note: `.obsidian/graph.json` is a different file — Obsidian's own graph styling.)",
            "", "See `_DATA_POINTS.md` for the full catalog of node types and relations."]
    (brain / "_GRAPH.md").write_text("\n".join(body) + "\n", encoding="utf-8")


def update_summary(brain: Path, goals, n_prompts):
    """Refresh `_SUMMARY.md` (written at build time) so it reflects the goal layer
    added here — idempotent via a marker so re-runs replace, not stack."""
    f = brain / "_SUMMARY.md"
    if not f.is_file():
        return
    txt = f.read_text(encoding="utf-8")
    marker = "<!-- analyze:goals -->"
    if marker in txt:                       # drop the previous block before re-adding
        txt = txt.split(marker)[0].rstrip()
    label = {"fundraising": "fundraising", "bd": "sales-bd", "jobsearch": "job-search",
             "datamining": "data-mining", "personalization": "personalization"}
    block = [marker, "", "## Goal workspaces (analyze.py)", "",
             f"Generated for: **{', '.join(goals)}**.", "",
             "| Artifact | What |", "|---|---|"]
    for g in goals:
        stem = label.get(g, g)
        block.append(f"| `95-goals/{stem}.md` | {g} — ranked tables + a ready AI prompt |")
    block += [f"| `Dashboard.md` | live Dataview tables (warm/dormant ties, clusters, investors) |",
              f"| `copilot-prompts/` | {n_prompts} Obsidian-Copilot `/commands` |", ""]
    f.write_text(txt.rstrip() + "\n\n" + "\n".join(block) + "\n", encoding="utf-8")


def link_from_home(brain: Path, goals):
    """Append a 'Goal workspaces' section to Home.md (idempotent via a marker)."""
    home = brain / "Home.md"
    if not home.is_file():
        return
    txt = home.read_text(encoding="utf-8")
    if "## 🎯 Goal workspaces" in txt:
        return
    block = ["", "## 🎯 Goal workspaces", "",
             "- [[Dashboard]] — live tables of your network (Dataview)",
             "- [[_DATA_POINTS]] — every data point + relation (and which source enriched it)",
             "- [[_GRAPH]] — the cross-source global graph (colored by source + type)"]
    label = {"fundraising": "Fundraising paths", "bd": "Sales / BD",
             "jobsearch": "Job search", "datamining": "Data mining",
             "personalization": "For me (personalized recommendations)",
             "onboarding": "Onboarding (company)",
             "whoknows": "Who knows what (company)"}
    for g in goals:
        if g in label:
            stem = {"fundraising": "fundraising", "bd": "sales-bd", "jobsearch": "job-search",
                    "datamining": "data-mining", "personalization": "personalization",
                    "onboarding": "onboarding", "whoknows": "whoknows"}[g]
            block.append(f"- [[{stem}]] — {label[g]}")
    block += ["", "Open-ended questions → **Obsidian Copilot → Vault QA**, or the `/commands` "
              "in `copilot-prompts/`.", ""]
    home.write_text(txt.rstrip() + "\n" + "\n".join(block), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Generate goal-driven analyses + dashboard + Copilot prompts over a built brain.")
    ap.add_argument("brain", help="path to a built brain dir (contains 10-people/, 90-synthesis/, …)")
    ap.add_argument("--goals", default="fundraising,bd,jobsearch",
                    help="comma-separated goals: " + ", ".join(GOALS))
    ap.add_argument("--icp", default="", help="ideal customer/partner profile (tailors the BD note)")
    ap.add_argument("--thesis", default="", help="what you're raising for (tailors the fundraising note)")
    ap.add_argument("--copilot-dir", default=None,
                    help="also copy Copilot prompts into this Obsidian custom-prompts folder")
    ap.add_argument("--graph-config", default=None,
                    help="merge source/type color groups into this .obsidian/graph.json "
                         "(preserves your settings; writes a .bak) so the global graph is "
                         "colored by source + type")
    ap.add_argument("--graph-data", action="store_true",
                    help="(re)generate the brain's root graph.json (sbl-graph/1 typed "
                         "node/edge dataset) by scanning the built vault — the retrofit "
                         "path for vaults built before graph.json existed. No rebuild "
                         "needed; deterministic; zero network.")
    args = ap.parse_args()

    brain = Path(args.brain).expanduser()
    if not (brain / _L(brain, "people")).is_dir():
        print(f"error: {brain} doesn't look like a built brain (no people layer)."); raise SystemExit(1)
    goals = [g.strip() for g in args.goals.split(",") if g.strip() in GOALS]
    if not goals:
        print(f"error: no valid goals in {args.goals!r}; choose from {', '.join(GOALS)}"); raise SystemExit(1)

    people = read_people(brain)
    ctx = {"icp": args.icp, "thesis": args.thesis}
    gdir = brain / "95-goals"
    gdir.mkdir(exist_ok=True)
    for g in goals:
        fname, md = GOALS[g](brain, people, ctx)
        (gdir / fname).write_text(md + "\n", encoding="utf-8")
        print(f"  ✓ 95-goals/{fname}")

    (brain / "Dashboard.md").write_text(build_dashboard(brain, people, goals) + "\n", encoding="utf-8")
    print("  ✓ Dashboard.md")
    # the data-point & relation catalog (always — it's the map of the whole brain)
    (brain / "_DATA_POINTS.md").write_text(build_data_catalog(brain, people) + "\n", encoding="utf-8")
    print("  ✓ _DATA_POINTS.md")
    write_graph_guide(brain)
    print("  ✓ _GRAPH.md")
    # smart-brain layer: health self-check + graph insights + overview canvas
    # (deterministic; suspicions labelled suspicions, nothing auto-merged)
    try:
        import health
        hh = health.run(brain)
        print(f"  ✓ _HEALTH.md/.json ({len(hh['orphans'])} orphans, "
              f"{hh['links']['unresolved']} unresolved links) + "
              "90-synthesis/graph-insights.md + _canvas/brain-overview.canvas")
    except Exception as e:
        print(f"  ! health layer skipped: {e}")
    lay = brain_layout(brain)[1]
    n = write_copilot_prompts(brain / "copilot-prompts", lay)
    print(f"  ✓ copilot-prompts/ ({n} commands)")
    if args.copilot_dir:
        try:
            write_copilot_prompts(Path(args.copilot_dir).expanduser(), lay)
            print(f"  ✓ copied Copilot prompts → {args.copilot_dir}")
        except Exception as e:
            print(f"  ! could not copy to --copilot-dir: {e}")
    if args.graph_config:
        try:
            print("  ✓ " + write_graph_config(args.graph_config))
        except Exception as e:
            print(f"  ! could not write --graph-config: {e}")
    if args.graph_data:
        try:
            import graphdata
            g = graphdata.write_graph_json(brain)
            print(f"  ✓ graph.json — {g['stats']['nodes']} nodes, "
                  f"{g['stats']['edges']} edges, {len(g['layers'])} layers")
        except Exception as e:
            print(f"  ! could not write --graph-data: {e}")
    link_from_home(brain, goals)
    update_summary(brain, goals, n)         # reflect the goal layer in _SUMMARY.md
    print(f"\n✅ analyzed {len(people)} people for goals: {', '.join(goals)} → {brain}")


if __name__ == "__main__":
    main()
