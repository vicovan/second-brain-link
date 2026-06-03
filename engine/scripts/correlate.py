#!/usr/bin/env python3
"""
correlate.py — cross-entity correlation vault.

After per-entity brains are built (one Collector each, for each
personal/<identity> and company/<company>), this links them into a single
`_correlations/` brain:

  - people/<name>.md  — a person who appears in ≥2 entity brains becomes ONE
    cross-note that links into each brain and lists their role/company per entity.
  - orgs/<org>.md     — an organization referenced by ≥2 entities.
  - edges.md          — identity↔company edges (works_at / employs / founded)
    derived deterministically (a person-entity's Positions name a company that is
    also a company-entity, or a company-entity lists that person as an employee).
  - Home.md + the provider agent-guide.

Deterministic + precision-biased: people are matched by normalized name AND, when
both have one, a matching canonical profile URL (a URL mismatch blocks the merge —
a wrong cross-merge is worse than a miss). Reuses helpers from sources/common.py.
"""
from collections import defaultdict
# correlate.py is imported as a top-level module (scripts dir is on sys.path),
# so reach the helpers via the sources package.
from sources.common import nk, canonical_url, obsidian_name


def _link_into(vault_path, layer, title):
    """An Obsidian path-link into a sibling vault, relative to _correlations/.
    e.g. ../personal/grace-brain/10-people/Ada Lovelace"""
    if not vault_path:
        return f"[[{obsidian_name(title)}]]"
    rel = f"../{vault_path.parent.name}/{vault_path.name}/{layer}/{obsidian_name(title)}"
    return f"[{obsidian_name(title)}]({rel}.md)"


def _fm(d):
    """Render dict `d` as a YAML frontmatter block (--- fenced). List/set values
    become a block sequence (sets sorted for stable output); scalars become
    `key: value`."""
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, (list, set)):
            v = sorted(v) if isinstance(v, set) else v
            out.append(f"{k}:")
            for it in v:
                out.append(f"  - {it}")
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    return "\n".join(out)


