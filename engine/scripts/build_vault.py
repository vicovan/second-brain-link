#!/usr/bin/env python3
"""
build_vault.py — Second Brain Link's multi-source vault builder.

Detects which export(s) you have (LinkedIn, Facebook, Instagram, Google Takeout),
runs the matching source adapters to normalize everything into one canonical
Collector, then renders a single unified, Obsidian-native vault. People seen in
more than one network are merged into one note tagged with each source.

Local-only. No network calls. Privacy enforced in the collector
(see sources/common.py): third-party emails/phones are never stored, and message
bodies are never read — only a derived per-person signal.

Usage:
    python build_vault.py <export.zip | folder> -o <vault-dir> [--overrides f.json]
    python build_vault.py <export.zip | folder> --dry-run        # detect + plan only
"""
import argparse
import json
import re
import sys
import shutil
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources as _sources
from sources import detect_sources, BY_NAME, ALL
def _quar():  # always read the live registry (rebuilt when --mappings overrides)
    """Return the live union of every adapter's quarantine set.

    Reads `sources.ALL_QUARANTINE` live (via the module object, not a by-value
    import) so a `--mappings` rebuild — which re-registers adapters and rebuilds
    the registry — takes effect for callers in this same run.
    """
    return _sources.ALL_QUARANTINE
from sources.common import (Collector, norm_file, obsidian_name, link, iso_date,
                            nk, SENSITIVE_COL_HINTS, EMAIL_RE, read_csv, read_json)
import selfheal

TODAY = datetime.now().strftime("%Y-%m-%d")
OVERRIDES = {"extra_aliases": [], "file_routes": {}}
STRUCTURE = None   # optional brain_structure.json spec (from profile step)
PROVIDER = "claude"   # which agent the in-vault guide is written for (set by --provider)
MIN_ORG_REFS = 1   # orgs below this ref count + no metadata go to 15-organizations/_mentions/ (set by --min-org-refs)

# Provider table — the engine is provider-neutral; only the in-vault agent-guide
# filename + a little wording differ. Adding a provider = one row here + a manifest
# under providers/<name>/. (Agent Skills open standard: same SKILL.md format.)
PROVIDERS = {
    "claude": {"guide": "CLAUDE.md", "agent": "Claude (Claude Code)",
               "install": "~/.claude/skills/second-brain-link/"},
    "openai": {"guide": "AGENTS.md", "agent": "your OpenAI coding agent (Codex)",
               "install": "your Agent Skills directory"},
}

def _provider():
    """Return the PROVIDERS row for the current module-global PROVIDER (the CLI
    `--provider`), defaulting to claude. Used in __main__-side messaging only;
    the VaultWriter reads provider off the Collector instead (see _prov)."""
    return PROVIDERS.get(PROVIDER, PROVIDERS["claude"])

# ---------------------------------------------------------------------------
# Obsidian-native frontmatter rendering
# ---------------------------------------------------------------------------

def _yaml_scalar(v):
    """Render one value as an Obsidian-safe YAML scalar.

    Quotes (with quotes OUTSIDE any brackets) whenever the string contains YAML
    metacharacters, has surrounding whitespace, looks like a YAML bool/null, or
    starts with a YAML indicator char — so a wikilink becomes `"[[Acme]]"`, which
    Obsidian resolves (unquoted fails silently). Numbers pass through bare.
    """
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "":
        return ""
    # Conditions that force quoting: YAML special chars, leading/trailing
    # whitespace, reserved bool/null words, or a leading YAML indicator.
    needs = (re.search(r'[:#\[\]{}>|*&!%@`"\n]', s) or s != s.strip()
             or s.lower() in ("true", "false", "null", "yes", "no", "~")
             or re.match(r"^[-?,]", s))
    if needs:
        # Escape backslashes first, then double-quotes, then wrap in quotes.
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s

def fm(d):
    """Render a dict as an Obsidian YAML frontmatter block (between `---` fences).

    Lists/sets become block sequences (sets sorted for stable output); empty
    collections render as `[]`; None/empty scalars render as a bare key. All
    scalar values go through _yaml_scalar so wikilinks etc. stay Obsidian-safe.
    Route ALL frontmatter through here so the quoting invariant holds everywhere.
    """
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, (list, set)):
            v = sorted(v) if isinstance(v, set) else v
            if v:
                out.append(f"{k}:")
                for item in v:
                    out.append(f"  - {_yaml_scalar(item)}")
            else:
                out.append(f"{k}: []")
        else:
            s = "" if v is None else _yaml_scalar(v)
            out.append(f"{k}:" if s == "" else f"{k}: {s}")
    out.append("---")
    return "\n".join(out)

def write(path: Path, text: str):
    """Write `text` to `path` (creating parent dirs), normalizing to a single
    trailing newline. UTF-8 so mojibake-repaired names survive on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")

def slug(s):
    """Slugify a string for a NON-entity filename (coverage/owner/service notes).

    Do NOT use for person/org/place note filenames — those use obsidian_name()
    so title==filename and `[[X]]` links resolve. Caps at 80 chars; never empty.
    """
    s = re.sub(r"[^\w\s-]", "", s).strip()
    return re.sub(r"[\s_-]+", "-", s)[:80] or "untitled"

def _tag_slug(s):
    """Normalize a tag segment to be Obsidian-tag-safe: lowercase, alphanumerics
    and `-`/`_` only (slashes are kept by the caller for nested tags)."""
    s = re.sub(r"[^a-z0-9_]+", "-", str(s).lower()).strip("-")
    return s

def note_tags(base, sources=None, extra=None):
    """Build a note's `tags` list: the layer/type tag(s) + one `source/<name>` per
    contributing source + any rule-declared semantic tags. This is what lets the
    Obsidian global graph (and Bases/Dataview) color & filter every data point by
    source and type across ALL networks. Deduped + sorted for stable output."""
    tags = set(base or [])
    for s in (sources or []):
        sl = _tag_slug(s)
        if sl:
            tags.add(f"source/{sl}")
    for t in (extra or []):
        t = str(t).strip().lstrip("#")
        if t:
            # normalize each `/`-separated segment, preserve the nesting
            tags.add("/".join(_tag_slug(seg) for seg in t.split("/") if _tag_slug(seg)))
    return sorted(t for t in tags if t)

def _details_block(rec):
    """Render every captured field of an entity record into a markdown 'Details'
    section so FULL-mode keeps all data points (incl. PII + every extra column).
    No-op when there's nothing beyond what the frontmatter already shows."""
    rows = []
    for label, key in (("Email", "email"), ("Phone", "phone"), ("Profile", "url")):
        v = rec.get(key)
        if v:
            rows.append((label, v))
    for k, v in (rec.get("extra") or {}).items():
        if v and str(v).strip():
            rows.append((str(k), str(v).strip()))
    if not rows:
        return ""
    out = ["\n## Details\n"]
    for k, v in rows:
        out.append(f"- **{k}:** {v}")
    return "\n".join(out) + "\n"

def keywords(text, n=20):
    """Return the `n` most-frequent content words in `text` (4+ letters, common
    stopwords removed). A deterministic, zero-API signal feeding the synthesis
    drafts (recurring themes / how-you-describe-yourself); never the final word."""
    words = re.findall(r"[a-z][a-z]{3,}", (text or "").lower())
    stop = set("the and for with that this from your you are our who all have has "
               "into not but can will more their about over across using used use "
               "help building build led team teams they them then than been being "
               "were what when where which while have just like really very".split())
    return [w for w, _ in Counter(w for w in words if w not in stop).most_common(n)]

