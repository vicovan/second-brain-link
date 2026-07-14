#!/usr/bin/env python3
"""
profile_export.py — multi-source schema map ("data dictionary") for any supported
export (all registered sources — the registry is auto-discovered — and unknowns).

Detects which source(s) the export belongs to, then catalogs every data file:
type, columns/keys, fill-rate, a privacy-safe sample, and whether an adapter is
expected to consume it. Files no source recognizes are flagged for adaptation.
Read the generated schema_map.md (PII-safe) — never the raw files.

Also emits PII-safe visualizations (unless disabled):
  - <stem>_mindmap.md / .canvas  — every file & column + cross-file correlations
  - brain_structure.md / .canvas / .json — the designed (pruned-canonical) vault
    tree; the .json is the build-spec that build_vault.py --structure consumes.

Usage:
  python profile_export.py <export.zip | folder> [--out <dir>]
                           [--no-mindmap] [--no-structure]
"""
import argparse, json, re, sys, tempfile, zipfile, shutil
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources as _sources
from sources import detect_sources
from sources.common import (norm_file, nk, read_csv, read_json, EMAIL_RE, PHONE_RE,
                            SENSITIVE_COL_HINTS)
import selfheal

SAMPLE = 200

def index_files(root):
    """Walk `root` recursively → (index, all_paths). `index` maps norm_file(name)
    → [paths] for profilable data files (csv/json/ics/vcf/html); `all_paths` is
    every file found. The norm_file keys match what adapters/mappings consume."""
    idx, allp = {}, []
    for p in root.rglob("*"):
        if p.is_file():
            allp.append(p)
            if p.suffix.lower() in (".csv", ".json", ".ics", ".vcf", ".html", ".htm"):
                idx.setdefault(norm_file(p.name), []).append(p)
    return idx, allp

