#!/usr/bin/env python3
"""
new_source.py — scaffold a new data-source adapter.

Usage:
    python3 scripts/new_source.py <name>            # personal-subject source
    python3 scripts/new_source.py <name> --company  # company-subject source

Creates (idempotent — refuses to overwrite existing files):
  - scripts/sources/<personal|company>/<name>.py   (from _template.py, NAME filled)
  - data/<name>/README.md                          (intake folder)
  - tests/fixtures/<name>/.gitkeep                  (drop a synthetic export here)

No registry edit is needed — sources/__init__.py AUTO-DISCOVERS every module in
sources/personal/ and sources/company/. Personal modules default SUBJECT="person";
company modules get SUBJECT="company". Then fill in detect() + extract() and add a
fixture so `python3 tests/run.py` exercises it. See CONTRIBUTING.md.
"""
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SOURCES = SCRIPTS / "sources"
REPO = SCRIPTS.parent.parent          # engine/scripts → repo root


def fail(msg):
    """Print an error message and exit non-zero (used for usage/validation errors)."""
    print(f"error: {msg}")
    sys.exit(1)


def main():
    """Scaffold a new source adapter from _template.py plus its intake folder and
    test-fixture dir. Idempotent (refuses to overwrite an existing adapter). No
    registry edit is needed — sources/__init__.py auto-discovers the new module."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    is_company = "--company" in sys.argv[1:]
    if len(args) != 1:
        fail("usage: python3 scripts/new_source.py <name> [--company]")
    name = args[0].strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        fail("name must be lowercase letters/digits/underscore, starting with a letter")

    subdir = "company" if is_company else "personal"
    adapter = SOURCES / subdir / f"{name}.py"
    if adapter.exists():
        fail(f"{adapter.relative_to(REPO)} already exists")
    adapter.parent.mkdir(parents=True, exist_ok=True)

    template = (SOURCES / "_template.py").read_text(encoding="utf-8")
    body = template.replace('NAME = "template"', f'NAME = "{name}"')
    body = body.replace("_template.py — scaffold for a new source adapter.",
                        f"{name}.py — adapter for the {name} export.")
    # _template uses ..common already (it lives one level under sources/ once copied
    # into a subfolder); ensure the company SUBJECT tag is present for company sources
    if is_company and "SUBJECT" not in body:
        body = body.replace('NAME = "%s"' % name,
                            'NAME = "%s"\nSUBJECT = "company"' % name)
    adapter.write_text(body, encoding="utf-8")
    print(f"created {adapter.relative_to(REPO)} (auto-discovered — no registry edit needed)")

    data_readme = REPO / "data" / name / "README.md"
    if not data_readme.exists():
        data_readme.parent.mkdir(parents=True, exist_ok=True)
        data_readme.write_text(
            f"# {name} export\n\nDrop your unzipped **{name}** data export here "
            f"(or pass a `.zip`). Contents are git-ignored.\n", encoding="utf-8")
        print(f"created data/{name}/README.md")

    fixture = REPO / "tests" / "fixtures" / name / ".gitkeep"
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text("", encoding="utf-8")
        print(f"created tests/fixtures/{name}/ (add a tiny synthetic export here)")

    print(f"\nNext: implement detect()+extract() in sources/{subdir}/{name}.py, "
          f"add a synthetic fixture under tests/fixtures/{name}/, then run "
          f"`python3 tests/run.py`.")


if __name__ == "__main__":
    main()