# ---------------------------------------------------------------------------
# Vault-map role registry — drives the always-generated `_STRUCTURE.md` so every
# folder and generated file is documented (what it is, what feeds it, its role).
# Person-mode layout; 00-org/ replaces 00-me/ in company mode.
# ---------------------------------------------------------------------------
LAYER_ROLES = [
    ("00-me/", "IDENTITY — who the twin speaks as (name, headline, positions, education, skills). `00-org/` in company mode."),
    ("10-people/", "NETWORK — one note per person, merged across sources; tags carry `source/*` + relationship status/strength."),
    ("15-organizations/", "Companies: employers, targets, vendors, pages/groups followed. `_mentions/` holds thin one-off orgs (links still resolve)."),
    ("20-reputation/", "Recommendations received/given + endorsement summary."),
    ("30-voice/", "Your own content: posts/, comments, reactions, interests/follows, saved."),
    ("40-career/", "Applications log, job-seeker preferences, saved jobs, reusable answers."),
    ("50-mirror/", "HOW THE ALGORITHMS SEE YOU — inferences + ad-targeting segments (fed by the mirror/ad_segment emits)."),
    ("60-learning/", "Courses/coaching + events."),
    ("70-services/", "Freelance / Services Marketplace activity."),
    ("80-search/", "Your search history — a curiosity log."),
    ("85-places/", "Saved/reviewed/checked-in locations (lat/lng → Obsidian Map View)."),
    ("90-synthesis/", "THE PAYOFF (derived): network-map, target-companies, positions-i-hold, positioning-gaps."),
    ("99-uncategorized/", "Files no mapping claimed, rescued + summarized by the harvester (nothing lost)."),
    ("_quarantine/", "Sensitive files catalogued but NEVER imported (default mode). In --full they fold into 00-me/my-*.md."),
]
# artifacts written during/after the build; ANALYZE_ARTIFACTS come from analyze.py
ANALYZE_ARTIFACTS = {"Dashboard.md", "_DATA_POINTS.md", "_GRAPH.md", "95-goals/", "copilot-prompts/"}
ARTIFACT_ROLES = [
    ("Home.md", "Map of Content — the human entry point; start here."),
    ("CLAUDE.md", "In-vault agent guide (AGENTS.md for the OpenAI provider) — how an agent should read this brain."),
    ("_STRUCTURE.md", "THIS map — every folder/file + its role."),
    ("_SUMMARY.md", "Seed counts — per-layer note counts + the coverage line (+ goal layer once analyzed)."),
    ("_COVERAGE.md", "Per-file coverage: mapped / routed / harvested / uncategorized / quarantined, + a 'Needs a mapping' backlog."),
    ("_BUILD_REPORT.md", "What this build detected/extracted (sources, notes, log)."),
    ("Dashboard.md", "Live Dataview tables (warm/dormant ties, clusters, by-source) — written by analyze.py."),
    ("_DATA_POINTS.md", "Catalog of every node type + relation + which source enriched each field — written by analyze.py."),
    ("_GRAPH.md", "How to read the cross-source global graph + the color legend — written by analyze.py."),
    ("95-goals/", "Goal workspaces (ranked tables + a ready AI prompt per goal) — written by analyze.py."),
    ("copilot-prompts/", "Obsidian-Copilot `/commands` (warm-intro, investor-paths, mine, …) — written by analyze.py."),
]

# ---------------------------------------------------------------------------
# Builder: renders the vault from a populated Collector
# ---------------------------------------------------------------------------