def infer_type(vals):
    """Guess a column's logical type from a sample of values: empty / email / url /
    date-ts / number / categorical / text. Inspects only the first ~20 non-empty
    values; the type label is metadata, not a stored cell value."""
    v = [x for x in vals if x]
    if not v: return "empty"
    if all(EMAIL_RE.search(x) for x in v[:20]): return "email"
    if all(x.startswith("http") for x in v[:20]): return "url"
    if all(re.match(r"^\d{4}[-/]\d", x) or re.match(r"^\d{10,13}$", x) for x in v[:20]): return "date/ts"
    if all(re.match(r"^-?\d+(\.\d+)?$", x.replace(",", "")) for x in v[:20]): return "number"
    return "categorical" if len(set(v)) <= max(8, len(v)//10) else "text"

def safe_sample(col, vals):
    """Return ONE privacy-safe example value for column `col`. Redaction is
    mandatory: a sensitive-named column, or a value that looks like an email/phone,
    yields "[redacted]"; otherwise the first non-empty value truncated to 48 chars.
    This keeps the schema_map shareable."""
    if any(h in nk(col) for h in SENSITIVE_COL_HINTS): return "[redacted]"
    for x in vals:
        if x:
            if EMAIL_RE.search(x) or PHONE_RE.search(x): return "[redacted]"
            return (x[:48] + "…") if len(x) > 48 else x
    return ""

def profile_csv(p):
    """Profile a CSV at `p` → (row_count, columns). Each column carries name, inferred
    type, fill-rate %, and a redacted sample. Samples only the first SAMPLE rows."""
    rows = read_csv(p)
    headers = list(rows[0].keys()) if rows else []
    headers = [h for h in headers if h is not None]   # drop DictReader restkey
    cols = []
    for h in headers:
        vals = [(r.get(h) or "").strip() for r in rows[:SAMPLE]]
        ne = [v for v in vals if v]
        cols.append({"name": h, "type": infer_type(vals),
                     "fill": round(100*len(ne)/len(vals)) if vals else 0,
                     "sample": safe_sample(h, ne)})
    return len(rows), cols

def profile_json(p):
    """Profile a JSON file at `p` → (count, columns). Catalogs the top-level keys
    (first 12) as "json-key" columns; no values are sampled, so it is PII-safe by
    construction."""
    data = read_json(p)
    if isinstance(data, list):
        n = len(data); keys = list(data[0].keys())[:12] if data and isinstance(data[0], dict) else []
    elif isinstance(data, dict):
        n = len(data); keys = list(data.keys())[:12]
    else:
        n, keys = 0, []
    return n, [{"name": k, "type": "json-key", "fill": 100, "sample": ""} for k in keys]

def main():
    """CLI entry point: accept a .zip or folder, detect sources, catalog every data
    file into a PII-safe schema_map.md/.json, and (unless disabled) emit the mindmap
    and brain-structure visualizations. `--doctor` runs a preflight check instead.
    On failure, writes a structured _ERROR.md and exits non-zero (self-heal cue)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("--out", default=None)
    ap.add_argument("--no-mindmap", action="store_true",
                    help="skip the mindmap (files+fields+correlations) visualizations")
    ap.add_argument("--no-structure", action="store_true",
                    help="skip the brain-structure design (md/canvas/json)")
    ap.add_argument("--doctor", action="store_true",
                    help="run a preflight health check (writes _DOCTOR.md) and exit")
    args = ap.parse_args()
    src = Path(args.source).expanduser()
    tmp = None
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp()); zipfile.ZipFile(src).extractall(tmp); work = tmp
    elif src.is_dir(): work = src
    else: print("Source must be .zip or folder."); sys.exit(1)
    out_dir0 = Path(args.out).expanduser() if args.out else Path.cwd()
    if args.doctor:
        try:
            status = selfheal.doctor(work, out_dir0,
                                     detect_sources=detect_sources, index_files=index_files)
            print(f"doctor: {status} → {out_dir0/'_DOCTOR.md'}")
        finally:
            if tmp: shutil.rmtree(tmp, ignore_errors=True)
        return
    try:
        idx, allp = index_files(work)
        sources = detect_sources(idx)
        src_names = [m.NAME for m in sources]
        quar = _sources.ALL_QUARANTINE
        quar_pfx = getattr(_sources, "ALL_QUARANTINE_PREFIX", ())
        catalog, summary = [], Counter()
        for key, paths in sorted(idx.items()):
            p = paths[0]
            is_quar = key in quar or (bool(quar_pfx) and key.startswith(quar_pfx))
            kind = ("quarantine" if is_quar else "known" if src_names else "unknown")
            summary[kind] += 1
            if p.suffix.lower() == ".csv": nrows, cols = profile_csv(p)
            elif p.suffix.lower() == ".json": nrows, cols = profile_json(p)
            else: nrows, cols = 0, []
            catalog.append({"file": p.name, "key": key, "class": kind, "rows": nrows, "columns": cols})
        out_dir = Path(args.out).expanduser() if args.out else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "schema_map.json").write_text(
            json.dumps({"sources": src_names, "summary": dict(summary), "catalog": catalog}, indent=2),
            encoding="utf-8")
        md = ["# Export schema map", "",
              f"Sources detected: **{', '.join(src_names) or 'none — generic catch-all only'}**",
              f"Data files: {len(idx)} (known {summary['known']}, unknown {summary['unknown']}, "
              f"quarantine {summary['quarantine']})", ""]
        unknown = [c for c in catalog if c["class"] == "unknown"]
        if unknown or not src_names:
            md += ["## ⚠️ Adaptation needed", ""]
            if not src_names:
                md.append("No source adapter matched. Files below will be summarized into "
                          "`99-uncategorized/`; add `file_routes` to map them.\n")
            for c in unknown:
                cl = ", ".join(col["name"] for col in c["columns"][:8])
                md.append(f"- `{c['file']}` ({c['rows']} records) — {cl}")
            md.append("")
        md += ["## Full catalog", ""]
        for c in catalog:
            tag = {"known": "mapped by adapter", "quarantine": "QUARANTINE — not imported",
                   "unknown": "UNKNOWN"}[c["class"]]
            md.append(f"### {c['file']} — {tag} ({c['rows']} records)")
            if c["class"] == "quarantine":
                md.append("_columns omitted for privacy_\n"); continue
            for col in c["columns"]:
                md.append(f"- **{col['name']}** · {col['type']} · {col['fill']}% · `{col['sample']}`")
            md.append("")
        (out_dir / "schema_map.md").write_text("\n".join(md), encoding="utf-8")
        print(f"Profiled {len(idx)} files → {out_dir/'schema_map.md'}")
        print(f"  sources: {', '.join(src_names) or 'none'} · known={summary['known']} "
              f"unknown={summary['unknown']} quarantine={summary['quarantine']}")

        # ---- visualizations (PII-safe; built from the catalog, not raw data) ----
        import diagrams
        # a company export designs a company-named brain (30-content, 85-locations,
        # …) — re-apply the layout under the company variant so the mindmap +
        # designed structure preview exactly what the builder will emit.
        if any(getattr(m, "SUBJECT", "person") == "company" for m in sources):
            import mapping as _mapping
            diagrams.apply_layout(_mapping.load_brain_layout(), "company")
        # name outputs after the single detected source (e.g. linkedin_mindmap.md)
        stem = src_names[0] if len(src_names) == 1 else "schema_map"
        root_label = (src_names[0].title() + " export") if len(src_names) == 1 else "Export"
        if not args.no_mindmap:
            (out_dir / f"{stem}_mindmap.md").write_text(
                diagrams.mindmap_markdown(catalog, src_names, quar, root_label),
                encoding="utf-8")
            (out_dir / f"{stem}_mindmap.canvas").write_text(
                diagrams.mindmap_canvas(catalog, src_names, quar, root_label),
                encoding="utf-8")
            print(f"  mindmap: {out_dir/(stem+'_mindmap.md')} (+ .canvas)")
        if not args.no_structure:
            sm, sc, sj = diagrams.brain_structure(catalog, src_names, quar, stem)
            (out_dir / "brain_structure.md").write_text(sm, encoding="utf-8")
            (out_dir / "brain_structure.canvas").write_text(sc, encoding="utf-8")
            (out_dir / "brain_structure.json").write_text(
                json.dumps(sj, indent=2), encoding="utf-8")
            print(f"  brain structure: {out_dir/'brain_structure.md'} (+ .canvas, .json)")
    except Exception as e:
        rep = selfheal.write_error_report(out_dir0, "profile_export", e)
        print(f"\n❌ Profiling failed: {type(e).__name__}: {e}")
        print(f"   Structured fix report → {rep}")
        sys.exit(1)
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
