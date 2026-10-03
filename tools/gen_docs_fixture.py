#!/usr/bin/env python3
"""
gen_docs_fixture.py — generate a SYNTHETIC company document store for the
document-store sources (git_docs / google_drive) tests and demos.

Generated into a folder at test time (never committed): the repo's .gitignore
secrets net would swallow committed `.env` / credentials files, and the planted
"secrets" below are assembled from pieces so no scanner mistakes this source file
for a real leak. Everything is fictional (Initech, Northwind Data, Globex) and
deterministic — the same bytes on every run.

    python3 tools/gen_docs_fixture.py <out-dir> [--drive <out-dir>]
"""
import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

# Needles a test asserts NEVER reach the vault (assembled, not literal).
NEEDLE_BODY = "secret-body-" + "do-not-leak"
FAKE_AWS = "AKIA" + "IOSFODNN7" + "EXAMPLE"
FAKE_PEM = "-----BEGIN RSA " + "PRIVATE KEY-----"
FAKE_PASSWORD_LINE = "db_" + "password = " + "Tr0ub4dor-Horse-Battery"
PLANTED_EMAIL = "fixture" + "@example.com"
PLANTED_PHONE = "+1 555 " + "555 0123"


def _ooxml(kind, texts):
    """A minimal but valid-enough OOXML zip carrying `texts`."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("docProps/core.xml", '<?xml version="1.0"?><cp:coreProperties '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture</dc:title>'
                   '<dc:creator>Grace Hopper</dc:creator></cp:coreProperties>')
        if kind == "pptx":
            for i, t in enumerate(texts, 1):
                z.writestr(f"ppt/slides/slide{i}.xml", f'<p:sld><a:t>{t}</a:t></p:sld>')
        elif kind == "xlsx":
            z.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{t}</t></si>" for t in texts) + "</sst>")
            z.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData/></worksheet>")
        else:
            z.writestr("word/document.xml", "<w:document><w:body>" +
                       "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in texts) + "</w:body></w:document>")
    return _fix_zip_times(b.getvalue())


def _fix_zip_times(data):
    """Rewrite a zip with a fixed timestamp so the bytes are deterministic."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            ni = zipfile.ZipInfo(info.filename, date_time=(2024, 1, 1, 0, 0, 0))
            ni.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(ni, src.read(info))
    return out.getvalue()


