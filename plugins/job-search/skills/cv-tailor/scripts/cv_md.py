#!/usr/bin/env python3
"""
cv_md.py - the CV content format, as Markdown.

A CV is authored as a Markdown note with YAML frontmatter, so it is readable in
Obsidian, indexable in a Second Brain vault, and diffable - instead of a nested JSON
blob nobody can read. `build_cv.py` renders it to PDF.

    python3 cv_md.py to-md   content.json  [-o out.md]
    python3 cv_md.py to-json content.md    [-o out.json]
    python3 cv_md.py check   <dir-or-glob>        # round-trip gate over real files

Two functions carry the whole mapping - keep them the only place it lives:

    content_to_md(dict) -> str
    md_to_content(str)  -> dict

Zero dependencies: the YAML this needs is a flat map of scalars plus one list of
`{text, url}`, so it is parsed and written here rather than pulling in PyYAML. A
public plugin should not need a pip install to read its own files.

## The format

    ---
    type: cv
    title: <name> - <role>
    tags: [jobsearch, cv]
    name: ...            headline: ...        output_basename: ...
    company: ...         role: ...            target_type: ...     contact_set: ...
    email/phone/location/status: ...
    links:
      - text: linkedin.com/in/someone
        url: https://www.linkedin.com/in/someone/
    ---

    ## Professional Summary
    <!-- blocks: prose -->

    Body text.

    ## Core Competencies
    <!-- blocks: kv -->

    - **Label:** value one - value two

    ## Work Experience
    <!-- blocks: mixed -->

    ### Job Title | Employer - one-line descriptor
    *05/2026 - Present*
    City, Country - what the company does
    <https://employer.example>

    - **Bold lead-in:** the rest of the bullet.
    - A bullet with no lead-in.

    #### Earlier ventures and roles

    ## Education
    <!-- blocks: entries -->

    - **Programme** - Institution — 11/2023

The `<!-- blocks: kind -->` marker disambiguates `- **X:** y`, which means a `kv`
item under Core Competencies and a `bullet` with a lead everywhere else. It is an
HTML comment, so it is invisible in every Markdown renderer, and it matches the
vault's own house style (`_SUMMARY.md` carries `<!-- analyze:goals -->`). When the
marker is missing the heading name decides, so a hand-written CV still builds.

Role meta lines are the lines *directly under* the `###` with no blank line between:
italic is the dates, `<...>` is the URL, anything else is the location/descriptor.
The blank line is what separates them from a following italic paragraph.
"""
import argparse, glob, json, os, re, sys

FM_KEYS_ORDER = ["type", "title", "tags", "name", "headline", "output_basename",
                 "company", "role", "target_type", "contact_set",
                 "email", "phone", "location", "status"]

SECTION_KIND = {           # fallback when no <!-- blocks: --> marker is present
    "core competencies": "kv",
    "education": "entries",
    "professional summary": "prose",
}


# ---------------------------------------------------------------- YAML (the subset we emit)
def _needs_quote(v):
    if v == "" or v != v.strip():
        return True
    if v[0] in "&*!|>%@`'\"[]{}#-?":
        return True
    return ": " in v or v.endswith(":") or v[0] == "+"


def _q(v):
    v = str(v)
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' if _needs_quote(v) else v


