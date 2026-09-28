#!/usr/bin/env python3
"""
import_doc.py - bring a fundraising plan the founder keeps OUTSIDE the brain into it.

    python3 import_doc.py PLAN.md --title "Funding Targets" [--check-ledger]

Writes <fundraising layer>/research/<Title>.md with frontmatter (type, source, imported)
and an info callout. Relative links in the source point at files that do not exist inside
the vault, so each becomes its path in inline code; http(s)/mailto links are kept. A CSV
the document links to is copied into profile/materials/ (never moved) and the link says so.

Re-runnable: it only ever overwrites a note that it wrote itself (`imported_by:
import_doc`). --check-ledger lists the bold names in the document's tables and tier lists
that have no record in the ledger, so nothing is lost in the transfer.
"""
import argparse, datetime, os, pathlib, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import render_dir  # noqa: E402
import ledger as L  # noqa: E402
import founder_profile as prof  # noqa: E402

TODAY = datetime.date.today().isoformat()
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def rewrite(text, src_dir, materials):
    copied = []

    def fix(m):
        label, url = m.group(1), m.group(2)
        if re.match(r"(https?|mailto):", url, re.I) or url.startswith("#"):
            return m.group(0)
        target = (src_dir / url).resolve()
        if url.lower().endswith(".csv") and target.is_file():
            materials.mkdir(parents=True, exist_ok=True)
            dst = materials / target.name
            if not dst.exists():
                shutil.copy2(target, dst)
            copied.append(target.name)
            return f"{label} (copied to `profile/materials/{target.name}`)"
        return f"{label} (`{url}` beside the source document)"

    return LINK.sub(fix, text), copied


def doc_names(text):
    names = set()
    for m in re.finditer(r"^\|\s*(?:\d+\s*\|\s*)?\*\*([^*|]{2,60})\*\*", text, re.M):
        names.add(m.group(1).strip())
    for sec in re.findall(r"###\s+Tier[^\n]*\n(.*?)(?=\n###\s|\n##\s|\Z)", text, re.S):
        for m in re.finditer(r"(?:^|\n|· |^- |\n- )\*\*([^*]{2,50})\*\*", sec):
            names.add(m.group(1).strip())
    out = set()
    for n in names:
        n = re.split(r" — | \(|,", n)[0].strip()
        # a name: starts with a capital, no numbers-as-claims, no sentence punctuation, ≤ 6 words
        if (re.match(r"[A-Z0-9]", n) and not re.search(r"[%$:?!]|\b(only|lead|led|rounds?)\b", n)
                and len(n.split()) <= 6 and not re.match(r"(Oct|Nov|Dec|Jan|Feb|Now|Rolling)\b", n)):
            out.add(n)
    return out


def missing_from_ledger(text):
    have = {L.norm_name(r["name"]) for r in L.load().values()}
    out = []
    for n in sorted(doc_names(text)):
        k = L.norm_name(n)
        if len(k) < 3 or re.search(r"\d", n) and len(n) < 12:   # dates / labels, not names
            continue
        if not any(k in h or h in k for h in have if len(h) >= 3):
            out.append(n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--title", required=True)
    ap.add_argument("--check-ledger", action="store_true")
    a = ap.parse_args()
    src = pathlib.Path(a.doc).resolve()
    text = src.read_text(encoding="utf-8")
    layer = render_dir()
    body, copied = rewrite(text, src.parent, layer / "profile" / "materials")
    dest = layer / "research" / (re.sub(r'[\\/:*?"<>|#^\[\]]', "", a.title).strip() + ".md")
    if dest.is_file():
        fm = prof.frontmatter(dest.read_text(encoding="utf-8"))
        if fm.get("imported_by") != "import_doc":
            sys.exit(f"refused: {dest} exists and was not written by import_doc — pick another --title")
    dest.parent.mkdir(parents=True, exist_ok=True)
    head = (f'---\ntype: fundraising-research\ntitle: {a.title}\nsource: "{src}"\nimported: {TODAY}\n'
            f'imported_by: import_doc\ntags: [fundraising, fundraising/research, plan]\n---\n\n'
            f'> [!info] Imported {TODAY} from `{src.name}` — the research of record behind [[Funding Plan]]. '
            f'Re-import to refresh; edit the source, not this copy.\n\n')
    dest.write_text(head + body, encoding="utf-8")
    print(f"imported -> {dest}" + (f" · copied {', '.join(sorted(set(copied)))} to profile/materials/" if copied else ""))
    if a.check_ledger:
        miss = missing_from_ledger(text)
        print("missing from the ledger: " + (", ".join(miss) if miss else "none"))


if __name__ == "__main__":
    main()