def _pdf(text):
    """A tiny uncompressed PDF whose page shows `text` (Tj operator)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out = b"%PDF-1.4\n"
    for i, o in enumerate(objs, 1):
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    return out + b"trailer << /Root 1 0 R >>\n%%EOF\n"


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def generate(root):
    root = Path(root)
    files = {
        "README.md": "# Initech docs\n\nThe company handbook. See [the plan](product/Launch-Plan.md).\n",
        # product: md source + pdf/html renders + a v2
        "product/Launch-Plan.md": ("---\nowner: product\n---\n# Launch plan\n\n## Goals\n\nShip the TPS report "
                                   "redesign between 2025-03-01 and 2025-04-01.\n\n![diagram](../assets/flow.png)\n\n"
                                   "Related: [[Pricing-Model]] and [deploy guide](../engineering/Deployment-Guide.md).\n\n"
                                   f"Call the office at {PLANTED_PHONE} or write {PLANTED_EMAIL}.\n"),
        "product/Launch-Plan.pdf": _pdf("Launch plan rendered"),
        "product/Launch-Plan-v2.md": "# Launch plan v2\n\nThe revised plan.\n",
        "product/Pricing-Model.md": "# Pricing model\n\nTiers: free, team, enterprise.\n",
        # engineering + a byte-identical duplicate elsewhere
        "engineering/Deployment-Guide.md": "# Deployment guide\n\nRun the release script, then verify the health check.\n",
        "archive-old/Deployment-Guide.md": "# Deployment guide\n\nRun the release script, then verify the health check.\n",
        "engineering/System-Architecture.svg": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700">'
                                                '<rect x="10" y="10" width="200" height="80"/></svg>\n'),
        "company/Team.md": ("# Team\n\n- **Bill Lumbergh** — Co-founder & CEO\n- Milton Waddams, Advisor\n\n"
                            "| Name | Role |\n|---|---|\n| Samir Nagheenanajar | Board Member |\n"),
        "strategy/Plan-2025.md": ("# Plan 2025\n\n## Goals\n\n- Reach 10 paying customers by Q4 2025\n"
                                  "- Launch the TPS portal in the EU\n\n## Notes\n\n- not a goal\n"),
        "engineering/Glyph.svg": '<svg class="glyph" viewBox="0 0 64 64"><line x1="1" y1="1" x2="9" y2="9"/></svg>\n',
        "product/Remote-Image.md": "# Remote image\n\n![flow](https://example.com/static/flow.png)\n",
        "assets/initech-logo.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>\n',
        "engineering/api-spec.yaml": "openapi: 3.0.0\ninfo:\n  title: Initech API\n",
        # customers: one clean demo script, one credentials sheet (stub by name AND content)
        "customers/Northwind-Data-Demo-Script.md": "# Northwind demo\n\nWalk through the dashboard.\n",
        "customers/Northwind-Data-Access-Credentials.md": (f"# Access\n\n{NEEDLE_BODY}\n\nkey: {FAKE_AWS}\n"
                                                           f"{FAKE_PASSWORD_LINE}\n"),
        # policy doc that MUST stay clean despite "password" in the name
        "compliance/policies/password-policy.md": "# Password policy\n\nPasswords rotate every 90 days.\n",
        # payments doc quoting a public TEST card number — must stay clean
        "product/Device-Tokenization.md": "# Device tokenization\n\nUse test card 4111 1111 1111 1111 in sandbox.\n",
        # secret-by-content in an innocently named doc
        "engineering/notes-on-setup.md": f"# Setup notes\n\n{FAKE_PEM}\nMIIEpAIBAAKCAQEA\n",
        # ops material: sensitive by path / name
        "config/.env.production": "API_KEY=zq81Lr0PAm2Nx7Kd\nSTRIPE_SECRET=Hn28Wq01xZpLk3Vb\n",
        "postman/Initech.postman_environment.json": '{"_postman_variable_scope": "environment", "values": []}\n',
        "pen-tests/Q1-Scan-Report.pdf": _pdf("Findings"),
        # dense contact list
        "sales/contacts.md": "# Leads\n\n" + "".join(f"- lead{i}@example.org\n" for i in range(25)),
        # an e-mail kept with the docs: message bodies are never read → stub
        "sales/Intro-Call.eml": "From: Jane Doe\nSubject: Intro\n\nHello there\n",
        # office files with extractable text
        "fundraising/Seed-Deck.pptx": _ooxml("pptx", ["Initech seed round", "Market size"]),
        "finance/Budget-2025.xlsx": _ooxml("xlsx", ["Budget", "Payroll", "Tools"]),
        "legal/Mutual-NDA.docx": _ooxml("docx", ["Mutual non-disclosure agreement between Initech and Globex"]),
        # an archive — never extracted
        "exports/bundle.zip": b"",   # filled below
        # assets + agent tooling + a generator
        "assets/flow.png": PNG_1PX,
        "assets/Screenshot 1.png": PNG_1PX,
        ".claude/skills/tps/SKILL.md": "---\nname: tps\n---\n# TPS skill\n",
        "_src/render.py": "print('render')\n",
        ".DS_Store": b"\x00\x00\x00\x01Bud1",
    }
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        zi = zipfile.ZipInfo("credentials.json", date_time=(2024, 1, 1, 0, 0, 0))
        z.writestr(zi, "{}")
    files["exports/bundle.zip"] = zb.getvalue()
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        os.utime(p, (1704067200, 1704067200))     # 2024-01-01 — deterministic times
    try:
        os.symlink("/etc", root / "link-outside")
    except (OSError, NotImplementedError):
        pass
    return root


def generate_drive(root):
    """A Drive-for-desktop shaped folder: native pointer files + a normal file."""
    root = Path(root)
    files = {
        "My Drive/Strategy/Vision 2025.gdoc": ('{"url": "https://docs.google.com/document/d/abc123/edit", '
                                               '"doc_id": "abc123", "email": "' + PLANTED_EMAIL + '"}'),
        "My Drive/Strategy/Roadmap.gsheet": '{"url": "https://docs.google.com/spreadsheets/d/def456/edit", "doc_id": "def456"}',
        "My Drive/Marketing/Brand-Guide.md": "# Brand guide\n\nUse the Initech blue.\n",
    }
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        os.utime(p, (1704067200, 1704067200))
    return root


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--drive", default=None)
    a = ap.parse_args()
    generate(a.out)
    if a.drive:
        generate_drive(a.drive)
    print(f"fixture → {a.out}")
    sys.exit(0)