class VaultWriter:
    """Renders an Obsidian-native vault from a populated Collector into `out`.

    The default `obsidian` emitter wraps this. All output here is deterministic
    (zero API). Run-context (provider/subject/structure_spec) is read off the
    Collector instance, never module globals — an emitter does
    `from build_vault import VaultWriter`, a separate module object, so globals
    set in __main__ would be stale here.
    """
    def __init__(self, col: Collector, out: Path):
        self.col = col
        self.out = out

    def _prov(self):
        """Return the PROVIDERS row for this build's target agent."""
        # read provider off the collector (set in run()) so it survives the
        # emitter's `from build_vault import VaultWriter` (separate module object).
        return PROVIDERS.get(getattr(self.col, "provider", None) or PROVIDER, PROVIDERS["claude"])

    def build(self):
        """Render the full vault. Order matters: orgs render AFTER career/people
        so every company referenced there is already registered → `[[X]]` links
        resolve. home() / scaffolding() write the MOC and agent guide last."""
        self.identity()
        self.people()
        self.organizations()
        self.reputation()
        self.voice()
        self.career()
        self.mirror()
        self.misc()
        self.places()
        self.synthesis()
        self.home()
        self.scaffolding()

    # 00 — identity (company mode roots on the org; person mode on the user)
    def identity(self):
        """Write the root identity note: `00-org/organization.md` in company mode
        (rooted on the org, plus a data-handling note), else `00-me/identity.md`
        (the person the twin speaks as). Subject is read off the Collector."""
        i = self.col.identity
        company_mode = getattr(self.col, "subject", "person") == "company"
        root_dir = "00-org" if company_mode else "00-me"
        if company_mode:
            self._company_data_controller_note(root_dir)
        if not i:
            return
        name = i.get("name", "Me")
        body = [fm({"type": ("organization" if company_mode else "identity"),
                    "title": name or "Me",
                    "aliases": [name] if name else [],
                    "tags": note_tags(["organization"] if company_mode else ["identity"],
                                      i.get("sources", [])),
                    "created": TODAY, "updated": TODAY,
                    "headline": i.get("headline", ""), "location": i.get("location", ""),
                    "industry": i.get("industry", ""),
                    "sources": sorted(i.get("sources", []))}), "",
                f"# {name or 'Me'}\n"]
        if i.get("headline"): body.append(f"**{i['headline']}**\n")
        if i.get("about"): body.append("## About\n\n" + i["about"] + "\n")
        if i.get("positions"):
            body.append("## Experience\n")
            for r in i["positions"]:
                comp = r.get("company", "")
                body.append(f"- **{r.get('title','')}** — {link(comp) if comp else ''} "
                            f"({r.get('start','')} – {r.get('end','')})")
            body.append("")
        if i.get("skills"):
            body.append("## Skills\n\n" + ", ".join(i["skills"][:40]) + "\n")
        if i.get("education"):
            body.append("## Education\n")
            for e in i["education"]:
                body.append(f"- **{e.get('school','')}** — {e.get('degree','')} "
                            f"{e.get('field','')} {e.get('years','')}".rstrip())
            body.append("")
        if i.get("certifications"):
            body.append("## Certifications\n\n" +
                        ", ".join(x for x in i["certifications"] if x) + "\n")
        if i.get("languages"):
            body.append("## Languages\n\n" +
                        ", ".join(x for x in i["languages"] if x) + "\n")
        fname = "organization.md" if company_mode else "identity.md"
        write(self.out / root_dir / fname, "\n".join(body))

    def _company_data_controller_note(self, root_dir):
        """Company mode: emit a short note making the local-first / data-controller
        posture explicit, and list what was quarantined (never imported)."""
        # _quar() reads the live registry so a --mappings rebuild is reflected.
        quar = sorted(k for k in getattr(self.col, "file_keys", set()) if k in _quar())
        body = [fm({"type": "note", "title": "Data handling (company mode)",
                    "tags": ["privacy", "company"]}), "",
                "# Data handling — company mode\n",
                "This brain was built **100% locally** from your organization's own "
                "exports. No data left this machine during the build (an optional "
                "`--gbrain-import` step is the only thing that can send data onward, "
                "and only if you run it). **You are the data controller** for the "
                "employee data processed here.\n",
                "- Third-party & employee **emails/phones are stripped** by default "
                "(use `--full` only on data you're authorized to retain in full).\n",
                "- Message **bodies are never read** — only per-person frequency/"
                "recency signal.\n",
                "- **Quarantined (catalogued, never imported):** "
                + (", ".join(quar) if quar else "none detected") + "\n"]
        write(self.out / root_dir / "data-handling.md", "\n".join(body))

    # 10 — people (merged across sources)
    def people(self):
        """Write one note per person in `10-people/`, already merged across sources
        by the Collector. Filename==title (obsidian_name) so `[[X]]` resolves;
        collisions get a numeric suffix. Derives relationship strength (1-5) and
        status from the privacy-safe message SIGNAL only (count + last date — no
        body was ever read). email/phone are blank unless --full."""
        seen = set()
        d = self.out / "10-people"
        for key, r in self.col.people.items():
            name = r["name"]
            title = obsidian_name(name)
            # disambiguate same-title people with a numeric suffix so no filename collides
            base = title; i = 2
            while base.lower() in seen:
                base = f"{title} {i}"; i += 1
            seen.add(base.lower())
            msg = self.col.msg_signal.get(key, (0, ""))
            cnt, last = msg
            # strength buckets from message count only (frequency signal, not content)
            if cnt >= 20: strength = 5
            elif cnt >= 10: strength = 4
            elif cnt >= 5: strength = 3
            else: strength = 2
            # warm = recent sustained contact; dormant = had contact but it lapsed pre-2024
            status = "warm" if cnt >= 5 else ("dormant" if last and last < "2024" else "cold")
            comp = r.get("company", "")
            note = fm({"type": "person", "title": title,
                       "aliases": [name] if name != title else [],
                       "tags": note_tags(["person"], r["sources"], r.get("tags")),
                       "sources": sorted(r["sources"]),
                       "created": r.get("date") or TODAY,
                       "status": status,
                       "company": link(comp) if comp else "",
                       "role": r.get("role", ""),
                       "url": r.get("url", ""),
                       "email": r.get("email", ""),   # only populated in --full mode
                       "phone": r.get("phone", ""),   # only populated in --full mode
                       "handles": sorted(r.get("handles", [])),
                       "strength": strength, "last_contact": last})
            sub = f"{r.get('role','')}{' at ' + link(comp) if comp else ''}".strip()
            details = _details_block(r)
            write(d / f"{base}.md", note + f"\n\n# {name}\n\n{sub}\n" + details)
        self.col.note(f"vault: {len(seen)} person notes (merged across sources)")
        self._people_count = len(seen)

    # 15 — organizations
    def organizations(self):
        """Write one note per organization in `15-organizations/`. Runs AFTER
        career/people so every company merely REFERENCED there (positions,
        applications, a person's employer) also gets a note → `[[Acme]]` links
        resolve instead of dangling. Filename==title via obsidian_name."""
        seen = set()
        counts = getattr(self.col, "_li_company_counts", Counter())
        min_refs = getattr(self.col, "min_org_refs", 1)
        orgs = dict(self.col.orgs)
        # Reverse index: which known people are at each org → list them in the org's
        # body so an org node carries real context, not just a title.
        people_by_org = {}
        for pr in self.col.people.values():
            cn = (pr.get("company") or "").strip()
            if cn:
                people_by_org.setdefault(nk(cn), []).append(pr)
        # ensure every merely-referenced company also gets a note so links resolve
        for c in self.col.companies:
            orgs.setdefault(c, {"category": "referenced", "sources": set()})
        pruned = 0
        for name, meta in orgs.items():
            title = obsidian_name(name)
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            note = fm({"type": "company", "title": title,
                       "aliases": [name] if name != title else [],
                       "tags": note_tags(["company"], meta.get("sources", []), meta.get("tags")),
                       "category": meta.get("category", "referenced"),
                       "sources": sorted(meta.get("sources", [])),
                       "url": meta.get("url", ""),
                       "known_contacts": counts.get(name, 0)})
            details = _details_block(meta)
            # Declutter: a "thin" org (few references AND no metadata) goes to a
            # _mentions/ subfolder. Obsidian resolves [[links]] by basename across
            # the whole vault, so links from people/career notes still work — the
            # main 15-organizations/ list just stays focused on real companies.
            has_meta = bool(meta.get("url") or meta.get("extra")
                            or meta.get("category", "referenced") != "referenced")
            thin = min_refs > 1 and not has_meta and counts.get(name, 0) < min_refs
            sub = "_mentions" if thin else ""
            if thin:
                pruned += 1
            # Body context: category line + the people known at this org.
            ctx = []
            cat = meta.get("category", "referenced")
            if cat and cat != "referenced":
                ctx.append(f"_{cat}_\n")
            folks = people_by_org.get(nk(name), [])
            if folks:
                ctx.append(f"## People here ({len(folks)})\n")
                for pr in sorted(folks, key=lambda x: x["name"].lower())[:50]:
                    role = (pr.get("role") or "").strip()
                    ctx.append(f"- [[{obsidian_name(pr['name'])}]]" + (f" — {role}" if role else ""))
                ctx.append("")
            ctx_body = ("\n".join(ctx) + "\n") if ctx else ""
            write(self.out / "15-organizations" / sub / f"{title}.md",
                  note + f"\n\n# {title}\n\n" + ctx_body + details)
        self._orgs_count = len(seen)
        self._orgs_pruned = pruned
        if pruned:
            self.col.note(f"[orgs] moved {pruned} thin one-off companies to "
                          f"15-organizations/_mentions/ (min_org_refs={min_refs}; links still resolve)")

    # 20 — reputation
    def reputation(self):
        """Write `20-reputation/` notes: recommendations received/given and an
        endorsements summary. Skips any sub-note that has no data."""
        c = self.col; d = self.out / "20-reputation"
        if c.reputation_received:
            lines = [fm({"type": "reputation", "tags": ["reputation"]}), "",
                     "# Recommendations received\n"]
            for r in c.reputation_received:
                who = r["who"] or "Someone"
                lines.append(f"### From {link(who)}\n\n{r['text']}\n")
            write(d / "recommendations-received.md", "\n".join(lines))
        if c.reputation_given:
            lines = [fm({"type": "reputation", "tags": ["reputation"]}), "",
                     "# Recommendations given\n"]
            for r in c.reputation_given:
                lines.append(f"### To {link(r['who'] or 'Someone')}\n\n{r['text']}\n")
            write(d / "recommendations-given.md", "\n".join(lines))
        if c.endorse_received or c.endorse_given:
            lines = [fm({"type": "reputation", "tags": ["reputation"]}), "",
                     "# Endorsements\n", "## Received (by skill)\n"]
            for sk, n in c.endorse_received.most_common():
                lines.append(f"- {sk}: {n}")
            lines.append(f"\n## Given: {c.endorse_given}")
            write(d / "endorsements.md", "\n".join(lines))

    # 30 — voice
    def voice(self):
        """Write `30-voice/`: one note per post, plus comments, reactions,
        interests/follows, and a saved-items count. Also caches a combined voice
        corpus on self for the synthesis drafts (positions-i-hold)."""
        c = self.col; d = self.out / "30-voice"; posts_dir = d / "posts"
        for idx, p in enumerate(c.posts):
            if not p["text"]:
                continue
            note = fm({"type": "post",
                       "tags": note_tags(["post"], [p["source"]], p.get("tags")),
                       "kind": p["kind"],
                       "source": p["source"], "created": p["date"], "url": p.get("url", "")})
            write(posts_dir / f"{p['date'] or 'post'}-{idx}.md", note + f"\n\n{p['text']}\n")
        if c.comments:
            lines = [fm({"type": "voice", "tags": ["voice"]}), "", "# Comments\n"]
            for r in c.comments:
                lines.append(f"- ({r['date']}) [{r['source']}] {r['text']}")
            write(d / "comments.md", "\n".join(lines))
        if c.reactions:
            lines = ["# Reactions & votes\n"]
            for k, n in c.reactions.most_common():
                lines.append(f"- {k}: {n}")
            write(d / "reactions.md", "\n".join(lines))
        if c.interests:
            lines = ["# Interests & follows\n",
                     "*Pages, topics, hashtags, channels you follow across networks.*\n"]
            for tag, n in c.interests.most_common(200):
                lines.append(f"- {tag}" + (f" ({n})" if n > 1 else ""))
            write(d / "interests.md", "\n".join(lines))
        if c.saved_count:
            write(d / "saved.md", f"# Saved items\n\n{c.saved_count} items you kept.")
        self._voice_corpus = " ".join(p["text"] for p in c.posts) + " " + \
                             " ".join(r["text"] for r in c.comments)
        self._voice_count = len(c.posts) + len(c.comments)

    # 40 — career
    def career(self):
        """Write `40-career/`: applications log, job-seeker preferences, saved jobs,
        and reusable application answers. Companies are linked via link() so the
        orgs pass (which runs after) registers them as resolvable notes."""
        c = self.col; d = self.out / "40-career"
        if c.applications:
            dates = sorted(c.app_dates)
            note = fm({"type": "career", "title": "Applications log", "tags": ["career"],
                       "count": sum(c.applications.values()),
                       "window": f"{dates[0]}..{dates[-1]}" if dates else "",
                       "top_roles": [t for t, _ in c.app_titles.most_common(5)],
                       "top_companies": [x for x, _ in c.applications.most_common(8)]})
            note += "\n\n# Applications log\n\n## Most-applied companies\n"
            note += "\n".join(f"- {link(x)} ({n})" for x, n in c.applications.most_common(15))
            note += "\n\n## Most-applied roles\n"
            note += "\n".join(f"- {t} ({n})" for t, n in c.app_titles.most_common(15))
            write(d / "applications.md", note)
        if c.prefs:
            write(d / "preferences.md", "# Job-seeker preferences\n\n" +
                  "\n".join(f"- **{k}**: {v}" for k, v in c.prefs.items()))
        if c.saved_jobs:
            lines = ["# Saved jobs\n"]
            for j in c.saved_jobs:
                lines.append(f"- {j['title']} — {link(j['company']) if j['company'] else ''}")
            write(d / "saved-jobs.md", "\n".join(lines))
        if c.reusable:
            lines = ["# Reusable application answers\n",
                     "*Pull from here for future applications instead of writing fresh.*\n"]
            for r in c.reusable:
                if r["q"] or r["a"]:
                    lines.append(f"**Q: {r['q']}**\n\n{r['a']}\n")
            write(d / "reusable-answers.md", "\n".join(lines))

    # 50 — mirror
    def mirror(self):
        """Write `50-mirror/`: how the platforms see the user — algorithmic
        inferences and the ad-targeting segment profile. De-duplicates while
        preserving order. Feeds the positioning-gaps synthesis draft."""
        c = self.col; d = self.out / "50-mirror"
        if c.mirror_inferences:
            uniq = list(dict.fromkeys(c.mirror_inferences))
            note = fm({"type": "mirror", "title": "How platforms see me",
                       "tags": note_tags(["mirror", "mirror/inference"], c.sources),
                       "source": "inferences"})
            note += "\n\n# How the algorithms categorize me\n\n"
            note += "\n".join(f"- {x}" for x in uniq[:120])
            write(d / "inferences.md", note)
        if c.ad_segments:
            uniq = list(dict.fromkeys(c.ad_segments))
            note = [fm({"type": "mirror", "title": "Ad profile",
                        "tags": note_tags(["mirror", "mirror/ad-segment"], c.sources),
                        "source": "ad-profile"}), "",
                    "# Ad profile\n",
                    f"Ad-targeting segments: {len(uniq)} "
                    f"· ads clicked: {getattr(c,'_li_ads_clicked',0)} "
                    f"· engagements: {getattr(c,'_li_ad_eng',0)}\n",
                    "## Targeting segments (revealed interests)"]
            for s in uniq[:80]:
                note.append(f"- {s}")
            write(d / "ad-profile.md", "\n".join(note))

    # 60/70/80 — misc
    def misc(self):
        """Write the smaller layers: `60-learning/` (coaching, events),
        `70-services/` (per-service counts), `80-search/` (search log). Caches
        search keywords on self for the target-companies synthesis draft."""
        c = self.col
        if c.learning_count:
            write(self.out / "60-learning" / "coaching.md",
                  f"# Learning coach sessions\n\n{c.learning_count} messages recorded.")
        if c.events:
            ev_sources = {e.get("source") for e in c.events if e.get("source")}
            lines = [fm({"type": "events",
                         "tags": note_tags(["events"], ev_sources)}), "", "# Events\n"]
            for e in c.events:
                line = f"- {e['name']} — {e['date']}".rstrip(" —")
                if e.get("location"):
                    line += f" · 📍 {e['location']}"
                lines.append(line)
                if e.get("description"):
                    lines.append(f"  - {e['description']}")
            write(self.out / "60-learning" / "events.md", "\n".join(lines))
        if any(c.services.values()):
            d = self.out / "70-services"
            for label, n in c.services.items():
                if n:
                    write(d / f"{slug(label)}.md", f"# {label.title()}\n\n{n} {label}.")
        if c.searches:
            write(self.out / "80-search" / "search-log.md",
                  "# Search log\n\n*What you've been looking for, over time.*\n\n" +
                  "\n".join(f"- {q}" for q in c.searches[:200]))
            self._search_terms = keywords(" ".join(c.searches), 20)

    # 85 — places (saved/reviewed locations: Google Maps, IG locations)
    def places(self):
        """Write the `85-places/` layer from the Collector's places bucket (Google
        Maps saved/reviewed, IG locations): ONE note per place, filename==place name
        (obsidian_name), each carrying its full detail (address, lat/lng, map link,
        lists, review) — exactly like people/orgs get one note each. No aggregate
        `places.md` index: an index that `[[links]]` thousands of places became one
        giant graph hub the whole graph clustered under (and a confusing mega-note).
        No-op when there are no places."""
        c = self.col
        if not c.places:
            return
        d = self.out / "85-places"
        for p in c.places.values():
            lat, lng = p.get("lat", ""), p.get("lng", "")
            lists = sorted(p.get("lists", []))
            list_tags = [f"place/list/{_tag_slug(x)}" for x in lists]
            fmd = {"type": "place", "title": obsidian_name(p["name"]),
                   "tags": note_tags(["place", f"place/{_tag_slug(p.get('kind','place'))}"]
                                     + list_tags,
                                     p.get("sources", []), p.get("tags")),
                   "address": p.get("address", ""), "url": p.get("url", ""),
                   "lat": lat, "lng": lng,
                   # combined key the Obsidian "Map View" plugin reads by default,
                   # so saved places plot on a map with no extra config.
                   "location": f"{lat},{lng}" if (lat and lng) else ""}
            if lists:
                fmd["lists"] = lists
            fmd["created"] = p.get("date", "")
            fmd["sources"] = sorted(p.get("sources", []))
            note = fm(fmd)
            body = note + f"\n\n# {p['name']}\n"
            if p.get("address"):
                body += f"\n{p['address']}\n"
            if lists:
                body += f"\nSaved in: {', '.join(lists)}\n"
            if p.get("url"):
                body += f"\n[View on Google Maps]({p['url']})\n"
            if p.get("note"):
                body += f"\n## My review\n\n{p['note']}\n"
            write(d / f"{obsidian_name(p['name'])}.md", body)
        self._places_count = len(c.places)

    # 90 — synthesis
    def synthesis(self):
        """Write the `90-synthesis/` brains — the goal-driven summaries the agent
        is told to read first: network-map, target-companies, and the two
        deterministic drafts (positions-i-hold, positioning-gaps, marked with
        callouts) that the optional AI enrichment pass later articulates."""
        c = self.col; d = self.out / "90-synthesis"
        # network map
        cc = getattr(c, "_li_company_counts", None)
        if c.people:
            by_company = Counter()
            for r in c.people.values():
                if r.get("company"):
                    by_company[r["company"]] += 1
            by_source = Counter()
            for r in c.people.values():
                for s in r["sources"]:
                    by_source[s] += 1
            lines = [fm({"type": "synthesis", "title": "Network map",
                         "tags": ["synthesis"], "updated": TODAY}), "",
                     "# Network map\n",
                     f"Total people: **{len(c.people)}** across "
                     f"{', '.join(sorted(c.sources))}\n",
                     "## People by source\n"]
            for s, n in by_source.most_common():
                lines.append(f"- {s}: {n}")
            lines.append("\n## Strongest company clusters\n")
            for comp, n in by_company.most_common(20):
                lines.append(f"- {link(comp)} — {n} people")
            warm = sum(1 for v in c.msg_signal.values() if v[0] >= 5)
            lines.append(f"\n## Relationship signal\n\n**{warm}** correspondents with "
                         "sustained contact (5+ messages). People with `status: warm` "
                         "and an old `last_contact` are your revival candidates. People "
                         "appearing in multiple `sources` are your strongest multi-context ties.\n")
            write(d / "network-map.md", "\n".join(lines))

        # target companies
        if c.applications or getattr(self, "_search_terms", None):
            lines = [fm({"type": "synthesis", "tags": ["synthesis"]}), "",
                     "# Target companies & intent\n", "## Where you've actually applied\n"]
            for x, n in c.applications.most_common(15):
                lines.append(f"- {link(x)} ({n})")
            if c.app_titles:
                lines.append("\n## Roles you've targeted\n")
                for t, n in c.app_titles.most_common(10):
                    lines.append(f"- {t} ({n})")
            if getattr(self, "_search_terms", None):
                lines.append("\n## Recurring search themes\n\n" + ", ".join(self._search_terms))
            write(d / "target-companies.md", "\n".join(lines))

        # positions I hold (draft)
        vk = keywords(getattr(self, "_voice_corpus", ""), 25)
        draft = [fm({"type": "synthesis", "tags": ["synthesis", "draft"]}), "",
                 "> [!warning] Deterministic draft",
                 "> Run the AI enrichment pass to turn these signals into "
                 "articulated positions in your voice.\n",
                 "# Positions I hold (draft)\n",
                 f"Public activity analyzed: **{getattr(self,'_voice_count',0)}** posts/comments "
                 f"across {', '.join(sorted(c.sources))}.\n",
                 "## Recurring themes in what I post & engage with\n\n" +
                 (", ".join(vk) if vk else "*(low public activity — this layer is thin)*")]
        write(d / "positions-i-hold.md", "\n".join(draft))

        # positioning gaps (draft)
        idk = keywords(f"{c.identity.get('headline','')} {c.identity.get('about','')}", 15)
        gap = [fm({"type": "synthesis", "tags": ["synthesis", "draft"]}), "",
               "> [!info] Deterministic draft",
               "> Enrichment will interpret the gap between how you describe yourself "
               "and how the algorithms tag you.\n",
               "# Positioning gaps (draft)\n",
               "## How I describe myself\n\n" + (", ".join(idk) or "*(no profile summary)*"),
               "\n## How platforms tag me\n\n" +
               (", ".join(list(dict.fromkeys(c.mirror_inferences))[:25]) or "*(no inference data)*")]
        write(d / "positioning-gaps.md", "\n".join(gap))

    # Home MOC
    def home(self):
        """Write `Home.md` — the Map of Content and human entry point: example
        agent prompts, links into the synthesis layer, and a layer legend."""
        c = self.col
        name = c.identity.get("name", "") or "your professional life"
        srcs = ", ".join(sorted(c.sources)) or "your data"
        body = f"""{fm({"type": "moc", "tags": ["moc", "home"], "title": "Home",
                        "sources": sorted(c.sources)})}

# 🧠 Second Brain Link — Home

Your digital twin, built from **{srcs}** ({name}). Start here, then ask your AI anything.

> [!tip] Try asking your AI
> - "Using my network map, who are my strongest dormant connections, and draft a reconnect message to each in my voice."
> - "Who shows up across multiple networks — those are my strongest multi-context relationships."
> - "How do the algorithms categorize me vs how I describe myself, and what should I change?"

## Your synthesis (start here)
- [[identity]] — who the twin speaks as
- [[network-map]] — your unified network across all sources
- [[positions-i-hold]] — your real public stances (for writing in your voice)
- [[target-companies]] — where you've actually been aiming
- [[positioning-gaps]] — how you see yourself vs how the algorithms tag you

## Your layers
`00-me/` identity · `10-people/` network · `15-organizations/` companies ·
`20-reputation/` · `30-voice/` posts & interests · `40-career/` · `50-mirror/` ·
`60-learning/` · `70-services/` · `80-search/`

## How to explore
Open **Graph view** (left ribbon) to see your network as a map — people link to
companies link to roles, merged across every source. Filter with the **tag pane**
(`person`, `company`, `post`, `synthesis`…) or **Properties** (`sources`, `status`).
Everything is plain Markdown you own.

*Built by Second Brain Link · secondbrainlink.com · sources: {srcs}*
"""
        write(self.out / "Home.md", body)

    def scaffolding(self):
        """Write the non-layer scaffolding: the provider's agent guide
        (CLAUDE.md/AGENTS.md), a `.gitignore` that excludes quarantine/attachments,
        and ALWAYS a `_STRUCTURE.md` vault map (what goes where + each file's role)."""
        prov = self._prov()
        write(self.out / prov["guide"], vault_guide(prov))
        write(self.out / ".gitignore", "_quarantine/\nattachments/\n.obsidian/\n.trash/\n")
        self._structure_index()

    def _structure_index(self):
        """Write `_STRUCTURE.md` — the vault MAP: every folder and every generated
        file annotated with its role (what it is, what feeds it, what it's for), so a
        human or agent can see at a glance what goes where. Layers present in THIS
        build are marked ✅; parts that are empty for this export ◻️; artifacts written
        by a later step (analyze.py) are labelled so their absence now isn't a gap.
        If a brain_structure.json spec is present, its designed-layers view is
        appended. Read off the Collector, never a module global (emitters import
        build_vault as a separate module object)."""
        present = lambda rel: (self.out / rel).exists()
        mark = lambda rel: "✅" if present(rel) else "◻️"
        L = [fm({"type": "structure", "title": "Vault structure", "tags": ["structure"],
                 "sources": sorted(self.col.sources)}), "",
             "# 🗺️ Vault structure — what goes where", "",
             f"Built by Second Brain Link · sources: **{', '.join(sorted(self.col.sources)) or 'none'}**. "
             "Folders generate only if the data exists, so this brain is the subset your "
             "exports support. ✅ = present here · ◻️ = empty for this export · ⏳ = written by "
             "`analyze.py` (the value/goals step, run after the build).", "",
             "## Layers (the knowledge graph)", ""]
        for rel, role in LAYER_ROLES:
            L.append(f"- {mark(rel)} **`{rel}`** — {role}")
        L += ["", "## Reports & generated artifacts", ""]
        for rel, role in ARTIFACT_ROLES:
            # analyze artifacts: ⏳ until the value step runs. Core build reports
            # (_SUMMARY/_COVERAGE/_BUILD_REPORT/Home/guide) are written each build,
            # some AFTER this map — so always mark them present.
            m = ("⏳" if not present(rel) else "✅") if rel in ANALYZE_ARTIFACTS else "✅"
            L.append(f"- {m} **`{rel}`** — {role}")
        # any unexpected top-level folder not covered above (forward-compat)
        known = {r.split("/")[0].rstrip("/") for r, _ in LAYER_ROLES + ARTIFACT_ROLES}
        extra = sorted(p.name for p in self.out.iterdir()
                       if p.is_dir() and p.name not in known and not p.name.startswith("."))
        if extra:
            L += ["", "## Other folders", ""] + [f"- **`{e}/`**" for e in extra]
        spec = getattr(self.col, "structure_spec", None)
        if spec:
            L += ["", "## Designed structure (from the profile/mindmap)", "",
                  f"Taxonomy: **{spec.get('taxonomy','')}**.", ""]
            for layer in spec.get("layers", []):
                folder = layer["folder"]
                L.append(f"- {mark(folder)} **`{folder}/`** — {layer.get('purpose','')}")
                if layer.get("source_files"):
                    L.append(f"    - from: {', '.join(layer['source_files'])}")
            L.append("\nSee `_profile/brain_structure.md` / `.canvas` for the diagram, and "
                     "`_profile/<source>_mindmap.md` for every file & field.")
        write(self.out / "_STRUCTURE.md", "\n".join(L))

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def index_files(root: Path):
    """Walk `root` recursively. Returns (file_index, all_paths): file_index maps a
    normalized filename (norm_file — the key adapters/mappings must return as
    consumed) to the list of paths sharing it, limited to data suffixes; all_paths
    is every file on disk (the harvester/adapters may look beyond the index)."""
    idx = {}
    all_paths = []
    for p in root.rglob("*"):
        if p.is_file():
            all_paths.append(p)
            if p.suffix.lower() in (".csv", ".json", ".ics", ".vcf", ".html", ".htm"):
                idx.setdefault(norm_file(p.name), []).append(p)
    return idx, all_paths