def _write(path, text):
    """Write a note to `path`, creating parent dirs and normalizing to a single
    trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def build_correlations(collectors, out, provider="claude"):
    """collectors: list of built Collector objects (each with entity_name/kind/
    entity_vault). Writes the _correlations/ vault at `out`."""
    out.mkdir(parents=True, exist_ok=True)

    # ---- index people across entities -------------------------------------
    # key: (nk(name)) -> {url-> set, appearances: [(entity, kind, vault, rec)]}
    people = defaultdict(lambda: {"urls": set(), "appear": []})
    for c in collectors:
        ent = c.entity_name or c.subject_entity or "?"
        for key, r in c.people.items():
            people[key]["appear"].append((ent, c.entity_kind, c.entity_vault, r))
            if r.get("url"):
                people[key]["urls"].add(r["url"])
        # the entity's OWN identity is also a "person" for cross-linking
        if c.entity_kind == "person" and c.identity.get("name"):
            k = nk(c.identity["name"])
            people[k]["appear"].append((ent, "person-self", c.entity_vault,
                                        {"name": c.identity["name"],
                                         "role": c.identity.get("headline", ""),
                                         "company": "", "url": c.identity.get("url", "")}))

    # cross-people = appear in ≥2 distinct entities, and (precision) no conflicting URL
    cross_people = []
    for key, info in people.items():
        ents = {a[0] for a in info["appear"]}
        if len(ents) < 2:
            continue
        if len(info["urls"]) > 1:        # conflicting profile URLs → don't merge
            continue
        cross_people.append((key, info))

    # ---- index orgs across entities ---------------------------------------
    orgs = defaultdict(lambda: {"appear": []})
    for c in collectors:
        ent = c.entity_name or c.subject_entity or "?"
        for name in c.companies:
            orgs[nk(name)]["appear"].append((ent, c.entity_kind, c.entity_vault, name))
    cross_orgs = [(k, v) for k, v in orgs.items()
                  if len({a[0] for a in v["appear"]}) >= 2]

    # ---- identity ↔ company edges -----------------------------------------
    company_names = {nk(c.entity_name): c for c in collectors if c.entity_kind == "company"}
    edges = []  # (person_entity, predicate, company_entity, detail)
    for c in collectors:
        if c.entity_kind != "person":
            continue
        for pos in c.identity.get("positions", []):
            comp = pos.get("company", "")
            ck = nk(comp)
            # match a company-entity by name (folder) OR by the company's own org name
            match = company_names.get(ck)
            if not match:
                for cc in company_names.values():
                    if nk(cc.subject_entity) == ck or comp and nk(cc.subject_entity) and (
                            ck in nk(cc.subject_entity) or nk(cc.subject_entity) in ck):
                        match = cc; break
            if match:
                edges.append((c.entity_name, "works_at", match.entity_name,
                              pos.get("title", "")))
    # NOTE: we deliberately DON'T infer edges from a company's people list — that
    # list mixes employees, followers, and contacts, so it can't ground a precise
    # "employed_by". A person's OWN Positions (above) is the authoritative signal.

    # ---- write people cross-notes -----------------------------------------
    for key, info in cross_people:
        # pick a display name (first non-empty)
        name = next((a[3].get("name") for a in info["appear"] if a[3].get("name")), key)
        lines = [_fm({"type": "correlation-person", "title": obsidian_name(name),
                      "tags": ["correlation", "person"],
                      "appears_in": sorted({a[0] for a in info["appear"]})}),
                 "", f"# {name}", "",
                 "Appears across multiple brains:", ""]
        for ent, kind, vault, r in info["appear"]:
            role = r.get("role", ""); comp = r.get("company", "")
            sub = f" — {role}" + (f" at {comp}" if comp else "") if role or comp else ""
            lines.append(f"- **{ent}** ({kind}): "
                         + _link_into(vault, "10-people", name) + sub)
        if info["urls"]:
            lines += ["", f"Profile: {sorted(info['urls'])[0]}"]
        _write(out / "people" / f"{obsidian_name(name)}.md", "\n".join(lines))

    # ---- write org cross-notes --------------------------------------------
    for key, v in cross_orgs:
        name = v["appear"][0][3]
        lines = [_fm({"type": "correlation-org", "title": obsidian_name(name),
                      "tags": ["correlation", "company"],
                      "referenced_by": sorted({a[0] for a in v["appear"]})}),
                 "", f"# {name}", "", "Referenced across:", ""]
        for ent, kind, vault, nm in v["appear"]:
            lines.append(f"- **{ent}** ({kind}): " + _link_into(vault, "15-organizations", nm))
        _write(out / "orgs" / f"{obsidian_name(name)}.md", "\n".join(lines))

    # ---- edges note --------------------------------------------------------
    if edges:
        uniq = sorted(set(edges))
        lines = [_fm({"type": "correlation-edges", "title": "Identity ↔ company edges",
                      "tags": ["correlation", "edges"]}),
                 "", "# Identity ↔ company edges", ""]
        for a, pred, b, detail in uniq:
            d = f" ({detail})" if detail else ""
            lines.append(f"- **{a}** —{pred}→ **{b}**{d}")
        _write(out / "edges.md", "\n".join(lines))

    # ---- Home + guide ------------------------------------------------------
    guides = {"claude": "CLAUDE.md", "openai": "AGENTS.md"}
    home = [_fm({"type": "moc", "title": "Correlations", "tags": ["moc", "correlation"],
                 "entities": sorted(c.entity_name for c in collectors)}),
            "", "# 🔗 Correlations", "",
            f"Links across **{len(collectors)}** brains "
            f"({', '.join(sorted((c.entity_kind+':'+c.entity_name) for c in collectors))}).", "",
            f"- **{len(cross_people)}** people appear in more than one brain → `people/`",
            f"- **{len(cross_orgs)}** organizations referenced by more than one → `orgs/`",
            f"- **{len(set(edges))}** identity↔company edges → `edges.md`", "",
            "Each cross-note links into the per-entity brains under `../personal/<id>-brain/` "
            "and `../company/<co>-brain/`. Open the whole `vault/` in Obsidian; the graph "
            "view spans every brain.", ""]
    _write(out / "Home.md", "\n".join(home))
    _write(out / guides.get(provider, "CLAUDE.md"),
           "# Correlations vault\n\nCross-entity links between the per-identity and "
           "per-company brains in this vault. Start at `Home.md`. People/orgs here are "
           "*pointers* into the entity brains — read those for detail. Same privacy rules "
           "as every brain: never surface quarantined PII.\n")
    return {"people": len(cross_people), "orgs": len(cross_orgs), "edges": len(set(edges))}
