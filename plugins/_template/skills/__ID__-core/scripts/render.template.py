#!/usr/bin/env python3
"""render.py - the __LABEL__'s layer, rendered from the ledger. Deterministic; the same ledger gives
byte-identical files. Standard layout (the Jobs standard):

    <layer>/__SHORT__ Dashboard.md · __SHORT__ KPI.md · __SHORT__ Lessons.md · pipeline.json
    <layer>/<items>/<key>.md  (one living note per item)   reports/ (the dailies - never touched here)

R6: a note you edited is kept (the fresh render lands beside it as <name>.new.md); machine files
are always rewritten. The manifest lives in the hidden state root.

    render.py [--quiet] [--dest DIR] [--migrate-layout]
"""
import argparse, datetime, json, os, pathlib, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, render_dir, contract, is_brain  # noqa: E402
from ledger_base import Writer  # noqa: E402
import ledger as LG  # noqa: E402
import pipeline_doc as pdoc  # noqa: E402
import stages as STG  # noqa: E402
import kpi as KPI  # noqa: E402

C = contract()
MANIFEST = "___MANIFEST___GENERATED.json"
TODAY = datetime.date.today().isoformat()
LABEL = str(C.get("label", "__LABEL__")).replace(" Agent", "")
LAY = C.get("layout") or {}


def safe(name):
    return "".join(ch for ch in str(name) if ch not in '\\/:*?"<>|#^[]').strip() or "item"


def item_note(rec, funnel):
    f = funnel or {}
    lab = next((s.get("label") for s in f.get("stages", []) if s["id"] == rec.get("status")), rec.get("status"))
    lines = ["---", f"type: {f.get('item', 'item')}", f"title: {safe(rec.get('title') or rec['key'])}", f"status: {rec.get('status')}",
             f"funnel: {rec.get('funnel', '')}", f"updated: {str(rec.get('updated') or '')[:10]}", "tags:", f"  - {C.get('id')}", "---",
             f"# {safe(rec.get('title') or rec['key'])}", "", f"**Stage:** {lab} · **Score:** {rec.get('score', '—')}", ""]
    if rec.get("why"):
        lines += ["## Why", "", str(rec["why"]), ""]
    if rec.get("next"):
        lines += ["## Next", "", f"- {rec['next'].get('action')} — due {rec['next'].get('due')}", ""]
    if rec.get("work"):
        lines += ["## Work", ""] + [f"- `{w}`" for w in rec["work"]] + [""]
    hist = rec.get("history") or []
    if hist:
        lines += ["## History", ""] + [f"- {h.get('at', '')[:10]} {h.get('from') or '∅'} → {h.get('to')}" for h in hist[-8:]] + [""]
    lines.append(f"Back to [[{LABEL} Dashboard]]")
    return "\n".join(lines) + "\n"


def write_pipeline(w, dest, recs, evs):
    S = pdoc.stage
    pre = dest.name + "/" if is_brain(dest.parent) else ""
    doc = pdoc.new(C["id"], LABEL, C.get("color") or "#3e6ae1")
    doc["funnels"] = [pdoc.funnel(f["id"], f["label"], f["item"], f["success"],
                                  [S(s["id"], s.get("label") or s["id"].title(), s.get("role", "open"), next=s.get("next") or [], gate=s.get("gate", "none")) for s in f["stages"]],
                                  f.get("success2")) for f in C.get("funnels") or []]
    doc["floor"] = [pdoc.floor_group(g["id"], g["label"], g["stages"], g.get("funnel")) for g in C.get("floor") or []]
    items_dir = (LAY.get("items") or {})
    for r in sorted(recs, key=lambda x: x["key"]):
        f = next((x for x in C.get("funnels") or [] if x["id"] == r.get("funnel")), None)
        if not f:
            continue
        folder = items_dir.get(f["item"], f["item"] + "s")
        role = next((s.get("role") for s in f["stages"] if s["id"] == r.get("status")), "open")
        it = pdoc.item(r["key"], r.get("title") or r["key"], r.get("status"), funnel=f["id"], score=r.get("score"),
                       why=r.get("why"), note=pre + f"{folder}/{safe(r.get('title') or r['key'])}.md",
                       attrs={"source": r.get("source") or "", "kind": r.get("kind") or "", "day": r.get("day") or ""},
                       next=r.get("next"), stage_since=str(r.get("updated") or "")[:10] or None, updated=r.get("updated"))
        if role in ("open", "positive"):
            it["detail"] = {"kv": {"Source": r.get("source") or "", "Since": str(r.get("created") or "")[:10]},
                            "history": [{"label": f"{h.get('from') or '∅'} → {h.get('to')}", "status": "done", "date": str(h.get("at") or "")[:10]} for h in (r.get("history") or [])[-6:]]}
        doc["items"].append(it)
    k = KPI.compute(doc, evs, TODAY)
    f0 = k["funnels"][0] if k["funnels"] else None
    if f0:
        doc["headline"] = {"label": f0["success_label"], "value": f0["success_rate"]["num"], "n": f0["success_rate"]["den"], "period": "all time"}
        doc["stats"] = [{"label": f"{f0['success_label']} / {f0['chain'][0] if f0['chain'] else 'items'}", "num": f0["success_rate"]["num"], "den": f0["success_rate"]["den"], "min_n": KPI.MIN_N}]
    doc["lenses"] = [pdoc.lens("score", "Score", "score", domain=[0, 100]),
                     pdoc.lens("age", "Age in stage", "stage_since", scale="days", buckets=[3, 7, 14, 30]),
                     pdoc.lens("today", "New today", "attrs.day", scale="flag", value=TODAY)]
    doc["facets"] = [pdoc.facet("source", "Source", "attrs.source"), pdoc.facet("kind", "Kind", "attrs.kind")]
    doc["panel"] = {"top": ["{stage_label}", "score {score}", "{attrs.source}"],
                    "sections": [{"type": "text", "label": "Why", "from": "why"}, {"type": "kv", "label": "Item", "from": "detail.kv"},
                                 {"type": "steps", "label": "History", "from": "detail.history"}],
                    "actions": [pdoc.action("Act on it", "Act on {title} the way my autonomy setting says.", "primary")]}
    doc["actions"] = [pdoc.action("Run today's __WHAT__", "Run today's __WHAT__.", "primary")]
    doc["generated"] = max([str(r.get("updated") or "") for r in recs] + [""])
    STG.apply(doc, dest / str(LAY.get("profile") or "profile"))
    probs = pdoc.check(doc)
    if probs:
        raise SystemExit("pipeline.json would be invalid: " + "; ".join(probs[:5]))
    w.text("pipeline.json", pdoc.dumps(doc), machine=True)
    return doc, k