def build_uncategorized_and_coverage(col, out, file_index, all_paths, consumed_keys,
                                     sources_used, owned_elsewhere=None):
    """For every file no adapter claimed, run the universal harvester to RESCUE
    its data deterministically (nothing lost), summarize its shape into the
    target layer (`99-uncategorized/` by default), then write `_COVERAGE.md`
    classifying every file (mapped / routed / harvested / uncategorized /
    quarantined). Harvested files are flagged under "Needs a mapping" — the cue
    to write a precise mapping JSON. Skips quarantine-class files and any file
    `owned_elsewhere` (consumed by a sibling brain) to keep the split clean."""
    import harvester
    routes = OVERRIDES.get("file_routes", {})
    owned_elsewhere = owned_elsewhere or set()
    uncategorized = []
    harvested = []   # (key, shape) — universal harvester rescued these; flag for a mapping
    for key, paths in file_index.items():
        if key in consumed_keys:
            continue
        # skip quarantine-class (linkedin set is the broadest; reuse it)
        if key in _quar():
            continue
        # in a sibling build, files consumed by the OTHER subject's brain belong
        # there — don't dump them as uncategorized here (keeps the split clean).
        if key in owned_elsewhere:
            continue
        p = paths[0]
        route = routes.get(key)
        # Universal harvester: before summarizing, try to RESCUE the data
        # deterministically (people/places/posts/interests/message-signal) so
        # nothing is lost. A real mapping always beats this — flag it for one.
        if not route:
            hits, shape = harvester.harvest(col, "harvested", p)
            if hits:
                harvested.append((key, shape, hits))
        layer = (route or {}).get("layer", "99-uncategorized")
        title = (route or {}).get("title", p.stem)
        # summarize columns safely
        cols = []
        if p.suffix.lower() == ".csv":
            rows = read_csv(p)
            headers = list(rows[0].keys()) if rows else []
            for h in headers:
                vals = [(r.get(h) or "").strip() for r in rows[:200]]
                ne = [v for v in vals if v]
                sample = "[redacted]" if any(s in nk(h) for s in SENSITIVE_COL_HINTS) else (ne[0][:48] if ne else "")
                cols.append(f"- **{h}** — {len(ne)}/{len(vals)} filled · e.g. `{sample}`")
            nrows = len(rows)
        else:
            data = read_json(p)
            nrows = len(data) if isinstance(data, list) else (len(data) if isinstance(data, dict) else 0)
            cols.append(f"- (JSON structure; {p.suffix} file)")
        body = [f"# {title}\n",
                f"*Source file: `{p.name}` — {nrows} records. "
                f"{'Routed by override.' if route else 'No adapter matched; summarized so the data is not lost.'}*\n",
                "## Structure\n", *cols]
        write(out / layer / f"{slug(title)}.md", "\n".join(body))
        if not route:
            uncategorized.append(key)

    # coverage report
    total = len(file_index)
    quar = sum(1 for k in file_index if k in _quar())
    leveraged = sum(1 for k in file_index if k in consumed_keys or k in routes)
    lines = ["# Coverage report\n",
             f"Sources detected: **{', '.join(sources_used) or 'none'}**\n",
             f"**{leveraged}/{total - quar}** importable files leveraged "
             f"({len(uncategorized)} uncategorized, {quar} quarantined).\n",
             "## By file\n"]
    harvested_keys = {k for k, _, _ in harvested}
    for key in sorted(file_index):
        if key in _quar():
            st = "quarantined (not imported)"
        elif key in consumed_keys:
            st = "mapped"
        elif key in routes:
            st = f"routed → {routes[key].get('layer')}"
        elif key in harvested_keys:
            st = "harvested (universal — write a mapping for precision)"
        else:
            st = "uncategorized (summarized)"
        lines.append(f"- `{key}` — {st}")
    if harvested:
        lines.append("\n## Needs a mapping (self-adapt)\n\nThe universal harvester "
                     "rescued these files generically (data not lost). For precise "
                     "field mapping, add a rule to a source mapping JSON under "
                     "`engine/mappings/sources/<name>.json` (or a `--mappings` "
                     "override dir) — no Python needed. Detected shapes:")
        for key, shape, hits in sorted(harvested):
            lines.append(f"- `{key}` — {hits} records · shape: {shape}")
    if uncategorized:
        lines.append("\n## Adaptation opportunity\n\nUncategorized files were summarized "
                     "generically. To map them, add a mapping JSON rule (preferred) or "
                     "`file_routes`/`extra_aliases` to `mapping_overrides.json`, and re-run.")
    write(out / "_COVERAGE.md", "\n".join(lines))
    # return the same numbers the coverage line reports, so the seed summary
    # (_SUMMARY.md) stays consistent without recomputing them.
    return {"total": total, "quar": quar, "leveraged": leveraged,
            "uncategorized": len(uncategorized), "needs_mapping": len(harvested)}


