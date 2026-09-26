#!/usr/bin/env python3
"""
places.py - read the brain's places layer as full records. Everything else builds on this.

The engine writes one note per place (saved pins, saved lists, your own ratings and review
text, visited places, photo spots, check-ins, event venues) with real coordinates. This
returns each one as a dict:

    name  title  kind  lat  lng  address  country  city  url  lists  tags  rating  review
    sources  created  note  (brain-relative path, e.g. <places layer>/Name.md)
    saved  visited  reviewed   (booleans derived from kind, lists and tags)

Source order: `<brain>/graph.json` when it carries place fields (one file, fast), with the
note body read only for places that have a review; otherwise a walk of the places layer.
The layer folder is resolved through paths.layer() - never spelled here.

    python3 places.py                       # summary by city
    python3 places.py --json                # every record
    python3 places.py --city Lisbon --json  # one city
    python3 places.py --brain <dir> ...     # a brain other than the one at cwd
"""
import argparse, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import brain_at_cwd, layer  # noqa: E402


def parse_front(text):
    """The engine's own frontmatter subset: `key: scalar` + block lists. (dict, body)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    fm, i, key = {}, 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            i += 1
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                fm[key] = [v.strip().strip('"\'') for v in val[1:-1].split(",") if v.strip()]
            else:
                fm[key] = val.strip('"\'') if val else ""
        elif key and re.match(r"^\s+-\s", line):
            item = re.sub(r"^\s+-\s*", "", line).strip().strip('"\'')
            if not isinstance(fm.get(key), list):
                fm[key] = [] if fm.get(key) in ("", None) else [fm[key]]
            fm[key].append(item)
        i += 1
    return fm, "\n".join(lines[i:])


def _num(v):
    try:
        f = float(str(v).strip().strip('"'))
        return f
    except (TypeError, ValueError):
        return None


def _review(body):
    """The `## My review` section, minus the leading star rating."""
    m = re.search(r"^## My review\s*\n+(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not m:
        return ""
    txt = m.group(1).strip()
    return re.sub(r"^★\s*\d(?:\.\d)?\s*[—-]\s*", "", txt).strip()


def _finish(rec):
    tags = [t.lower() for t in rec.get("tags") or []]
    kind = (rec.get("kind") or "").lower()
    if not kind:
        kind = next((t.split("/", 1)[1] for t in tags if t.startswith("place/")
                     and t.count("/") == 1), "place")
    rec["kind"] = kind
    if not rec.get("country"):
        rec["country"] = next((t.split("/")[-1].upper() for t in tags
                               if t.startswith("place/country/")), "")
    rec["lists"] = list(rec.get("lists") or [])
    rec["saved"] = kind == "saved" or bool(rec["lists"]) or "place/saved" in tags
    rec["visited"] = kind in ("visited", "check-in", "photo", "activity", "event") or any(
        t in tags for t in ("place/visited", "place/check-in", "place/photo"))
    rec["reviewed"] = kind == "reviewed" or rec.get("rating") is not None or "place/reviewed" in tags
    return rec


def _from_note(brain, path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, body = parse_front(text)
    if (fm.get("type") or "place") != "place":
        return None
    rel = path.relative_to(brain).as_posix()
    lists = fm.get("lists")
    rec = {"name": fm.get("title") or path.stem, "title": fm.get("title") or path.stem,
           "kind": fm.get("kind", ""), "lat": _num(fm.get("lat")), "lng": _num(fm.get("lng")),
           "address": fm.get("address", ""), "country": (fm.get("country") or "").upper(),
           "city": fm.get("city", ""), "url": fm.get("url", ""),
           "lists": lists if isinstance(lists, list) else ([lists] if lists else []),
           "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
           "rating": _num(fm.get("rating")), "review": _review(body),
           "sources": fm.get("sources") if isinstance(fm.get("sources"), list) else [],
           "created": fm.get("created", ""), "note": rel}
    if rec["rating"] is None:
        m = re.search(r"^## My review\s*\n+\s*★\s*(\d(?:\.\d)?)", body, re.M)
        if m:
            rec["rating"] = float(m.group(1))
    return _finish(rec)


def _from_graph(brain, folder):
    g = brain / "graph.json"
    try:
        data = json.loads(g.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nodes = [n for n in data.get("nodes") or [] if n.get("type") == "place"
             and str(n.get("path", "")).startswith(folder + "/")]
    # graph.json from before the place fields shipped carries no country/kind: walk instead
    if not nodes or not any("kind" in n or "country" in n for n in nodes):
        return None
    out = []
    for n in nodes:
        rec = {"name": n.get("title"), "title": n.get("title"), "kind": n.get("kind", ""),
               "lat": _num(n.get("lat")), "lng": _num(n.get("lng")),
               "address": n.get("address", ""), "country": (n.get("country") or "").upper(),
               "city": n.get("city", ""), "url": "", "lists": n.get("lists") or [],
               "tags": n.get("place_tags") or [], "rating": _num(n.get("rating")),
               "review": "", "sources": n.get("sources") or [], "created": "",
               "note": n.get("path")}
        if rec["rating"] is not None or rec["kind"] == "reviewed":
            full = _from_note(brain, brain / n["path"])   # the review text lives in the body
            if full:
                rec.update({k: full[k] for k in ("review", "url", "created")})
        out.append(_finish(rec))
    return out


def load(brain=None, prefer_graph=True):
    """Every place record in the brain (list of dicts), sorted by name."""
    b = pathlib.Path(brain) if brain else brain_at_cwd()
    if b is None:
        return []
    folder = layer(b, "places")
    recs = _from_graph(b, folder) if prefer_graph else None
    if recs is None:
        d = b / folder
        recs = [r for r in (_from_note(b, p) for p in sorted(d.glob("*.md"))) if r] if d.is_dir() else []
    return sorted(recs, key=lambda r: (r["name"] or "").lower())


def by_city(recs):
    out = {}
    for r in recs:
        key = (r.get("city") or "", r.get("country") or "")
        out.setdefault(key, []).append(r)
    return out


def summary(recs):
    rows = []
    for (city, cc), rs in by_city(recs).items():
        rated = [r["rating"] for r in rs if r.get("rating") is not None]
        rows.append({"city": city, "country": cc, "places": len(rs),
                     "saved": sum(r["saved"] for r in rs),
                     "visited": sum(r["visited"] for r in rs),
                     "saved_not_visited": sum(r["saved"] and not r["visited"] for r in rs),
                     "reviewed": sum(r["reviewed"] for r in rs),
                     "avg_rating": round(sum(rated) / len(rated), 2) if rated else None})
    return sorted(rows, key=lambda x: (-x["saved_not_visited"], -x["places"], x["city"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--brain")
    ap.add_argument("--city")
    ap.add_argument("--country")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--walk", action="store_true", help="ignore graph.json, walk the layer")
    a = ap.parse_args()
    recs = load(a.brain, prefer_graph=not a.walk)
    if a.city:
        recs = [r for r in recs if (r.get("city") or "").lower() == a.city.lower()]
    if a.country:
        recs = [r for r in recs if (r.get("country") or "").upper() == a.country.upper()]
    if a.json:
        print(json.dumps(recs, ensure_ascii=False, indent=1))
        return 0
    if not recs:
        print("no places found (is this a brain with a places layer?)", file=sys.stderr)
        return 1
    print(f"{len(recs)} places")
    for s in summary(recs)[:40]:
        print(f"  {s['city'] or '(no city)'}, {s['country'] or '??'}: {s['places']} places · "
              f"{s['saved_not_visited']} saved-not-visited · {s['reviewed']} reviewed"
              + (f" · avg ★{s['avg_rating']}" if s["avg_rating"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