def dashboard(recs, k, kept):
    lines = ["---", "type: dashboard", f"title: {LABEL} Dashboard", f"updated: {TODAY}", "tags:", "  - dashboard", "---",
             f"# {LABEL} Dashboard", "", f"> Rendered {TODAY} from the ledger. Rewritten on every run — edit the ledger, not this note.", ""]
    for f in k["funnels"]:
        lines += [f"## {f['label']}", "", f"**{f['success_label']}:** {f['success_rate']['num']} · funnel {f['funnel_line']}", ""]
        lines += ["| Item | Stage | Updated |", "|---|---|---|"]
        for r in sorted([r for r in recs if r.get("funnel") == f["id"]], key=lambda r: str(r.get("updated") or ""), reverse=True)[:30]:
            lines.append(f"| [[{safe(r.get('title') or r['key'])}]] | {r.get('status')} | {str(r.get('updated') or '')[:10]} |")
        lines.append("")
    lines += ["## Notes", "", f"- [[{LABEL} KPI]] · [[{LABEL} Lessons]]", ""]
    return "\n".join(lines)


def lessons(root):
    body = ""
    try:
        import memory as M  # noqa: PLC0415
        items = M.recall(C["id"], None, 4000, stamp=False, brain=str(root.parent.parent) if root.parent.name == ".plugins" else None)
        body = "\n".join("- " + M.recall_line(it) for it in items)
    except Exception:  # noqa: BLE001
        body = ""
    return ("---\ntype: synthesis\n" f"title: {LABEL} Lessons\nupdated: {TODAY}\ntags:\n  - lessons\n---\n# {LABEL} Lessons\n\n"
            "> The readable mirror of what this agent remembers (`_memory/`, scope `" + C["id"] + "`). Inferred items are flagged; edit or remove them in Studio's Memory manager.\n\n"
            + (body or "_Nothing learned yet._") + f"\n\nBack to [[{LABEL} Dashboard]]\n")


def render(dest=None, quiet=True):
    dest = pathlib.Path(dest) if dest else render_dir()
    root = state_root()
    recs = LG.L.load()
    evs = LG.L.events()
    w = Writer(dest, root / MANIFEST, quiet)
    funnels = {f["id"]: f for f in C.get("funnels") or []}
    items_dir = LAY.get("items") or {}
    for r in recs:
        f = funnels.get(r.get("funnel"))
        if not f:
            continue
        folder = items_dir.get(f["item"], f["item"] + "s")
        w.text(f"{folder}/{safe(r.get('title') or r['key'])}.md", item_note(r, f))
    doc, k = write_pipeline(w, dest, recs, evs)
    w.text(str(LAY.get("kpi") or f"{LABEL} KPI.md"), KPI.markdown(k, LABEL))
    w.text(str(LAY.get("lessons") or f"{LABEL} Lessons.md"), lessons(root))
    w.text(str(LAY.get("dashboard") or f"{LABEL} Dashboard.md"), dashboard(recs, k, w.kept))
    gone = w.finish()
    if not quiet:
        print(f"{w.wrote} written · {w.same} unchanged · kept {len(w.kept)} · {len(recs)} items -> {dest}", file=sys.stderr)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--migrate-layout", action="store_true", help="moves through the manifest (none defined yet)")
    a = ap.parse_args()
    if a.migrate_layout:
        w = Writer(render_dir(a.dest), state_root() / MANIFEST, a.quiet)
        print(json.dumps(w.migrate_layout([])))
        return 0
    render(a.dest, a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