def write_seed_summary(out: Path, col, sources_used, subj, emit_list, stats):
    """Write `_SUMMARY.md` — a human snapshot of what this build SEEDED into the
    brain: sources, the coverage line, and a per-layer note-count table. It's a
    pure post-pass over the rendered vault (counts `*.md` per layer dir), written
    alongside `_COVERAGE.md` / `_BUILD_REPORT.md` so "what's in my brain" is
    answerable at a glance. `stats` is the dict returned by
    build_uncategorized_and_coverage (None-safe)."""
    # count notes per top-level layer dir, plus root-level notes (Home, guide, reports)
    layer_counts = []
    total_md = 0
    for child in sorted(out.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            n = sum(1 for _ in child.rglob("*.md"))
            if n:
                layer_counts.append((child.name, n)); total_md += n
    total_md += sum(1 for _ in out.glob("*.md"))   # Home.md, CLAUDE.md/AGENTS.md, _*.md
    ent = getattr(col, "entity_name", "") or col.subject_entity or subj
    lines = [f"# Brain seed summary — {ent}".rstrip(), "",
             f"Built: {TODAY} · subject: {subj} · provider: {PROVIDER} · "
             f"emitters: {', '.join(emit_list)}",
             f"Sources: **{', '.join(sources_used) or 'none (generic catch-all)'}**", ""]
    if stats:
        lines += [f"Coverage: **{stats['leveraged']}/{max(stats['total'] - stats['quar'], 0)}** "
                  f"importable files leveraged ({stats['uncategorized']} uncategorized, "
                  f"{stats['quar']} quarantined, {stats['needs_mapping']} need a mapping).", ""]
    lines += ["## Notes per layer", "", "| Layer | Notes |", "|---|---|"]
    for name, n in layer_counts:
        lines.append(f"| `{name}/` | {n} |")
    lines.append(f"| **total** | **{total_md}** |")
    lines += ["",
              f"Key buckets — people: **{len(col.people)}** · organizations: "
              f"**{len(col.orgs)}** · places: **{len(col.places)}** · interests: "
              f"**{len(col.interests)}** · posts: **{len(col.posts)}** · message "
              f"correspondents: **{len(col.msg_signal)}** (signal only, no bodies).", "",
              "_Generated by build_vault.py alongside `_COVERAGE.md` / `_BUILD_REPORT.md`._"]
    write(out / "_SUMMARY.md", "\n".join(lines))
    return total_md

def dump_owner_records(out: Path, file_index, consumed_keys):
    """FULL mode only: render the files that the normal build deliberately leaves
    out — the quarantine-class personal records (the OWNER's own Email Addresses,
    PhoneNumbers, Logins, Receipts, Security Challenges, Registration, …) plus any
    unmapped file — into `00-me/` as full tables. Everything else (Connections,
    Positions, posts, searches, …) is already a proper note, so we do NOT dump it
    again — no redundant parallel tree. These are about YOU, so they live in
    identity. Local only; vault/ is git-ignored."""
    quar = _quar()
    me = out / "00-me"
    written = []
    for key in sorted(file_index):
        # only the records the normal build skipped
        if key not in quar and key in consumed_keys:
            continue
        if key not in quar and key not in consumed_keys:
            # unmapped non-sensitive files are already summarized in 99-uncategorized
            continue
        p = file_index[key][0]
        try:
            if p.suffix.lower() != ".csv":
                continue
            allrows = []
            for pp in file_index[key]:
                allrows.extend(read_csv(pp))
            if not allrows:
                continue
            headers = [h for h in allrows[0].keys() if h is not None]
            body = [f"# {p.stem} (your own records) 🔒\n",
                    f"*{len(allrows)} rows · captured because you built with "
                    f"`--full`. This is your own account data; keep it private.*\n"]
            body.append("| " + " | ".join(headers) + " |")
            body.append("| " + " | ".join("---" for _ in headers) + " |")
            for rrow in allrows:
                cells = [str(rrow.get(h, "") or "").replace("|", "\\|").replace("\n", " ")
                         for h in headers]
                body.append("| " + " | ".join(cells) + " |")
            write(me / f"my-{slug(p.stem)}.md", "\n".join(body))
            written.append(p.stem)
        except Exception:
            continue
    return written


def _build_one(mods, root, file_index, all_paths, out, subj, emit_names, full,
               owned_elsewhere=None):
    """Collect from a set of adapters into one Collector and emit one brain at
    `out`, rooted on `subj`. Returns (collector, [source names], consumed_keys).
    `owned_elsewhere` = keys consumed by a sibling brain, so they're not dumped
    as uncategorized here."""
    col = Collector(full=full)
    col.structure_spec = STRUCTURE      # carry spec on the instance (see scaffolding)
    col.provider = PROVIDER             # carry provider on the instance (see _prov)
    col.min_org_refs = MIN_ORG_REFS     # carry org-trim threshold on the instance
    col.file_keys = set(file_index)     # for the company data-handling note
    consumed_keys = set()
    sources_used = []
    for mod in mods:
        sources_used.append(mod.NAME)
        if mod.NAME == "linkedin":
            # linkedin uses file_index prefixes; guarded so one bad adapter can't
            # kill the whole build (self-heal: continue with the other sources).
            ck = selfheal.guarded_extract(
                mod, lambda m=mod: m.extract(root, file_index, col), col, log=print)
            consumed_keys |= {k for k in file_index
                              if any(k == c or k.startswith(c) for c in ck)}
        else:
            ck = selfheal.guarded_extract(
                mod, lambda m=mod: m.extract(root, file_index, all_paths, col),
                col, log=print)
            consumed_keys |= set(ck)

    col.subject = subj
    if subj == "person" and not col.subject_entity:
        col.subject_entity = col.identity.get("name", "")

    import emitters as _emitters
    chosen = _emitters.select(emit_names) or _emitters.select("obsidian")
    meta = {"sources": sources_used, "subject": subj}
    if len(chosen) == 1:
        chosen[0].emit(col, out, subject=subj, meta=meta)
        cov_dir = out
    else:
        for em in chosen:
            em.emit(col, out / em.name, subject=subj, meta=meta)
        cov_dir = out / "obsidian" if any(e.name == "obsidian" for e in chosen) else out

    stats = build_uncategorized_and_coverage(col, cov_dir, file_index, all_paths,
                                             consumed_keys, sources_used, owned_elsewhere)
    if full:
        dump_owner_records(cov_dir, file_index, consumed_keys)
    write(cov_dir / "_BUILD_REPORT.md", "# Build report\n\n" + f"Built: {TODAY}\n\n"
          f"Subject: {subj} · Emitters: {', '.join(e.name for e in chosen)}\n\n"
          f"Sources: {', '.join(sources_used) or 'none'}\n\n## Log\n" +
          "\n".join(f"- {l}" for l in col.log))
    # seed-counts snapshot (per-layer note counts + coverage) for a quick read
    write_seed_summary(cov_dir, col, sources_used, subj,
                       [e.name for e in chosen], stats)
    return col, sources_used, consumed_keys


# Folder names the repo ships as rename-me templates (data/personal/your-name,
# data/company/your-company). If a user drops a real export in WITHOUT renaming,
# run_multi names the brain after the detected identity instead (see below).
PLACEHOLDER_ENTITIES = {"your-name", "your-company"}


def discover_entities(root: Path):
    """If `root` uses the named-entity layout (personal/<name>/… and/or
    company/<name>/…), return a list of {kind, name, path}. A child dir is treated
    as a template (not an entity) and skipped when it has no recognizable data — so
    the shipped `personal/your-name/` and `company/your-company/` placeholders (only
    READMEs) are ignored until a real export is added. A name starting with '_' or
    '.' is always skipped. Returns [] if `root` is a plain single export (back-compat
    — caller falls back to run())."""
    entities = []
    for kind, sub in (("person", "personal"), ("company", "company")):
        base = root / sub
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            idx, _ = index_files(child)
            if idx:                       # only count folders that hold real data
                entities.append({"kind": kind, "name": child.name, "path": child})
    return entities


def run_multi(root: Path, out: Path, emit_names="obsidian", full=False, correlate=True):
    """Multi-entity orchestrator: build one brain per named entity under
    personal/<name> + company/<name>, then (if ≥2 entities) a cross-entity
    correlation vault. Falls back to single-brain run() when there are no entity
    folders. Returns (entities, [collectors])."""
    entities = discover_entities(root)
    if not entities:
        col, used = run(root, out, emit_names=emit_names, subject="auto", full=full)
        return [], [col]

    print(f"Discovered {len(entities)} entit{'y' if len(entities)==1 else 'ies'}: "
          + ", ".join(f"{e['kind']}:{e['name']}" for e in entities))
    cols = []
    for e in entities:
        target = out / e["kind"] if False else out / ("personal" if e["kind"] == "person"
                                                       else "company") / f"{e['name']}-brain"
        # Guard per-entity TARGET, not the shared `out` root: `out` legitimately
        # holds sibling brains, a `_profile/`, `_correlations/`, and unrelated user
        # content (e.g. an Obsidian config), so emptiness must be judged per brain.
        if target.exists() and any(target.iterdir()):
            print(f"  ! {target} exists and is not empty — skipping {e['name']} "
                  f"(remove it or use a fresh -o dir)")
            continue
        fi, ap_ = index_files(e["path"])
        srcs = detect_sources(fi)
        mods = [m for m in srcs
                if (getattr(m, "SUBJECT", "person") == "company") == (e["kind"] == "company")]
        if not mods:
            mods = srcs                   # fall back to whatever matched
        col, used, _ = _build_one(mods, e["path"], fi, ap_, target,
                                  e["kind"], emit_names, full)
        name = e["name"]
        # Graceful fallback: a user may drop a real export into the shipped template
        # folder (your-name/ · your-company/) WITHOUT renaming it. Rather than ship a
        # "your-name-brain", name the brain after the detected identity and tell them
        # to rename the data folder. (The in-vault content already uses the identity
        # name, not the folder name, so renaming the dir afterward is safe.)
        if name.lower().replace("_", "-") in PLACEHOLDER_ENTITIES:
            real = (col.subject_entity or col.identity.get("name", "") or "").strip()
            slug = re.sub(r"[^a-z0-9]+", "-", real.lower()).strip("-")
            folder = "personal" if e["kind"] == "person" else "company"
            if slug and not (target.parent / f"{slug}-brain").exists():
                new_target = target.parent / f"{slug}-brain"
                target.rename(new_target); target = new_target
                print(f"  ⚠ '{name}/' is the rename-me template folder — built the brain "
                      f"as '{slug}-brain' from the detected identity \"{real}\". "
                      f"Tip: rename data/{folder}/{name} → data/{folder}/{slug} to make it explicit.")
                name = slug
            else:
                print(f"  ⚠ '{name}/' is the rename-me template folder — rename "
                      f"data/{folder}/{name} to your real name/company so the brain "
                      f"isn't called '{name}-brain'.")
        col.entity_name = name; col.entity_kind = e["kind"]
        col.entity_vault = target
        cols.append(col)
        print(f"  ✓ {e['kind']}:{name} → {target}")

    if correlate and len(cols) >= 2:
        import correlate as _corr
        _corr.build_correlations(cols, out / "_correlations", PROVIDER)
        print(f"  ✓ correlations → {out / '_correlations'}")

    # top-level index of every entity brain, so `vault/_SUMMARY.md` answers "what did
    # this seed produce" across all brains at a glance — with sources, the key buckets,
    # and grand totals (not just a note count).
    if cols:
        def _notes(c):
            bdir = getattr(c, "entity_vault", out)
            return sum(1 for _ in Path(bdir).rglob("*.md")) if Path(bdir).is_dir() else 0
        tot = {k: 0 for k in ("notes", "people", "orgs", "places", "posts", "interests", "mirror")}
        rows = []
        for c in cols:
            bdir = getattr(c, "entity_vault", out)
            rel = bdir.relative_to(out) if str(bdir).startswith(str(out)) else bdir
            n = _notes(c)
            mir = len(getattr(c, "mirror_inferences", [])) + len(getattr(c, "ad_segments", []))
            # "harvested" is the universal-harvester pseudo-source, not a real export
            srcs = ", ".join(sorted(s for s in c.sources if s != "harvested")) or "—"
            rows.append((c.entity_name, c.entity_kind, srcs, rel, n, len(c.people),
                         len(c.orgs), len(c.places), len(c.posts), len(c.interests), mir))
            tot["notes"] += n; tot["people"] += len(c.people); tot["orgs"] += len(c.orgs)
            tot["places"] += len(c.places); tot["posts"] += len(c.posts)
            tot["interests"] += len(c.interests); tot["mirror"] += mir
        idx = ["# Vault seed summary", "",
               f"Built: {TODAY} · **{len(cols)}** entity brain(s) · "
               f"**{tot['notes']:,}** total notes.", "",
               "One brain per entity under `personal/` + `company/`"
               + (" · cross-entity links in `_correlations/`" if len(cols) >= 2 else "")
               + ". Each brain carries its own `_STRUCTURE.md` (the map), `_SUMMARY.md` "
               "(per-layer counts + coverage), `_DATA_POINTS.md` (every data point + relation "
               "+ which source enriched it), `Dashboard.md`, and `_GRAPH.md`.", "",
               "| Entity | Kind | Sources | Brain | Notes | People | Orgs | Places | Posts | Interests | Mirror |",
               "|---|---|---|---|--:|--:|--:|--:|--:|--:|--:|"]
        for (name, kind, srcs, rel, n, ppl, org, plc, po, intr, mir) in rows:
            idx.append(f"| {name} | {kind} | {srcs} | `{rel}/` | {n:,} | {ppl:,} | {org:,} | "
                       f"{plc:,} | {po:,} | {intr:,} | {mir:,} |")
        if len(rows) > 1:
            idx.append(f"| **total** | | | | **{tot['notes']:,}** | **{tot['people']:,}** | "
                       f"**{tot['orgs']:,}** | **{tot['places']:,}** | **{tot['posts']:,}** | "
                       f"**{tot['interests']:,}** | **{tot['mirror']:,}** |")
        idx += ["",
                "**Mirror** = how the platforms model you (ad-interests/advertisers/inferences, "
                "`50-mirror/`). Message correspondents are signal-only (no bodies).", "",
                "_Open a brain at its `Home.md`. Per-layer detail + the coverage line are in each "
                "brain's `_SUMMARY.md`; what-goes-where is in its `_STRUCTURE.md`._"]
        write(out / "_SUMMARY.md", "\n".join(idx))
    return entities, cols


def run(root: Path, out: Path, emit_names="obsidian", subject="auto", full=False):
    """Single-export / back-compat path: build a brain (or two sibling brains)
    from a plain `root` with no named-entity folders. `--subject` forces one
    brain; `auto` builds two SIBLING vaults (personal-brain/ + company-brain/)
    when BOTH personal and company sources fire. A pre-pass computes each group's
    consumed keys so each sibling treats the other group's files as owned-
    elsewhere (not uncategorized). Returns (last collector, [source names])."""
    file_index, all_paths = index_files(root)
    if not file_index:
        print("No recognizable data files (.csv/.json/.ics) found in the export.")
        sys.exit(1)
    sources = detect_sources(file_index)
    if not sources:
        print("Could not identify the source. Supported: LinkedIn, Facebook, "
              "Instagram, Google Takeout (personal); LinkedIn Company, Google "
              "Workspace, Slack (company). Proceeding with generic catch-all only.")
    personal = [m for m in sources if getattr(m, "SUBJECT", "person") != "company"]
    company = [m for m in sources if getattr(m, "SUBJECT", "person") == "company"]

    # Decide brains to build. `--subject` forces a single brain; `auto` builds two
    # SIBLING vaults when BOTH personal and company sources fired (clean split).
    if subject == "person":
        plan_ = [("person", sources, out)]
    elif subject == "company":
        plan_ = [("company", sources, out)]
    elif personal and company:
        print("Detected BOTH personal and company sources → building two sibling "
              "vaults: personal-brain/ + company-brain/")
        plan_ = [("person", personal, out / "personal-brain"),
                 ("company", company, out / "company-brain")]
    else:
        subj = "company" if company else "person"
        plan_ = [(subj, sources, out)]

    # first pass: compute each group's consumed keys so each sibling can treat the
    # OTHER group's files as owned-elsewhere (not uncategorized). Cheap second
    # build = the real one; we compute owned-sets by a throwaway collect per group.
    def _consumed(mods):
        # throwaway collect (log silenced) just to learn which keys this group claims
        c = Collector(full=full); c.file_keys = set(file_index)
        ck = set()
        for mod in mods:
            if mod.NAME == "linkedin":
                got = selfheal.guarded_extract(mod, lambda m=mod: m.extract(root, file_index, c), c, log=lambda *_: None)
                ck |= {k for k in file_index if any(k == x or k.startswith(x) for x in got)}
            else:
                got = selfheal.guarded_extract(mod, lambda m=mod: m.extract(root, file_index, all_paths, c), c, log=lambda *_: None)
                ck |= set(got)
        return ck
    owned = {}
    if len(plan_) > 1:
        by_subj = {subj: mods for subj, mods, _ in plan_}
        consumed_by = {subj: _consumed(mods) for subj, mods in by_subj.items()}
        for subj in by_subj:
            owned[subj] = set().union(*(v for s, v in consumed_by.items() if s != subj)) if len(consumed_by) > 1 else set()

    last_col, all_used = None, []
    for subj, mods, target in plan_:
        col, used, _ = _build_one(mods, root, file_index, all_paths, target,
                                  subj, emit_names, full, owned.get(subj))
        last_col, all_used = col, all_used + used
    return last_col, all_used

def plan(root: Path):
    """--dry-run: detect sources and print a build plan (file counts + detected
    sources) WITHOUT writing any vault."""
    file_index, all_paths = index_files(root)
    sources = detect_sources(file_index)
    print(f"Files found: {len(file_index)} data files")
    print(f"Sources detected: {', '.join(m.NAME for m in sources) or 'none'}")
    print(f"Total files on disk: {len(all_paths)}")

def vault_guide(prov=None):
    """The in-vault agent guide, written to the provider's guide filename
    (CLAUDE.md for Claude, AGENTS.md for OpenAI/Codex). Same guidance either way —
    only the addressed agent name differs."""
    agent = (prov or _provider())["agent"]
    return f"""# Working in this vault — built by Second Brain Link (secondbrainlink.com)

Guide for {agent} (and any coding agent). A digital-twin vault built from one or
more data exports. Each note's `sources` property says where it came from. The
value is in connections, voice, and intent — not raw storage.

## Read order (this keeps you efficient)
1. `Home.md` is the map of content; `_STRUCTURE.md` maps every folder/file + its
   role; `_SUMMARY.md` has the seed counts; `_DATA_POINTS.md` (if present) catalogs
   every node type + relation + which source enriched each field; `Dashboard.md` has
   live Dataview tables; `90-synthesis/` + `95-goals/` notes summarize each
   layer / goal — read those before raw layers.
2. Read a note's frontmatter (Properties) before its body. Filter by `type`,
   `status`, `company`, `tags`, `sources`, `last_contact` to find what's relevant
   WITHOUT opening every file. Every note is tagged `source/<name>` + its type (and
   semantic tags like `person/friend`, `place/check-in`, `mirror/ad-segment`), so you
   can scope queries by source and kind across all networks.
3. For network questions read `network-map.md` first. There may be thousands of
   person notes — never read them all. Note titles equal entity names, so
   `[[Acme]]` resolves and the graph reflects real relationships. People with
   multiple `sources` (multiple `source/*` tags) are the strongest multi-context ties.
   `_GRAPH.md` explains the cross-source global graph (colored by source + type).

## Hard privacy rules
- NEVER read `_quarantine/`. Never surface anyone's email, phone, or private
  message body — that data was deliberately kept out of this vault.

## Drafting
- Ground voice in `30-voice/` + `90-synthesis/positions-i-hold.md`; never invent
  opinions the user hasn't expressed. Keep new links tight.
"""

def main():
    """CLI entry point. Parses flags (--provider/--emit/--subject/--full/
    --structure/--overrides/--doctor/--dry-run/--gbrain-import/--no-correlate/
    --mappings), unpacks a .zip source if needed, then dispatches: doctor /
    dry-run / multi-entity run_multi (when entity folders are present and subject
    is auto) / single-export run. --mappings rebuilds the live source registry
    BEFORE detection so the override mappings win. Sets the module globals
    (PROVIDER/STRUCTURE/OVERRIDES) that get carried onto each Collector. The only
    networked step is the opt-in, PATH-gated --gbrain-import handoff at the end."""
    global OVERRIDES, STRUCTURE, PROVIDER, MIN_ORG_REFS
    ap = argparse.ArgumentParser(description="Build a multi-source digital-twin vault.")
    ap.add_argument("source")
    ap.add_argument("-o", "--output", default="second-brain-vault")
    ap.add_argument("--provider", default="claude", choices=sorted(PROVIDERS),
                    help="which agent the in-vault guide is written for "
                         "(claude→CLAUDE.md, openai→AGENTS.md). Default claude.")
    ap.add_argument("--overrides", default=None)
    ap.add_argument("--structure", default=None,
                    help="brain_structure.json from the profile step; lays the vault "
                         "out per the designed (pruned-canonical) spec.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Detect sources and report a plan without writing the vault.")
    ap.add_argument("--doctor", action="store_true",
                    help="Run a preflight health check (writes _DOCTOR.md) and exit.")
    ap.add_argument("--emit", default="obsidian",
                    help="output target(s): obsidian (default) | gbrain | both")
    ap.add_argument("--subject", default="auto", choices=["auto", "person", "company"],
                    help="root the brain on a person or a company (default: auto-detect)")
    ap.add_argument("--full", action="store_true",
                    help="FULL-FIDELITY / owner mode — capture EVERYTHING (emails, "
                         "phones, every extra column, sensitive files) into your own "
                         "local brain. Off by default (privacy-safe). Local only; "
                         "never committed (vault/ is git-ignored).")
    ap.add_argument("--gbrain-import", action="store_true",
                    help="after emitting a gbrain repo, shell out to `gbrain import "
                         "<dir>` IF the gbrain CLI is on PATH (opt-in; the only "
                         "non-core/networked step; no-ops with a message otherwise).")
    ap.add_argument("--no-correlate", action="store_true",
                    help="skip the cross-entity _correlations/ vault (multi-entity only)")
    ap.add_argument("--min-org-refs", type=int, default=1, metavar="N",
                    help="declutter: organizations referenced by fewer than N people "
                         "AND with no metadata are filed under 15-organizations/_mentions/ "
                         "instead of the main list (links still resolve). Default 1 = keep "
                         "all in the main folder. Try 2 to tuck one-off company mentions away.")
    ap.add_argument("--mappings", action="append", default=[],
                    help="extra mapping dir(s) with sources/<name>.json and/or "
                         "brain/layout.json that override/extend the shipped mappings "
                         "(repeatable; later wins). No Python needed to add a source.")
    args = ap.parse_args()
    PROVIDER = args.provider
    MIN_ORG_REFS = max(1, args.min_org_refs)
    if args.mappings:
        _sources.register_mappings(args.mappings)   # rebuild registry (mapping-wins)
        try:
            import diagrams, mapping as _mp
            diagrams.apply_layout(_mp.load_brain_layout(args.mappings))
        except Exception:
            pass

    if args.structure:
        try:
            STRUCTURE = json.loads(Path(args.structure).expanduser().read_text(encoding="utf-8"))
            print(f"Loaded brain structure: {len(STRUCTURE.get('layers', []))} layers "
                  f"({STRUCTURE.get('taxonomy','')})")
        except Exception as e:
            print(f"Could not read --structure ({e}); building with default layout.")

    if args.overrides:
        try:
            data = json.loads(Path(args.overrides).expanduser().read_text(encoding="utf-8"))
            OVERRIDES["extra_aliases"] = data.get("extra_aliases", [])
            OVERRIDES["file_routes"] = {norm_file(k): v for k, v in data.get("file_routes", {}).items()}
            print(f"Loaded overrides: {len(OVERRIDES['extra_aliases'])} aliases, "
                  f"{len(OVERRIDES['file_routes'])} file routes")
        except Exception as e:
            print(f"Could not read overrides ({e}); continuing with defaults.")

    src = Path(args.source).expanduser()
    tmp = None
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp())
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        work = tmp
    elif src.is_dir():
        work = src
    else:
        print("Source must be a .zip file or a folder."); sys.exit(1)

    try:
        if args.doctor:
            status = selfheal.doctor(work, Path(args.output).expanduser(),
                                     detect_sources=detect_sources, index_files=index_files)
            print(f"doctor: {status} → {Path(args.output).expanduser()/'_DOCTOR.md'}")
            return
        if args.dry_run:
            plan(work)
            return
        out = Path(args.output).expanduser()
        # multi-entity (personal/<name> + company/<name>) when present, else
        # back-compat single brain. --subject forces the single-brain path.
        use_multi = args.subject == "auto" and bool(discover_entities(work))
        # The single-brain path writes straight into `out`, so it must be empty.
        # The multi-entity path writes into per-entity subdirs (guarded in
        # run_multi), so `out` may already hold a _profile/ or other brains.
        if not use_multi and out.exists() and any(out.iterdir()):
            print(f"Output '{out}' exists and is not empty. Use a fresh dir."); sys.exit(1)
        try:
            if use_multi:
                multi_ents, _ = run_multi(work, out, emit_names=args.emit,
                                          full=args.full, correlate=not args.no_correlate)
                col, sources_used = None, []
            else:
                col, sources_used = run(work, out, emit_names=args.emit,
                                        subject=args.subject, full=args.full)
        except Exception as e:
            rep = selfheal.write_error_report(out, "build_vault", e)
            print(f"\n❌ Build failed: {type(e).__name__}: {e}")
            print(f"   Structured fix report → {rep}")
            print(f"   ({_provider()['agent']}: read _ERROR.md, apply the fix, "
                  "mirror to the installed copy, re-run.)")
            sys.exit(1)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    # optional opt-in GBrain handoff (the ONLY non-core/possibly-networked step)
    if args.gbrain_import and ("gbrain" in args.emit or args.emit == "both"):
        gdir = out if args.emit == "gbrain" else out / "gbrain"
        if shutil.which("gbrain"):
            import subprocess
            print(f"→ gbrain import {gdir}")
            try:
                subprocess.run(["gbrain", "import", str(gdir)], check=False)
            except Exception as e:
                print(f"   gbrain import failed ({e}); the repo is still at {gdir}.")
        else:
            print(f"   --gbrain-import set but `gbrain` not on PATH; skipped. "
                  f"The importable repo is at {gdir} (run `gbrain import` yourself).")

    if col is not None:
        print("\n".join(col.log))
    print(f"\n✅ Second Brain Link — vault built at: {out.resolve()}")
    if use_multi:
        # multi-entity: per-entity sources live in each brain's _BUILD_REPORT.md
        print(f"   Built {len(multi_ents)} entity brain(s) under "
              f"{out}/personal|company/ (+ _correlations/ when ≥2 entities). "
              f"See each brain's _BUILD_REPORT.md for its sources.")
    else:
        print(f"   Sources: {', '.join(sources_used) or 'none (generic catch-all)'}")
    print(f"   Open the folder in Obsidian (start at Home.md), then point "
          f"{_provider()['agent']} at it.")

if __name__ == "__main__":
    main()
