#!/usr/bin/env python3
"""
emitters/gbrain.py — OPT-IN GBrain output target.

Emits a GBrain-compatible markdown *brain repo* from the same canonical Collector,
so a user can `gbrain import <dir>` (or `gbrain sync --repo <dir>`) and bootstrap a
brain — personal OR company — from their exports. This is ADDITIVE and never the
default; Obsidian remains primary (see emitters/__init__.py).

GBrain schema note (verified against github.com/garrytan/gbrain docs + llms-full.txt,
2026-06): gbrain-base-v2 has ~15 page types (person, company, writing, tweet,
social-digest, note, project, deal, …). The docs are explicit about page `type`
frontmatter, `aliases`, `[[slug]]` wikilinks, and typed edges (works_at,
invested_in, founded, advises, attended, mentions) but DO NOT pin the on-disk
entity directory. We therefore emit the documented-safe shape:
  people/<slug>.md, companies/<slug>.md, writing/<slug>.md, notes/<slug>.md
at the repo root, with `type` + `title` + `aliases` frontmatter and `[[people/slug]]`
-style links. Typed edges are written BOTH as a `## Edges` list (human + greppable)
and inline in the body, e.g. `- works_at [[companies/acme]]`. If a future GBrain
version requires `wiki/` prefixes or a Facts-fence for edges, that's a one-line
change here — flagged in CLAUDE.md §12. We only emit edges we can ground
deterministically; we never fabricate. PII follows the Collector: default mode is
clean; `--full` carries emails/phones through just like Obsidian.
"""
import json
import re
from .base import Emitter


def _slug(s):
    """Slugify `s` for a GBrain page filename / wikilink target: lowercase, strip
    punctuation, collapse whitespace/underscores to hyphens, cap at 80 chars.
    Stable (derived from the name) so edges can target it; "untitled" if empty."""
    s = re.sub(r"[^\w\s-]", "", (s or "").strip().lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:80] or "untitled"


def _fm(d):
    """Minimal YAML frontmatter (GBrain reads standard YAML)."""
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, (list, tuple, set)):
            v = [x for x in (sorted(v) if isinstance(v, set) else v) if x]
            if v:
                out.append(f"{k}:")
                out += [f"  - {_yaml(x)}" for x in v]
            else:
                out.append(f"{k}: []")
        elif v not in (None, ""):
            out.append(f"{k}: {_yaml(v)}")
    out.append("---")
    return "\n".join(out)


def _yaml(v):
    """Render `v` as a YAML scalar, double-quoting (and escaping) it when it
    contains YAML-special characters or surrounding whitespace."""
    s = str(v)
    if re.search(r'[:#\[\]{}>|*&!%@`"\n]', s) or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