def _unq(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        body = v[1:-1]
        return body.replace('\\"', '"').replace("\\\\", "\\") if v[0] == '"' else body
    return v


def parse_frontmatter(text):
    """Return (dict, body). Handles flat scalars, `tags: [a, b]`, and the links list."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4:]
    fm, i, lines = {}, 0, raw.split("\n")
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [_unq(x) for x in val[1:-1].split(",") if x.strip()]
        elif val == "":
            items, cur = [], None
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("-")):
                sub = lines[i]
                i += 1
                if not sub.strip():
                    continue
                sm = re.match(r"^\s*-\s*([A-Za-z_][\w-]*):\s*(.*)$", sub)
                if sm:
                    cur = {sm.group(1): _unq(sm.group(2))}
                    items.append(cur)
                    continue
                sm = re.match(r"^\s*-\s+(.*)$", sub)
                if sm:
                    items.append(_unq(sm.group(1)))
                    cur = None
                    continue
                sm = re.match(r"^\s+([A-Za-z_][\w-]*):\s*(.*)$", sub)
                if sm and cur is not None:
                    cur[sm.group(1)] = _unq(sm.group(2))
            fm[key] = items if items else ""
        else:
            fm[key] = _unq(val)
    return fm, body.lstrip("\n")


def emit_frontmatter(fm):
    out = ["---"]
    for k in FM_KEYS_ORDER:
        if k not in fm:
            continue
        v = fm[k]
        if k == "tags" and isinstance(v, list):
            out.append("tags: [" + ", ".join(v) + "]")
        else:
            out.append(f"{k}: {_q(v)}")
    for k, v in fm.items():
        if k in FM_KEYS_ORDER or k == "links":
            continue
        out.append(f"{k}: {_q(v)}" if not isinstance(v, list)
                   else f"{k}: [" + ", ".join(str(x) for x in v) + "]")
    if fm.get("links"):
        out.append("links:")
        for l in fm["links"]:
            out.append(f"  - text: {_q(l.get('text', ''))}")
            out.append(f"    url: {_q(l.get('url', ''))}")
    out.append("---")
    return "\n".join(out)


# ---------------------------------------------------------------- canonicalisation
def canonicalize(content):
    """The one normalisation the format performs, applied to both sides of the gate.

    348 bullets across the real CVs, and 15 of them keep their bold lead-in inside
    `text` (`{"text": "**Doubled the org.** while introducing..."}`) rather than in
    `lead`. Both render to exactly the same `<b>lead</b> text`, so they are the same
    bullet written two ways - but only one of them survives a Markdown round trip.
    Splitting them here means the format is lossless against canonical input, and the
    change is provably invisible in the PDF.
    """
    c = json.loads(json.dumps(content))
    for sec in c.get("sections", []):
        for b in sec.get("blocks", []):
            if b.get("type") == "bullet" and not b.get("lead"):
                m = re.match(r"^\*\*(.+?)\*\*\s+(.*)$", b.get("text", ""), re.S)
                if m:
                    b["lead"], b["text"] = m.group(1), m.group(2)
    return c


# ---------------------------------------------------------------- content -> markdown
def _kind_for(heading, blocks):
    types = {b.get("type", "paragraph") for b in blocks}
    if types == {"kv"}:
        return "kv"
    if types == {"entries"}:
        return "entries"
    if types <= {"paragraph"}:
        return "prose"
    return "mixed"


def content_to_md(content):
    c = content.get("contact", {}) or {}
    t = content.get("target", {}) or {}
    name = content.get("name", "")
    role = t.get("role", "")
    fm = {
        "type": "cv",
        "title": f"{name} — {role}" if role else name,
        "tags": ["jobsearch", "cv"],
        "name": name,
        "headline": content.get("headline", ""),
        "output_basename": content.get("output_basename", ""),
        "company": t.get("company", ""),
        "role": role,
        "target_type": t.get("type", ""),
        "contact_set": t.get("contact_set", ""),
        "email": c.get("email", ""),
        "phone": c.get("phone", ""),
        "location": c.get("location", ""),
        "status": c.get("status", ""),
        "links": c.get("links", []),
    }
    out = [emit_frontmatter(fm), ""]

    for sec in content.get("sections", []):
        blocks = sec.get("blocks", [])
        kind = _kind_for(sec.get("heading", ""), blocks)
        out.append(f"## {sec.get('heading', '')}")
        out.append(f"<!-- blocks: {kind} -->")
        out.append("")
        for b in blocks:
            bt = b.get("type", "paragraph")
            if bt == "paragraph":
                out += [b.get("text", ""), ""]
            elif bt == "subheading":
                out += [f"#### {b.get('text', '')}", ""]
            elif bt == "bullet":
                lead = b.get("lead")
                out.append(f"- **{lead}** {b.get('text', '')}" if lead
                           else f"- {b.get('text', '')}")
            elif bt == "kv":
                for k, v in [(i[0], i[1]) for i in b.get("items", [])]:
                    out.append(f"- **{k}:** {v}")
                out.append("")
            elif bt == "entries":
                for l, r in [(i[0], i[1]) for i in b.get("items", [])]:
                    out.append(f"- {l} — {r}")
                out.append("")
            elif bt == "role":
                if out and out[-1] != "":
                    out.append("")
                head = b.get("title", "")
                if b.get("org"):
                    head += f" | {b['org']}"
                out.append(f"### {head}")
                if b.get("dates"):
                    out.append(f"*{b['dates']}*")
                if b.get("where"):
                    out.append(b["where"])
                if b.get("url"):
                    out.append(f"<{b['url']}>")
                out.append("")
            elif bt == "spacer":
                out += [f"<!-- spacer: {b.get('height', 4)} -->", ""]
        if out and out[-1] != "":
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- markdown -> content
def md_to_content(text):
    fm, body = parse_frontmatter(text)
    content = {
        "output_basename": fm.get("output_basename", ""),
        "target": {"company": fm.get("company", ""), "role": fm.get("role", ""),
                   "type": fm.get("target_type", ""), "contact_set": fm.get("contact_set", "")},
        "name": fm.get("name", ""),
        "headline": fm.get("headline", ""),
        "contact": {"email": fm.get("email", ""), "phone": fm.get("phone", ""),
                    "location": fm.get("location", ""), "status": fm.get("status", ""),
                    "links": fm.get("links", []) or []},
        "sections": [],
    }
    lines = body.split("\n")
    sec = None
    kind = "mixed"
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("## ") and not stripped.startswith("### "):
            sec = {"heading": stripped[3:].strip(), "blocks": []}
            content["sections"].append(sec)
            kind = SECTION_KIND.get(sec["heading"].lower(), "mixed")
            i += 1
            if i < len(lines):
                m = re.match(r"^\s*<!--\s*blocks:\s*(\w+)\s*-->\s*$", lines[i])
                if m:
                    kind = m.group(1)
                    i += 1
            continue

        if sec is None or not stripped:
            i += 1
            continue

        if stripped.startswith("### "):
            role = {"type": "role", "title": stripped[4:].strip()}
            if " | " in role["title"]:
                role["title"], role["org"] = [x.strip() for x in role["title"].split(" | ", 1)]
            i += 1
            # meta lines are the ones directly under the header, before any blank line
            while i < len(lines) and lines[i].strip():
                meta = lines[i].strip()
                if re.match(r"^\*[^*].*\*$", meta):
                    role["dates"] = meta[1:-1]
                elif re.match(r"^<https?://[^>]+>$", meta):
                    role["url"] = meta[1:-1]
                else:
                    role["where"] = meta
                i += 1
            ordered = {"type": "role", "title": role.get("title", ""), "org": role.get("org", "")}
            if "url" in role:
                ordered["url"] = role["url"]
            ordered["where"] = role.get("where", "")
            ordered["dates"] = role.get("dates", "")
            sec["blocks"].append(ordered)
            continue

        if stripped.startswith("#### "):
            sec["blocks"].append({"type": "subheading", "text": stripped[5:].strip()})
            i += 1
            continue

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if kind == "kv":
                m = re.match(r"^\*\*(.+?):\*\*\s+(.*)$", item, re.S)
                pair = [m.group(1), m.group(2)] if m else [item, ""]
                if sec["blocks"] and sec["blocks"][-1].get("type") == "kv":
                    sec["blocks"][-1]["items"].append(pair)
                else:
                    sec["blocks"].append({"type": "kv", "items": [pair]})
            elif kind == "entries":
                l, _, r = item.rpartition(" — ")
                pair = [l, r] if l else [item, ""]
                if sec["blocks"] and sec["blocks"][-1].get("type") == "entries":
                    sec["blocks"][-1]["items"].append(pair)
                else:
                    sec["blocks"].append({"type": "entries", "items": [pair]})
            else:
                m = re.match(r"^\*\*(.+?)\*\*\s+(.*)$", item, re.S)
                sec["blocks"].append({"type": "bullet", "lead": m.group(1), "text": m.group(2)}
                                     if m else {"type": "bullet", "text": item})
            i += 1
            continue

        m = re.match(r"^\s*<!--\s*spacer:\s*([\d.]+)\s*-->\s*$", line)
        if m:
            sec["blocks"].append({"type": "spacer", "height": float(m.group(1))})
            i += 1
            continue
        if stripped.startswith("<!--"):
            i += 1
            continue

        # everything else is a paragraph; join its continuation lines
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(#|- |<!--)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        sec["blocks"].append({"type": "paragraph", "text": " ".join(para)})
    return content


# ---------------------------------------------------------------- the gate
def _diff(a, b, path=""):
    """First difference between two structures, as a readable path. None if equal."""
    if type(a) is not type(b) and not (isinstance(a, str) and isinstance(b, str)):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: missing on the left"
            if k not in b:
                return f"{path}.{k}: missing on the right"
            d = _diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        for n, (x, y) in enumerate(zip(a, b)):
            d = _diff(x, y, f"{path}[{n}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


def check(paths):
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "**", "*.json"), recursive=True)) \
            if os.path.isdir(p) else sorted(glob.glob(p))
    ok = fail = skipped = canon = 0
    for f in files:
        try:
            orig = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP  {os.path.basename(f)} — unreadable: {e}")
            skipped += 1
            continue
        if "sections" not in orig or "name" not in orig:
            skipped += 1
            continue
        want = canonicalize(orig)
        canon += sum(1 for s in want.get("sections", []) for b in s["blocks"]
                     if b.get("type") == "bullet" and b.get("lead")) - \
            sum(1 for s in orig.get("sections", []) for b in s["blocks"]
                if b.get("type") == "bullet" and b.get("lead"))
        got = md_to_content(content_to_md(want))
        d = _diff(want, got)
        if d is None:
            ok += 1
            print(f"  PASS  {os.path.basename(f)}")
        else:
            fail += 1
            print(f"  FAIL  {os.path.basename(f)}\n          {d}")
    print(f"\n{ok} passed · {fail} failed · {skipped} not a CV"
          f"\n{canon} bullets canonicalised (bold lead-in moved out of `text` into `lead`;"
          f" renders identically)")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["to-md", "to-json", "check"])
    ap.add_argument("path", nargs="+")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.cmd == "check":
        return check(a.path)
    src = a.path[0]
    if a.cmd == "to-md":
        text = content_to_md(canonicalize(json.load(open(src, encoding="utf-8"))))
        out = a.out or os.path.splitext(src)[0] + ".md"
        open(out, "w", encoding="utf-8").write(text)
    else:
        data = md_to_content(open(src, encoding="utf-8").read())
        out = a.out or os.path.splitext(src)[0] + ".json"
        json.dump(data, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
