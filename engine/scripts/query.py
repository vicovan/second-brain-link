#!/usr/bin/env python3
"""query.py - exact answers from a built brain, by SQL. Stdlib only (sqlite3, in memory), no
network, no model.

The rule the Harness follows: counting, joining, dates and arithmetic are done HERE, never
guessed by a model; judgement and drafting are the model's. A routine or an agent asks this for
the numbers, then writes the prose.

    query.py <brain> --ask counts                    notes per type and per layer
    query.py <brain> --ask people-at "Acme"          people whose company is Acme
    query.py <brain> --ask dormant-strong            strong ties that went quiet
    query.py <brain> --ask orgs-by-people            organisations ranked by how many people link to them
    query.py <brain> --ask runs                      Harness runs by routine and status
    query.py <brain> --ask objects                   ontology object types: count + resolved (found in 2+ sources)
    query.py <brain> --ask relations                 labelled relations between object types, counted
    query.py <brain> --ask accounts-by-deals         accounts ranked by deals linked to them (+ total value)
    query.py <brain> --ask top-by "account_of"       notes ranked by how many edges of that type touch them
    query.py <brain> --sql "SELECT type, COUNT(*) FROM notes GROUP BY type"     read-only
    query.py <brain> --schema                         the tables and columns

Tables: notes(id, title, type, object, layer, path, deg, strength, status, sources, nsources)
        edges(a, b, type, w, src)        fm(id, key, value)   — every frontmatter scalar
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_FM = re.compile(r"^---\n(.*?)\n---", re.S)


def _scalars(text: str) -> dict:
    """Flat `key: value` frontmatter scalars (lists joined with ', ')."""
    m = _FM.match(text)
    if not m:
        return {}
    out: dict = {}
    key = None
    for ln in m.group(1).splitlines():
        item = re.match(r"^\s*-\s+(.*)$", ln)
        if item and key:
            out[key] = (out.get(key) + ", " if out.get(key) else "") + item.group(1).strip().strip('"')
            continue
        kv = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", ln)
        if kv:
            key = kv.group(1)
            out[key] = kv.group(2).strip().strip('"')
    return out


def connect(brain: pathlib.Path) -> sqlite3.Connection:
    g = json.loads((brain / "graph.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, title TEXT, type TEXT, object TEXT, layer TEXT, path TEXT, "
               "deg INTEGER, strength INTEGER, status TEXT, sources TEXT, nsources INTEGER)")
    onto = g.get("ontology") or {}
    db.execute("CREATE TABLE relations (edge_type TEXT, src_object TEXT, dst_object TEXT, label TEXT, n INTEGER)")
    for r in onto.get("relations", []):
        db.execute("INSERT INTO relations VALUES (?,?,?,?,?)",
                   (r.get("edge_type"), r.get("from"), r.get("to"), r.get("label"), r.get("count")))
    db.execute("CREATE TABLE edges (a TEXT, b TEXT, type TEXT, w REAL, src TEXT)")
    db.execute("CREATE TABLE fm (id TEXT, key TEXT, value TEXT)")
    for n in g.get("nodes", []):
        srcs = [s for s in (n.get("sources") or []) if s and s != "[]"]
        db.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (n["id"], n.get("title"), n.get("type"), n.get("object"), n.get("layer"), n.get("path"),
                    n.get("deg"), n.get("strength"), n.get("status"), ", ".join(srcs), len(srcs)))
        p = brain / str(n.get("path") or (n["id"] + ".md"))
        try:
            for k, v in _scalars(p.read_text(encoding="utf-8", errors="replace")[:6000]).items():
                db.execute("INSERT INTO fm VALUES (?,?,?)", (n["id"], k, v))
        except OSError:
            pass
    for e in g.get("edges", []):
        db.execute("INSERT INTO edges VALUES (?,?,?,?,?)", (e.get("a"), e.get("b"), e.get("type"), e.get("w"), e.get("src")))
    # the Harness's runs are notes too — counted by routine and status
    db.execute("CREATE VIEW runs AS SELECT n.id, n.title, "
               "(SELECT value FROM fm WHERE fm.id=n.id AND key='routine') AS routine, "
               "(SELECT value FROM fm WHERE fm.id=n.id AND key='status') AS status, "
               "(SELECT value FROM fm WHERE fm.id=n.id AND key='started') AS started "
               "FROM notes n WHERE n.type='run'")
    db.commit()
    db.execute("PRAGMA query_only = ON")  # --sql can read, never write
    return db


CANNED = {
    "counts": ("SELECT COALESCE(NULLIF(layer,''),'(none)') AS layer, type, COUNT(*) AS notes FROM notes "
               "GROUP BY layer, type ORDER BY notes DESC", ()),
    "people-at": ("SELECT title, status, strength FROM notes WHERE type='person' AND id IN "
                  "(SELECT id FROM fm WHERE key='company' AND lower(value) LIKE '%' || lower(?) || '%') "
                  "ORDER BY strength DESC, title", ("arg",)),
    "dormant-strong": ("SELECT title, strength, (SELECT value FROM fm WHERE fm.id=notes.id AND key='last_contact') "
                       "AS last_contact FROM notes WHERE type='person' AND lower(COALESCE(status,''))='dormant' "
                       "AND COALESCE(strength,0) >= 3 ORDER BY strength DESC, title", ()),
    "orgs-by-people": ("SELECT o.title, COUNT(DISTINCT CASE WHEN e.a=o.id THEN e.b ELSE e.a END) AS people "
                       "FROM notes o JOIN edges e ON (e.a=o.id OR e.b=o.id) "
                       "JOIN notes p ON p.id = CASE WHEN e.a=o.id THEN e.b ELSE e.a END AND p.type='person' "
                       "WHERE o.type IN ('company','organization','org') GROUP BY o.id ORDER BY people DESC, o.title LIMIT 50", ()),
    "objects": ("SELECT object, COUNT(*) AS count, SUM(nsources > 1) AS merged FROM notes "
                "WHERE object IS NOT NULL AND object != '' GROUP BY object ORDER BY count DESC", ()),
    "relations": ("SELECT src_object || ' —' || label || '→ ' || dst_object AS relation, edge_type, n "
                  "FROM relations ORDER BY n DESC", ()),
    "accounts-by-deals": ("SELECT a.title AS account, COUNT(d.id) AS deals, "
                          "ROUND(SUM(CAST(COALESCE((SELECT value FROM fm WHERE fm.id=d.id AND key='value'),'0') AS REAL)), 2) AS total_value "
                          "FROM notes a JOIN edges e ON (e.a=a.id OR e.b=a.id) AND e.type='account_of' "
                          "JOIN notes d ON d.id = CASE WHEN e.a=a.id THEN e.b ELSE e.a END AND d.type='deal' "
                          "WHERE a.object='account' GROUP BY a.id ORDER BY deals DESC, total_value DESC, a.title LIMIT 50", ()),
    "top-by": ("SELECT n.title, n.object, COUNT(*) AS edges FROM notes n JOIN edges e ON (e.a=n.id OR e.b=n.id) "
               "WHERE e.type = ? GROUP BY n.id ORDER BY edges DESC, n.title LIMIT 50", ("arg",)),
    "runs": ("SELECT COALESCE(NULLIF(routine,''),'(chat)') AS routine, status, COUNT(*) AS runs, MAX(started) AS last "
             "FROM runs GROUP BY routine, status ORDER BY last DESC", ()),
}


def run(brain: pathlib.Path, ask: str = "", arg: str = "", sql: str = "") -> tuple[list, list]:
    db = connect(brain)
    if sql:
        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.I):
            raise SystemExit("query: only SELECT queries")
        cur = db.execute(sql)
    else:
        if ask not in CANNED:
            raise SystemExit("query: unknown --ask (" + ", ".join(CANNED) + ")")
        q, params = CANNED[ask]
        cur = db.execute(q, tuple(arg for _ in params))
    cols = [d[0] for d in cur.description or []]
    return cols, cur.fetchall()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Exact answers from a built brain, by SQL (read-only)")
    ap.add_argument("brain")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ask", choices=sorted(CANNED))
    g.add_argument("--sql")
    g.add_argument("--schema", action="store_true")
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_intermixed_args(argv)  # `--ask people-at "Acme"`: the arg follows the option
    brain = pathlib.Path(a.brain).expanduser()
    if not (brain / "graph.json").is_file():
        print("query: no graph.json in that brain", file=sys.stderr)
        return 2
    if a.schema:
        print(__doc__.split("Tables:")[1].strip())
        return 0
    try:
        cols, rows = run(brain, a.ask or "", a.arg, a.sql or "")
    except sqlite3.Error as e:
        print(f"query: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps([dict(zip(cols, r)) for r in rows], ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print("(no rows)")
        return 0
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    print("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
