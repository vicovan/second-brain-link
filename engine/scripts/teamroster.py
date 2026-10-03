#!/usr/bin/env python3
"""
teamroster.py — a Company Brain's own team (founders, board, advisors, employees),
from sources the user already owns, when the company's exports never name them.

  1. Sibling PERSONAL brains (`--people-from DIR`, `SBL_PEOPLE_FROM`, or auto:
     `<vault>/personal/*-brain` when the company brain sits at
     `<vault>/company/<name>-brain`):
       - every `10-people/*.md` whose frontmatter `company:` names THIS company
         (exact normalized equality with the company's name or aliases — never a
         prefix/substring: "Delta" must not match "Delta Air Lines");
       - the owner's own current positions in `00-me/identity.md`
         (`- **ROLE** — [[ORG]] (… – Present)`).
  2. A roster file the user keeps beside the company's exports:
     `data/company/<name>/team.json` — `[{"name": "...", "role": "..."}, ...]`
     (or `{"people": [...]}`), for people no source names.

Only name, role and a public profile URL cross over. The owner's relationship to
the person (status, strength, last contact, connected-on) is the personal brain's
business, never the company's. Stdlib only, zero network, deterministic.
"""
import json
import os
import re
from pathlib import Path

from sources.common import nk

SOURCE = "team"
_LEGAL = re.compile(r"(?i)[,\s]+(?:inc|incorporated|llc|ltd|limited|gmbh|corp|corporation|co|plc|sa|ag|bv|srl|pte)\.?$")
_POS = re.compile(r"^\s*-\s+\*\*(?P<role>[^*]+)\*\*\s+[—–-]\s+\[\[(?P<org>[^\]|]+)(?:\|[^\]]*)?\]\]\s*\((?P<span>[^)]*)\)")
# rank of a role class: a self-reported title replaces a doc mention of equal or
# lower rank (founder > board > executive > advisor > investor > team)
_RANK = {"founder": 6, "board": 5, "executive": 4, "advisor": 3, "investor": 2, "team": 1}


def _keys(name):
    """Comparison keys for a company name: as written and without a legal suffix."""
    out = set()
    n = (name or "").strip().strip('"').strip()
    if n.startswith("[[") and n.endswith("]]"):
        n = n[2:-2].split("|")[0]
    while n:
        if nk(n):
            out.add(nk(n))
        m = _LEGAL.sub("", n).strip()
        if m == n:
            break
        n = m
    return out


def _frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def personal_brains(out, explicit=()):
    """The personal brain folders to read: explicit dirs, else siblings of `out`."""
    dirs = [Path(d).expanduser() for d in explicit if d]
    env = os.environ.get("SBL_PEOPLE_FROM", "")
    dirs += [Path(d).expanduser() for d in env.split(os.pathsep) if d]
    if not dirs and out is not None:
        out = Path(out).resolve()
        if out.parent.name == "company":
            dirs = sorted((out.parent.parent / "personal").glob("*-brain"))
    return [d for d in dirs if (d / "10-people").is_dir() or (d / "00-me").is_dir()]


def _roster(root):
    p = Path(root) / "team.json" if root else None
    if not p or not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("people", []) if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict) and str(r.get("name", "")).strip()]


def collect(company_names, brains, roster_root=None):
    """[(name, role, url, origin)] — this company's people from the brains + roster."""
    want = set()
    for n in company_names:
        want |= _keys(n)
    want.discard("")
    found = []
    if want:
        for b in brains:
            for f in sorted((b / "10-people").glob("*.md")) if (b / "10-people").is_dir() else []:
                try:
                    fm = _frontmatter(f.read_text(encoding="utf-8", errors="replace")[:4000])
                except OSError:
                    continue
                if fm.get("company") and _keys(fm["company"]) & want and fm.get("title"):
                    found.append((fm["title"], fm.get("role", ""), fm.get("url", ""), "personal-brain"))
            ident = b / "00-me" / "identity.md"
            if ident.is_file():
                text = ident.read_text(encoding="utf-8", errors="replace")
                owner = _frontmatter(text).get("title", "")
                for line in text.splitlines():
                    m = _POS.match(line)
                    if owner and m and re.search(r"(?i)present|current|now", m.group("span")) \
                            and _keys(m.group("org")) & want:
                        found.append((owner, m.group("role").strip(), _frontmatter(text).get("url", ""), "owner"))
    for r in _roster(roster_root):
        found.append((str(r["name"]).strip(), str(r.get("role", "")).strip(), str(r.get("url", "")).strip(), "roster"))
    return found


def apply(col, company_name, aliases=(), brains=(), roster_root=None):
    """Add the company's team to the Collector. Returns the number of people added
    or updated."""
    import docentities
    rows = collect([company_name, *aliases], brains, roster_root)
    for name, role, url, origin in rows:
        cls = docentities._role_class(role) if role else "team"
        before = col.people.get(nk(name))
        old_role = (before or {}).get("role", "")
        col.add_person(SOURCE, name, company=company_name, role=role, url=url,
                       tags=[f"person/{cls}", f"person/from-{origin}"])
        rec = col.people.get(nk(name))
        # deliberate exception to first-non-empty-wins: a person's OWN title (their
        # profile, or the user's roster) beats a role a document mentions in passing,
        # unless that mention is a higher-ranked role
        if rec is not None and role and old_role and nk(role) != nk(old_role) \
                and _RANK.get(cls, 1) >= _RANK.get(docentities._role_class(old_role), 1):
            rec["role"] = role
            rec.setdefault("prov", {})["role"] = SOURCE
            alts = [a for a in rec.setdefault("alt", {}).get("role", []) if nk(a[0]) != nk(role)]
            prev = (old_role, (before or {}).get("prov", {}).get("role", "docs"))
            if prev not in alts:
                alts.append(prev)
            rec["alt"]["role"] = alts
        if rec is not None and rec.get("company") and nk(rec["company"]) != nk(company_name) \
                and origin in ("personal-brain", "owner", "roster"):
            rec["company"] = company_name
    if rows:
        col.note(f"[team] {len(rows)} team member(s) from "
                 + ", ".join(sorted({o for *_, o in rows})))
    return len(rows)