class GBrainEmitter(Emitter):
    """Opt-in emitter: writes a GBrain-compatible brain repo (people/ companies/
    writing/ notes/ + a manifest) from the same Collector. Edges are only those we
    can ground deterministically — never fabricated. PII follows the Collector
    (clean by default; --full carries emails/phones through like Obsidian)."""

    name = "gbrain"

    def emit(self, col, out_dir, *, subject="person", meta=None):
        """Emit the full GBrain repo under `out_dir`: the subject root page, one
        page per person/company, posts as writing pages, a network-overview note,
        and gbrain.manifest.json + README. Relationships are [[people/slug]] /
        [[companies/slug]] wikilinks plus typed-edge lines (e.g. works_at)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        full = getattr(col, "full", False)
        people_dir = out_dir / "people"
        comp_dir = out_dir / "companies"
        writing_dir = out_dir / "writing"
        notes_dir = out_dir / "notes"

        # person/company slugs for edge targeting (stable: derived from name)
        pslug = {key: _slug(r["name"]) for key, r in col.people.items()}
        cslug = {name: _slug(name) for name in col.companies}

        # --- root entity (the subject) -------------------------------------
        root_type = "company" if subject == "company" else "person"
        root_name = col.subject_entity or col.identity.get("name") or (
            "Company" if subject == "company" else "Me")
        root_dir = comp_dir if subject == "company" else people_dir
        ident = col.identity
        edges = []
        for pos in ident.get("positions", []):
            c = pos.get("company")
            if c:
                edges.append(f"- works_at [[companies/{_slug(c)}]] — {pos.get('title','')}".rstrip(" —"))
        body = [_fm({"type": root_type, "title": root_name,
                     "aliases": [root_name], "tags": ["self"] ,
                     "headline": ident.get("headline", ""),
                     "location": ident.get("location", ""),
                     "industry": ident.get("industry", "")}),
                "", f"# {root_name}", ""]
        if ident.get("about"):
            body += [ident["about"], ""]
        if ident.get("skills"):
            body += ["## Skills", "", ", ".join(ident["skills"][:60]), ""]
        if edges:
            body += ["## Edges", "", *edges, ""]
        self._write(root_dir / f"{_slug(root_name)}.md", body)

        # --- people --------------------------------------------------------
        for key, r in col.people.items():
            fm = {"type": "person", "title": r["name"], "aliases": [r["name"]],
                  "tags": ["person"], "sources": sorted(r["sources"])}
            if r.get("url"): fm["url"] = r["url"]
            if full and r.get("email"): fm["email"] = r["email"]
            if full and r.get("phone"): fm["phone"] = r["phone"]
            e = []
            if r.get("company"):
                e.append(f"- works_at [[companies/{_slug(r['company'])}]]"
                         + (f" — {r['role']}" if r.get("role") else ""))
            b = [_fm(fm), "", f"# {r['name']}", ""]
            if r.get("role") or r.get("company"):
                b += [f"{r.get('role','')}"
                      + (f" at [[companies/{_slug(r['company'])}]]" if r.get("company") else ""), ""]
            if e:
                b += ["## Edges", "", *e, ""]
            if full and (r.get("extra")):
                b += ["## Details", "", *[f"- **{k}:** {v}" for k, v in r["extra"].items()], ""]
            self._write(people_dir / f"{pslug[key]}.md", b)

        # --- companies -----------------------------------------------------
        for name in col.companies:
            meta_o = col.orgs.get(name, {})
            fm = {"type": "company", "title": name, "aliases": [name],
                  "tags": ["company"], "category": meta_o.get("category", "referenced"),
                  "sources": sorted(meta_o.get("sources", []))}
            if meta_o.get("url"): fm["url"] = meta_o["url"]
            self._write(comp_dir / f"{cslug[name]}.md", [_fm(fm), "", f"# {name}", ""])

        # --- writing (posts/comments → writing pages) ----------------------
        n_w = 0
        for i, p in enumerate(col.posts):
            if not p.get("text"):
                continue
            fm = {"type": "writing", "title": f"{p.get('kind','post')} {p.get('date','') or i}".strip(),
                  "tags": ["writing", p.get("kind", "post")], "date": p.get("date", ""),
                  "sources": [p.get("source", "")]}
            self._write(writing_dir / f"{_slug(fm['title'])}-{i}.md",
                        [_fm(fm), "", p["text"], ""])
            n_w += 1

        # --- a synthesis note (network overview) ---------------------------
        overview = [_fm({"type": "note", "title": "Network overview",
                         "tags": ["synthesis"]}), "", "# Network overview", "",
                    f"- people: {len(col.people)}", f"- companies: {len(col.companies)}",
                    f"- writing: {n_w}", f"- subject: {subject} ({root_name})", ""]
        self._write(notes_dir / "network-overview.md", overview)

        # --- import manifest + README -------------------------------------
        manifest = {"schema": "gbrain-base-v2 (best-effort)", "subject": subject,
                    "root": {"type": root_type, "slug": _slug(root_name)},
                    "counts": {"people": len(col.people), "companies": len(col.companies),
                               "writing": n_w}}
        (out_dir / "gbrain.manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        (out_dir / "README.md").write_text(
            "# GBrain brain repo (emitted by Second Brain Link)\n\n"
            f"Subject: **{subject}** · people {len(col.people)} · "
            f"companies {len(col.companies)} · writing {n_w}.\n\n"
            "Import with `gbrain import .` (or `gbrain sync --repo .`). Entities live "
            "in `people/`, `companies/`, `writing/`, `notes/`; relationships are "
            "`[[people/slug]]` / `[[companies/slug]]` wikilinks + typed-edge lines "
            "(e.g. `- works_at [[companies/acme]]`). Generated locally; verify "
            "against your GBrain version's schema.\n", encoding="utf-8")

    @staticmethod
    def _write(path, lines):
        """Join `lines` and write the page to `path`, creating parent dirs and
        normalizing to a single trailing newline."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
