#!/usr/bin/env python3
"""
render_brain.py - render the job pipeline as a Second Brain layer.

The ledger (`outcomes.jsonl`, `seen.json`, the report Markdown, the built PDFs) stays where it is.
This turns it into a `45-jobs/` folder of properly frontmattered notes that Obsidian and Second
Brain Studio index, search and graph like any other layer of a vault.

    python3 render_brain.py                       # render to this surface
    python3 render_brain.py --dest <dir>          # render somewhere explicit
    python3 render_brain.py --import-to <dir>     # one-time copy across surfaces
    python3 render_brain.py --quiet               # after every status change

## Where it writes

**Strictly one place per run.** Inside a brain it renders into that brain; otherwise into the
workspace. Never both - that is the user's explicit choice, and the cost of it is that the other
surface holds the previous run until it is next run from there. `Dashboard.md` therefore records
which surface wrote it and when, so a stale copy says so rather than quietly looking current.

`--import-to` is the one exception, and it is never automatic: a flag the user asks for, to seed a
second surface from the first without doing the work twice.

## What it will not do

- It never writes `profile/` - that is onboarding's, and this only reads it.
- It never deletes. A job that vanishes from the ledger is reported, not removed.
- It never touches SBL's `_GENERATED.json`; it keeps its own `_JOBS_GENERATED.json`, so the vault
  engine sees these notes as user files and leaves them alone (`build_vault.py`).
- It creates no `companies/` notes: Obsidian resolves `[[Northwind]]` by title *or* filename, so a
  second `Northwind.md` would break every existing link in the vault. Application notes link out to
  the org layer instead, which is what puts them in the graph.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (state_root, render_dir, surface_root, work_root, brain_at_cwd,  # noqa: E402
                   brain_state_root, LEGACY_STATE_DIRNAME, is_brain)
import pipeline_doc as pdoc  # noqa: E402
import kpi as KPIlib  # noqa: E402
import stages as STG  # noqa: E402
from ledger_base import Writer as _BaseWriter, replace_between, add_alias  # noqa: E402

MANIFEST = "_JOBS_GENERATED.json"
# Names are prefixed on purpose. A vault root already has `Dashboard.md` and `_BUILD_REPORT.md`,
# and a bare `2026-01-15.md` collides with any daily-note scheme. Obsidian resolves [[links]] by
# filename as well as title (vaultCore.ts), so a duplicate name silently repoints real links.
DASHBOARD = "Job Dashboard.md"
LESSONS = "Job Lessons.md"
KPI = "Job KPI.md"                 # was "Job Pipeline KPI.md" (alias kept; --migrate-layout moves it)
KPI_OLD = "Job Pipeline KPI.md"
DAILY_SCHEMA = "sbl-daily/1"
BUILD_REPORT = "_JOBS_BUILD_REPORT.md"
TODAY = datetime.date.today().isoformat()


def machinery_dir(root, dest):
    """Where the renderer's own bookkeeping goes.

    The manifest and the build report are machinery, not reading material, and they sat at
    the top of the jobs layer where the user looks for the daily report and the dashboard.
    They live with the rest of the ledger now — hidden, and beside the data they describe.

    The state root is CREATED if it does not exist yet. Falling back to `dest` when it was
    merely absent put the manifest straight back into the jobs layer on every fresh install —
    exactly the thing this function was written to stop.
    """
    d = pathlib.Path(root)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Unwritable (a read-only mount, a path the user cannot create): the layer is the
        # honest fallback, and it is better than losing the manifest entirely.
        d = pathlib.Path(dest)
        d.mkdir(parents=True, exist_ok=True)
    return d

# Keyed on `status`, and only on `status` (used at :399 and :510). Every key must be
# something learn.py can actually write — STATUSES, or a RESULTS value promoted onto the row
# — or an application can reach a state the vault renders but nothing can record. "replied"
# was such a key: no code path ever produced it. The equivalent real value is `screen`.
# Files job-apply writes into an application folder that are NOT the CV.
WORKING_FILES = {"posting.md": "Posting", "fit.md": "Fit", "company.md": "Company research",
                 "cover-letter.md": "Cover letter", "form-fields.md": "Form fields",
                 "application-answers.md": "Application answers"}

# A tailored CV is named <First>_<Last>_CV_<Company>.md (cv-tailor). Only files that LOOK like
# one are rendered as a CV; any other working file job-apply adds later is rendered under its
# own humanised name instead of being mislabelled "CV <Company> 2" — which is exactly what
# happened to form-fields.md when it was introduced.
CV_NAME_RE = re.compile(r"(^|[_\s-])CV([_\s-]|$)", re.I)

STATUS_GLYPH = {"applied": "✅", "filled": "🟡", "not_started": "⬜", "skipped": "⛔",
                "disqualified": "❌", "excluded": "🚫", "screen": "🔵", "interview": "🎯",
                "prior_external": "📁", "skipped_knockout": "⛔", "skipped_review": "⛔",
                "drafted_linkedin": "🟠", "handoff_portal": "🟠"}


# ---------------------------------------------------------------- small helpers
def safe(name):
    """A filename that survives every filesystem and still reads as the note's title."""
    name = re.sub(r"[/\\:*?\"<>|]", "-", str(name)).strip().rstrip(".")
    return re.sub(r"\s+", " ", name)[:120]


def yaml_scalar(v):
    s = "" if v is None else str(v)
    if s == "" or s != s.strip() or s[0] in "&*!|>%@`'\"[]{}#-?" or ": " in s or s.endswith(":") \
            or s[0] == "+":
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def frontmatter(pairs, tags):
    out = ["---"]
    for k, v in pairs:
        out.append(f"{k}: {yaml_scalar(v)}")
    out.append("tags: [" + ", ".join(tags) + "]")
    out.append("---")
    return "\n".join(out) + "\n\n"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Writer(_BaseWriter):
    """The shared R6 writer (ledger_base.Writer): a note the user edited is kept and the fresh
    render lands beside it as <name>.new.md; machine files are always rewritten; the manifest
    (`_JOBS_GENERATED.json`, beside the ledger) remembers what was rendered."""

    def __init__(self, root, manifest_path, quiet=False):
        super().__init__(root, manifest_path, quiet)


def cv_label(company, role, taken):
    """A short, globally unique name for a CV in the rendered layer.

    Studio splits table cells on a bare `|` (brain-md.ts), so an aliased wikilink
    `[[Long_Name|CV]]` is torn in half inside a table — which is why the dashboard printed raw
    `[[…` / `CV]]`. Inside a table the *target name is the label*, so the label has to come from
    the filename. Links resolve by name globally, so a bare "CV" cannot point at 22 different
    files; the company (plus a role word only when the same company appears twice) is the
    shortest thing that is still unique.
    """
    base = safe(f"CV {company}").strip()   # a "/" in a company name would become a folder
    if base.lower() not in taken:
        taken.add(base.lower())
        return base
    for w in re.findall(r"[A-Za-z]+", role):
        cand = f"{base} {w}"
        if len(w) > 2 and cand.lower() not in taken:
            taken.add(cand.lower())
            return cand
    n = 2
    while f"{base} {n}".lower() in taken:
        n += 1
    taken.add(f"{base} {n}".lower())
    return f"{base} {n}"


# ---------------------------------------------------------------- the ledger
def load_outcomes(root):
    rows = []
    f = root / "outcomes.jsonl"
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def find_app_dir(root, job_key):
    """This job's artifact folder, and the day it is filed under."""
    base = root / "applications"
    if not base.is_dir():
        return None, ""
    for day in sorted(base.iterdir(), reverse=True):
        cand = day / job_key
        if cand.is_dir():
            return cand, (day.name if DAY_RE.match(day.name) else "")
    return None, ""


def scan_app_dirs(root):
    """Every application folder ON DISK, as {job_key: (dir, day)}.

    The renderer used to mirror only what `outcomes.jsonl` knew, and the ledger was only
    written AFTER a form was submitted — so an application you had built, tailored a CV for
    and filled in was completely absent from your own vault until you sent it. The disk is
    the truth about what exists; the ledger is the truth about what happened to it. Read
    both.
    """
    out = {}
    base = root / "applications"
    if not base.is_dir():
        return out
    for day in sorted(base.iterdir()):
        if not day.is_dir() or not DAY_RE.match(day.name):
            continue
        for d in sorted(day.iterdir()):
            if d.is_dir():
                out[d.name] = (d, day.name)      # a later day wins: the current attempt
    return out


def row_from_folder(job_key, app_dir, day):
    """Synthesise a ledger row for a folder that has none.

    `learn.py log-outcome` writes an ANSWERS.md whose frontmatter carries everything a row
    needs. When even that is missing, fall back to the job_key so the folder is still
    rendered under a readable name rather than dropped.
    """
    fm = {}
    ans = app_dir / "ANSWERS.md"
    if ans.is_file():
        txt = ans.read_text(encoding="utf-8", errors="replace")
        if txt.startswith("---"):
            end = txt.find("\n---", 3)
            if end != -1:
                for line in txt[3:end].splitlines():
                    m = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
                    if m:
                        fm[m.group(1)] = m.group(2).strip().strip('"')
    company = fm.get("company") or job_key.split("-")[0].title()
    role = fm.get("role") or job_key.replace("-", " ")
    status = (fm.get("status") or "").split("—")[0].strip().lower().replace(" ", "_")
    return {"date": fm.get("date") or day, "job_key": job_key, "company": company,
            "role": role, "url": fm.get("url", ""), "source": fm.get("source", ""),
            "score": fm.get("score", ""), "portal": fm.get("portal", ""),
            "status": status if status in STATUS_GLYPH else "filled",
            "result": None, "note": "", "_from_disk": True}


def merge_rows(ledger, on_disk):
    """Ledger rows first, then any folder the ledger has never heard of."""
    known = {r.get("job_key", "") for r in ledger}
    extra = [row_from_folder(k, d, day) for k, (d, day) in sorted(on_disk.items())
             if k and k not in known]
    return list(ledger) + extra



_LINKS_BLOCK = re.compile(r"^links:[ \t]*\n((?:[ \t]+.*\n?)+)", re.M)


def flatten_links(md_text):
    """The rendered copy's `links:` becomes a flat list of URLs.

    cv-tailor stores `links` as a list of `{text, url}` objects because the PDF builder needs
    the text. Studio's property panel cannot show nested objects and prints "[object Object]",
    so the VIEW gets plain URLs. The source CV in the ledger is never touched.
    """
    if not md_text.startswith("---"):
        return md_text
    end = md_text.find("\n---", 3)
    if end == -1:
        return md_text
    head, rest = md_text[:end + 1], md_text[end + 1:]
    m = _LINKS_BLOCK.search(head)
    if not m or "url:" not in m.group(1):
        return md_text
    urls = re.findall(r"url:\s*[\"']?([^\"'\n]+)", m.group(1))
    flat = "links:\n" + "".join(f"  - {u.strip()}\n" for u in urls)
    return head[:m.start()] + flat + head[m.end():] + rest


def retitle(md_text, label):
    """Give the rendered CV the note title we link it by.

    Studio's live link index maps **`title` only** (`brain-app.ts`) — not the filename. That
    is the whole reason `[[CV Northwind]]` rendered grey while `[[Northwind — Chief Product Officer]]`
    worked: the first matched a filename, the second matched a title. So the rendered copy carries
    `title: CV Northwind`. The CV in the ledger keeps its own title; only this view is retitled, and
    `cv_md.md_to_content` ignores `title`, so the PDF still builds from it unchanged.
    """
    md_text = flatten_links(md_text)
    if md_text.startswith("---"):
        end = md_text.find("\n---", 3)
        if end != -1:
            head, rest = md_text[:end], md_text[end:]
            if re.search(r"^title:", head, re.M):
                head = re.sub(r"^title:.*$", f"title: {label}", head, count=1, flags=re.M)
            else:
                head += f"\ntitle: {label}"
            return head + rest
    return f"---\ntype: cv\ntitle: {label}\n---\n\n" + md_text



def answers_section(app_dir):
    """What was actually typed into the employer's form.

    This is the part you cannot reconstruct later: at interview you need to know the
    salary figure you gave, the notice period, the work-authorisation answer and the
    free text. So prefer the STRUCTURED record (`answers.json`, written before the form
    is filled) and render it as a table; fall back to the prose in ANSWERS.md.

    The fallback stops at the next `##` heading on purpose — an earlier version appended
    everything after the heading, which dragged that file's own "## Result" section into
    the note and rendered Result twice.
    """
    if not app_dir:
        return ""
    aj = app_dir / "answers.json"
    if aj.is_file():
        try:
            data = json.loads(aj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        rows = _answer_rows(data)
        if rows:
            out = ["\n## Answers given on the form\n",
                   "\n| Question | Answer |\n|---|---|\n"]
            for q, a in rows:
                out.append(f"| {_cell(q)} | {_cell(a)} |\n")
            out.append("\n_Recorded before submitting, so it can be quoted back at interview._\n")
            return "".join(out)
    md = app_dir / "ANSWERS.md"
    if md.is_file():
        raw = md.read_text(encoding="utf-8")
        parts = raw.split("## Answers given on the form", 1)
        if len(parts) == 2:
            # up to the NEXT heading only
            rest = re.split(r"\n##\s", parts[1], 1)[0].rstrip()
            if rest.strip():
                return "\n## Answers given on the form\n" + rest + "\n"
    return ""


def _answer_rows(data):
    """Accept the shapes a run may produce, rather than demanding one.

    {"Question": "Answer"} · [{"question":…, "answer":…}] · {"answers": <either>}
    """
    if isinstance(data, dict) and "answers" in data:
        data = data["answers"]
    rows = []
    if isinstance(data, dict):
        for k, v in data.items():
            if v is None or v == "":
                continue
            rows.append((str(k), v))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            q = item.get("question") or item.get("label") or item.get("field") or ""
            a = item.get("answer") if "answer" in item else item.get("value", "")
            if q and a not in (None, ""):
                rows.append((str(q), a))
    return rows


def _cell(v):
    """One table cell: a bare `|` would split the row, and a newline would end it."""
    if isinstance(v, (list, tuple)):
        v = "; ".join(str(x) for x in v)
    elif isinstance(v, bool):
        v = "Yes" if v else "No"
    s = str(v).replace("|", "\\|")
    return " ".join(s.split())


def org_index(dest):
    """Names the destination vault already has a note for.

    A wikilink to a note that does not exist renders grey and does nothing, which reads as broken
    even though Obsidian calls it a healthy phantom. So a company is linked only when the vault can
    actually resolve it; otherwise it is plain text. Only filenames are read - no file contents -
    so this stays cheap even against a vault with tens of thousands of notes.
    """
    names = set()
    root = pathlib.Path(dest).parent
    from paths import layer as _layer
    for sub in (_layer(root, "orgs"), _layer(root, "people")):
        d = root / sub
        if d.is_dir():
            for f in d.rglob("*.md"):
                names.add(f.stem.lower())
    return names


def org_link(company, known):
    c = safe(company)
    return f"[[{c}]]" if c.lower() in known else c


# ---------------------------------------------------------------- the notes
def application_note(row, app_dir, cv_names, known=frozenset()):
    company, role = row.get("company", "?"), row.get("role", "?")
    status = row.get("status", "not_started")
    # The title is what links resolve against, and the filename is built from the same string —
    # so both go through safe(). "Northwind Ventures / Atlas" would otherwise title itself with a
    # slash the filename cannot carry, and every link to it would land nowhere.
    title = safe(f"{company} — {role}")
    pairs = [
        ("type", "application"), ("title", title),
        ("company", company), ("role", role), ("job_key", row.get("job_key", "")),
        ("status", status), ("score", row.get("score") or ""), ("portal", row.get("portal") or ""),
        ("source", row.get("source") or ""), ("url", row.get("url") or ""),
        ("location", row.get("location", "")), ("comp", row.get("comp", "")),
        ("applied", row.get("date", "")), ("result", row.get("result") or ""),
        ("result_date", row.get("result_date") or ""),
        ("cv", cv_names[0][0] if cv_names else ""),
        ("pdf", cv_names[0][1] if cv_names and cv_names[0][1] else ""), ("updated", TODAY),
    ]
    tags = ["jobsearch", "application", f"status/{status}"]
    if row.get("portal"):
        tags.append(f"portal/{row['portal']}")

    body = [frontmatter(pairs, tags)]
    body.append(f"# {title}\n")
    body.append(f"{STATUS_GLYPH.get(status, '⬜')} **{status}**"
                + (f" · {row['date']}" if row.get("date") else "")
                + (f" · score {row['score']}/100" if row.get("score") else "") + "\n")
    body.append(f"Company: {org_link(company, known)}\n")
    if row.get("url"):
        body.append(f"Posting: <{row['url']}>\n")
    if app_dir and (pathlib.Path(app_dir) / "confirmation.png").is_file():
        body.append(f"\n## Submitted\n\n![[{title} · Confirmation.png]]\n")
    if cv_names:
        # Wikilinks, with a short alias, for BOTH the Markdown and the PDF. Second Brain Studio's
        # renderer only turns `[text](url)` into a link when the url starts with http(s)
        # (brain-md.ts) — a relative `[PDF](Foo.pdf)` prints literally. A PDF *is* reachable,
        # because a non-.md file becomes a `type: file` note titled with its full basename
        # (vaultCore.ts), so `[[Foo.pdf]]` resolves and the host opens it.
        body.append("\n## CV sent\n")
        for n, pdf in cv_names:
            # BOTH are real links. A PDF is indexed as a `type: file` note titled with its
            # full basename, so `[[CV Foo.pdf]]` resolves and opens in the reader — naming
            # it in backticks, as this used to, left the actual file unreachable from the
            # note that is about it.
            if pdf:
                body.append(f"- **PDF sent:** [[{pdf}]] — opens here; *Reveal in folder* "
                            "shows it on disk\n")
                body.append(f"- **Markdown source:** [[{n}]]\n")
            else:
                body.append(f"- [[{n}|CV]]\n")
    if row.get("cv_variant") or row.get("contact_set"):
        body.append("\n## How it was pitched\n")
        if row.get("cv_variant"):
            body.append(f"- **Variant:** {row['cv_variant']}\n")
        if row.get("contact_set"):
            body.append(f"- **Contact set:** {row['contact_set']}\n")
    if row.get("keywords"):
        body.append(f"- **Keywords led with:** {' · '.join(row['keywords'])}\n")
    if row.get("note"):
        body.append(f"\n## Notes\n\n{row['note']}\n")

    body.append(answers_section(app_dir))

    body.append("\n## Result\n\n" + (f"**{row['result']}**" + (f" ({row['result_date']})"
                if row.get("result_date") else "") if row.get("result") else
                "_Not yet._ Record it with `learn.py set-result --job-key "
                f"{row.get('job_key','')} --result screen|rejected|interview|offer|none`") + "\n")
    return "".join(body)


def report_note(path, labels):
    date = path.stem
    raw = path.read_text(encoding="utf-8")
    # The agent sometimes writes the report with its own frontmatter block. This note carries
    # the frontmatter, so drop the report's (it printed as a line of "type: … ---" text), then
    # its leading H1 (the note title is already the heading).
    raw = re.sub(r"\A﻿?\s*---\s*\n.*?\n---[ \t]*\n", "", raw, count=1, flags=re.S)
    raw = re.sub(r"\A\s*#\s+.*\n", "", raw, count=1)
    # The ledger's reports link CVs by a path relative to <state>/reports/, which resolves
    # nowhere once the note is read from a vault — and a non-http markdown link is not even
    # rendered as a link. Rewrite them to wikilinks, which resolve by basename.
    def as_wikilink(m):
        target = m.group(2)
        parts = [x for x in target.split("/") if x]
        key = parts[-2] if len(parts) >= 2 else ""
        lab = labels.get(key)
        if not lab:
            # No CV rendered for this job. Emit the link TEXT, not the markdown link: a
            # non-http link is not rendered as a link at all, so leaving it prints the raw
            # ../applications/... path into the table as literal characters.
            return m.group(1) or "—"
        # No alias: these links sit in table rows, and Studio splits a row on a bare "|"
        # (brain-md.ts), which tears an aliased wikilink in half.
        return f"[[{lab[0]}]]"       # always the note: a .pdf is never indexed
    raw = re.sub(r"\[([^\]]*)\]\((\.\.?/[^)]+)\)", as_wikilink, raw)

    # The agent may also have written the wikilink itself. Point it at the label this run
    # actually produced, so both authoring styles converge on a link that resolves — and a
    # CV whose label gained a collision suffix is not left as a phantom.
    by_company = {}
    for lab in labels.values():
        by_company.setdefault(lab[0].split(" ")[-1].lower(), lab[0])
    for lab in labels.values():
        by_company.setdefault(lab[0].lower(), lab[0])

    def fix_bare(m):
        want = m.group(1).strip()
        if want.lower() in (l[0].lower() for l in labels.values()):
            return m.group(0)                       # already the real label
        hit = by_company.get(want.lower()) or by_company.get(want.split(" ")[-1].lower())
        return f"[[{hit}]]" if hit else m.group(0)
    raw = re.sub(r"\[\[\s*(CV [^\]|]+?)\s*\]\]", fix_bare, raw)
    pairs = [("type", "report"), ("title", f"Shortlist {date}"), ("date", date),
             ("updated", TODAY)]
    return frontmatter(pairs, ["jobsearch", "report", "dashboard"]) + \
        f"# Shortlist {date}\n" + raw


def dashboard_note(rows, reports, dest, profile_src, known=frozenset()):
    submitted = [r for r in rows if r.get("status") == "applied"]
    replied = [r for r in rows if r.get("result")]
    surface = "brain" if brain_at_cwd() else "working folder"
    pairs = [("type", "dashboard"), ("title", "Job pipeline"),
             ("applications", len(rows)), ("submitted", len(submitted)),
             ("with_result", len(replied)), ("surface", surface),
             ("rendered_from", str(state_root())), ("updated", TODAY)]
    b = [frontmatter(pairs, ["jobsearch", "dashboard"])]
    b.append("# 🎯 Job pipeline\n\n")
    b.append(f"> [!info] Rendered {TODAY} from the **{surface}** surface\n"
             "> The ledger this is built from lives at `" + str(state_root()) + "`.\n"
             "> Rendered notes are rewritten on every run — edit the ledger, not these.\n"
             "> A run from the *other* surface does not update this copy; check `updated:` above.\n\n")
    b.append(f"**{len(submitted)} applications submitted** · {len(rows)} tracked · "
             f"{len(replied)} with a result.\n\n")

    b.append("## Applications\n\n")
    b.append("| | Company | Role | Score | Portal | Applied | Note | CV |\n")
    b.append("|---|---|---|---|---|---|---|---|\n")
    for r in sorted(rows, key=lambda x: (x.get("date", ""), x.get("company", "")), reverse=True):
        title = safe(f"{r.get('company','?')} — {r.get('role','?')}")
        cv = r.get("_cv")
        b.append(f"| {STATUS_GLYPH.get(r.get('status'), '⬜')} | {org_link(r.get('company','?'), known)} "
                 f"| [[{title}]] | {r.get('score') or ''} | {r.get('portal') or ''} "
                 f"| {r.get('date') or ''} | {r.get('result') or '—'} "
                 f"| {'[[' + cv[0] + ']]' if cv else '—'} |\n")
    b.append("\n> **Legend:** ✅ applied · 🟡 filled, awaiting submit · 🟠 ready — you apply · ⬜ not started · "
             "⛔ skipped · ❌ disqualified · 🚫 excluded · 🔵 replied · 🎯 interview · "
             "📁 applied before this system\n\n")

    b.append("## Daily shortlists\n\n")
    for p in sorted(reports, reverse=True):
        b.append(f"- [[Shortlist {p.stem}]]\n")

    b.append("\n## The rest of this layer\n\n")
    b.append(f"- [[{LESSONS[:-3]}]] — what the outcomes have actually taught\n")
    b.append(f"- [[{KPI[:-3]}]] — the KPI and the conversion numbers\n")
    b.append("- [[Memory — Jobs Agent]] — what this agent remembers and uses every run · [[Review]] — what it inferred, waiting for your OK\n")
    b.append(f"- `profile/` — the criteria every run reads (from `{profile_src}`)\n")
    # Link the brain's own career notes by their real `title:` — the filename is not what
    # resolves (brain-app.ts) — and only the ones that are actually there.
    brain = brain_at_cwd()
    if brain:
        found = []
        from paths import layer as _layer
        for sub in (_layer(brain, "career"), _layer(brain, "synthesis"), _layer(brain, "goals")):
            d = pathlib.Path(brain) / sub
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.md")):
                t = f.stem
                head = f.read_text(encoding="utf-8", errors="replace")[:400]
                if head.startswith("---"):
                    m = re.search(r"^title:\s*(.+?)\s*$", head, re.M)
                    if m:
                        t = m.group(1).strip().strip("\"'")
                found.append(f"[[{t}]]")
        if found:
            b.append("- " + " · ".join(found[:8]) + " — this brain's own career notes\n")
    return "".join(b)


def lessons_note(root, rows):
    src = root / "lessons.md"
    raw = re.sub(r"^#\s+.*\n", "", src.read_text(encoding="utf-8"), count=1) if src.is_file() else ""
    pairs = [("type", "synthesis"), ("title", "Job lessons"), ("applications", len(rows)),
             ("results", len([r for r in rows if r.get("result")])), ("updated", TODAY)]
    return frontmatter(pairs, ["jobsearch", "synthesis"]) + "# Job lessons\n" + raw


def pipeline_note(rows):
    sub = [r for r in rows if r.get("status") == "applied"]
    by_portal = {}
    for r in sub:
        by_portal.setdefault(r.get("portal", "unknown"), []).append(r)
    pairs = [("type", "synthesis"), ("title", "Job pipeline KPI"), ("submitted", len(sub)),
             ("tracked", len(rows)), ("updated", TODAY)]
    b = [frontmatter(pairs, ["jobsearch", "synthesis", "kpi"]), "# Job pipeline KPI\n\n",
         f"**North star — applications actually submitted: {len(sub)}**\n\n",
         f"Tracked: {len(rows)} · with a result: {len([r for r in rows if r.get('result')])}\n\n",
         "## By portal\n\n| Portal | Submitted |\n|---|---|\n"]
    for k, v in sorted(by_portal.items(), key=lambda x: -len(x[1])):
        b.append(f"| {k} | {len(v)} |\n")
    b.append("\n## Results\n\n")
    got = [r for r in rows if r.get("result")]
    if not got:
        b.append("No results recorded yet. Until `learn.py set-result` is run when replies arrive, "
                 "the loop cannot learn anything — `Lessons` stays empty by definition.\n")
    else:
        b.append("| Company | Role | Result | When |\n|---|---|---|---|\n")
        for r in got:
            b.append(f"| {r.get('company','')} | {r.get('role','')} | {r['result']} "
                     f"| {r.get('result_date','')} |\n")
    return "".join(b)



def contract():
    """The plugin's own studio.json (the sbl-agent/1 contract: funnels, floor, layout)."""
    here = pathlib.Path(__file__).resolve()
    for d in [here.parent] + list(here.parents):
        sj = d / "studio.json"
        if sj.is_file():
            try:
                return json.loads(sj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                break
    return {}


FALLBACK_FUNNEL = {"id": "postings", "label": "Postings", "item": "posting", "success": "interview", "stages": [
    {"id": "shortlist", "label": "Shortlist", "role": "open"}, {"id": "prepared", "label": "Prepared", "role": "open"},
    {"id": "applied", "label": "Applied", "role": "open", "gate": "confirm"}, {"id": "handoff", "label": "Hand-off", "role": "open"},
    {"id": "screen", "label": "Screen", "role": "open"}, {"id": "interview", "label": "Interview", "role": "open"},
    {"id": "offer", "label": "Offer", "role": "positive", "gate": "reason"}, {"id": "rejected", "label": "Rejected", "role": "negative", "gate": "reason"},
    {"id": "seen", "label": "Seen", "role": "parked"}, {"id": "out", "label": "Out", "role": "parked", "gate": "reason"},
    {"id": "prior", "label": "Applied myself", "role": "parked"}]}


def kpi_note(doc, rows):
    """`Job KPI.md` from the shared kpi.py over the pipeline doc (R2: numbers from scripts)."""
    k = KPIlib.compute(doc, [], today=TODAY, signals=["portal", "archetype", "market", "source"])
    sub = [r for r in rows if r.get("status") == "applied"]
    by_portal = {}
    for r in sub:
        by_portal.setdefault(r.get("portal", "unknown"), []).append(r)
    extra = ["## Applications sent", "", f"**{len(sub)} applications sent** · {len(rows)} tracked · "
             f"{len([r for r in rows if r.get('result')])} with a result.", "", "| Portal | Submitted |", "|---|---|"]
    extra += [f"| {k_} | {len(v)} |" for k_, v in sorted(by_portal.items(), key=lambda x: -len(x[1]))]
    got = [r for r in rows if r.get("result")]
    if not got:
        extra += ["", "_No results recorded yet. Until `learn.py set-result` is run when replies arrive, the loop cannot learn anything._"]
    return KPIlib.markdown(k, "Job", title="Job KPI", extra="\n".join(extra), tags=["jobsearch", "synthesis"], aliases=["Job pipeline KPI", "Job Pipeline KPI"])


def merge_into_daily(path, body):
    """The dated Shortlist note is the daily note daily.py opened FIRST (schema sbl-daily/1): the
    scout's report goes into its `## Shortlist` section between markers, and the rest of the note
    - Status, Goal, what the model wrote - is never touched. Returns True when it merged."""
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if f"schema: {DAILY_SCHEMA}" not in txt.split("---", 2)[1] if txt.startswith("---") else True:
        return False
    body = re.sub(r"\A\ufeff?\s*---\s*\n.*?\n---[ \t]*\n", "", body, count=1, flags=re.S)
    body = re.sub(r"\A\s*#\s+.*\n", "", body, count=1).strip("\n")
    new = replace_between(txt, "shortlist", body, heading="Shortlist")
    if "## Shortlist" in txt and "<!-- shortlist:begin -->" not in txt:
        pat = re.compile(r"(^## Shortlist\n)(.*?)(?=^## |^Back to \[\[|\Z)", re.S | re.M)
        new = pat.sub(lambda m: m.group(1) + "\n<!-- shortlist:begin -->\n" + body + "\n<!-- shortlist:end -->\n\n", txt, count=1)
    if new != txt:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    return True


# ---------------------------------------------------------------- the Pipeline canvas
# Studio's Pipeline canvas draws every agent's pipeline.json (schema sbl-pipeline/2, built and
# checked by pipeline_doc.py). The Jobs Agent's: every posting it has seen, shortlisted, prepared,
# sent or heard back about, as one item each, in the stages below.
OUT_STATUSES = {"skipped_walled", "skipped_policy", "skipped_knockout", "skipped_review", "disqualified",
                "excluded", "abandoned"}
SHORTLIST_SCORE = 75     # the scoring rubric's default apply floor (profile/scoring.md may differ)
SHORTLIST_DAYS = 14


def _job_stage(r):
    res = (r.get("result") or "").lower()
    if res in ("screen", "interview", "offer", "rejected"):
        return res
    st = (r.get("status") or "").lower()
    if st in ("not_started", "filled"):
        return "prepared"
    if st == "applied":
        return "applied"
    if st in ("drafted_linkedin", "handoff_portal"):
        return "handoff"
    if st == "prior_external":
        return "prior"
    if st in OUT_STATUSES or st.startswith("skipped"):
        return "out"
    return "prepared"


def write_pipeline(w, root, rows, dest):
    S, A = pdoc.stage, pdoc.action
    dest = pathlib.Path(dest)
    pre = dest.name + "/" if is_brain(dest.parent) else ""
    doc = pdoc.new("job-search", "Jobs", "#3e6ae1")
    rec = "Record that {title} moved to {stage_label}."
    NEXT = {"shortlist": ["prepared", "out"], "prepared": ["applied", "handoff", "out"], "applied": ["screen", "interview", "rejected"],
            "handoff": ["applied", "out"], "screen": ["interview", "offer", "rejected"], "interview": ["offer", "rejected"],
            "seen": ["shortlist"]}
    PROMPT = {"prepared": "Prepare my application to {title}.", "applied": "Submit my application to {title}.",
              "handoff": "Hand {title} to me — I apply on the portal myself.", "screen": rec, "interview": rec, "offer": rec,
              "rejected": rec, "out": "Skip {title}.", "seen": "Put {title} on my shortlist."}
    # the stage IDs, roles and gates are the contract's (studio.json funnels); only the prompts live here
    c = contract()
    funnels = []
    for f in c.get("funnels") or [FALLBACK_FUNNEL]:
        funnels.append(pdoc.funnel(f["id"], f["label"], f["item"], f["success"],
                                   [S(x["id"], x.get("label") or x["id"].title(), x.get("role", "open"), next=NEXT.get(x["id"], []),
                                      gate=x.get("gate", "none"), move_prompt=PROMPT.get(x["id"], "Move {title} to {stage_label}."))
                                    for x in f["stages"]], f.get("success2")))
    doc["funnels"] = funnels
    doc["floor"] = [pdoc.floor_group(g["id"], g["label"], g["stages"], g.get("funnel")) for g in (c.get("floor") or [])]
    items, keys = [], set()
    for r in rows:
        key = str(r.get("job_key") or "")
        if not key or key in keys:
            continue
        keys.add(key)
        stage = _job_stage(r)
        title = f"{r.get('company', '?')} — {r.get('role', '?')}"
        try:
            score = int(float(r.get("score"))) if r.get("score") not in (None, "") else None
        except (TypeError, ValueError):
            score = None
        flags = []
        needs = ""
        if stage == "handoff":
            flags, needs = ["needs-you"], "Apply on the portal yourself — the answers are prepared"
        elif (r.get("status") or "") == "filled":
            flags, needs = ["needs-you"], "Filled — waiting for your submit"
        attrs = {"portal": r.get("portal") or "", "market": r.get("market") or "", "archetype": r.get("archetype") or "",
                 "status": r.get("status") or "", "source": r.get("source") or "", "day": str(r.get("date") or "")[:10]}
        it = pdoc.item(key, title, stage, funnel="postings", sub=" · ".join(x for x in (r.get("location") or "", r.get("portal") or "") if x),
                       score=score, flags=flags or None, needs=needs or None, url=r.get("url") or None,
                       note=(pre + r["_note"]) if r.get("_note") else None, attrs=attrs,
                       stage_since=str(r.get("result_date") or r.get("date") or "") or None, updated=str(r.get("date") or "") or None)
        if stage not in ("out", "prior", "rejected", "seen"):
            steps = [{"label": "Shortlisted", "status": "done"},
                     {"label": "CV built", "status": "done" if r.get("_cv") else "upcoming"},
                     {"label": "Filled", "status": "done" if (r.get("status") in ("filled", "applied")) else "upcoming"},
                     {"label": "Sent", "status": "done" if r.get("status") == "applied" else ("due" if stage == "prepared" else "upcoming"),
                      "date": str(r.get("date") or "") if r.get("status") == "applied" else ""},
                     {"label": "Result", "status": "done" if r.get("result") else "waiting", "date": str(r.get("result_date") or "")}]
            kv = {k: v for k, v in (("Applied", r.get("date")), ("Portal", r.get("portal")), ("Source", r.get("source")),
                                    ("Location", r.get("location")), ("Comp", r.get("comp")), ("Result", r.get("result")))
                  if v not in (None, "")}
            cv = r.get("_cv")
            it["detail"] = {"kv": kv, "steps": steps,
                            "evidence": [{"label": "The posting", "url": r.get("url"), "seen": str(r.get("date") or "")}] if r.get("url") else [],
                            "links": [pre + f"{pathlib.Path(r['_note']).parent}/{cv[0]}.md"] if cv and r.get("_note") else []}
        items.append(it)
    # the scout's seen postings: recent and above the floor = the shortlist, the rest = seen
    try:
        seen = json.loads((root / "seen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    applied_urls = {str(r.get("url") or "").split("?")[0].rstrip("/") for r in rows}
    today = datetime.date.today()
    for k, v in sorted(seen.items()):
        url = str(v.get("url") or "").split("?")[0].rstrip("/")
        if url and url in applied_urls:
            continue
        iid = "seen-" + re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")[:80]
        if iid in keys:
            continue
        keys.add(iid)
        try:
            score = int(float(v.get("score"))) if v.get("score") not in (None, "") else None
        except (TypeError, ValueError):
            score = None
        try:
            age = (today - datetime.date.fromisoformat(str(v.get("first_seen"))[:10])).days
        except ValueError:
            age = 999
        stage = "shortlist" if score is not None and score >= SHORTLIST_SCORE and age <= SHORTLIST_DAYS else "seen"
        it = pdoc.item(iid, f"{v.get('company', '?')} — {v.get('title', '?')}", stage, funnel="postings", score=score,
                       url=v.get("url") or None, stage_since=v.get("first_seen"), updated=v.get("first_seen"),
                       attrs={"status": "seen", "source": str(v.get("source") or ""), "day": str(v.get("first_seen") or "")[:10]})
        if stage == "shortlist":
            it["detail"] = {"evidence": [{"label": "The posting", "url": v.get("url"), "seen": v.get("first_seen")}] if v.get("url") else []}
        items.append(it)
    doc["items"] = items
    sent = sum(1 for r in rows if r.get("status") == "applied")
    interviews = sum(1 for r in rows if (r.get("result") or "") in ("interview", "offer"))
    doc["headline"] = {"label": "interviews", "value": interviews, "n": sent, "period": "all time"}
    doc["throughput"] = pdoc.throughput((contract().get("throughput") or {}).get("label") or "applications / day",
                                        [r.get("applied_date") or r.get("date") for r in rows if r.get("status") == "applied"], TODAY)
    doc["stats"] = [{"label": "interviews / applications", "num": interviews, "den": sent, "min_n": 20},
                    {"label": "screens or better / applications", "num": sum(1 for r in rows if (r.get("result") or "") in ("screen", "interview", "offer")), "den": sent, "min_n": 20}]
    doc["lenses"] = [pdoc.lens("score", "Score", "score", domain=[40, 100]),
                     pdoc.lens("age", "Age", "stage_since", scale="days", buckets=[3, 7, 14, 30]),
                     pdoc.lens("needs", "Needs you", "flags", scale="flag", value="needs-you"),
                     pdoc.lens("today", "New today", "attrs.day", scale="flag", value=TODAY)]
    doc["facets"] = [pdoc.facet("portal", "Portal", "attrs.portal"), pdoc.facet("market", "Market", "attrs.market"),
                     pdoc.facet("archetype", "Role type", "attrs.archetype"), pdoc.facet("status", "Status", "attrs.status")]
    doc["panel"] = {
        "top": ["{stage_label}", "score {score}", "{attrs.portal}"],
        "sections": [{"type": "kv", "label": "The role", "from": "detail.kv"},
                     {"type": "steps", "label": "Application", "from": "detail.steps"},
                     {"type": "evidence", "label": "Source", "from": "detail.evidence"},
                     {"type": "links", "label": "CV sent", "from": "detail.links"}],
        "actions": [
            A("Apply to it", "Apply to {title}: build the tailored CV, fill the employer's form, verify every field, then finish the way my autonomy setting says.", "primary", stages=["shortlist", "seen"]),
            A("Apply to these {n}", "Apply to these {n} roles, one by one, at my autonomy setting: {titles}.", "primary", stages=["shortlist"], bulk=True),
            A("Tailor my CV", "Tailor my CV for {title} and show it to me.", stages=["shortlist", "prepared"]),
            A("Finish and send", "Finish my application to {title} and send it the way my autonomy setting says.", "primary", stages=["prepared"]),
            A("Open the portal", "Open the portal for {title} with my prepared answers — I will apply myself.", "primary", stages=["handoff"]),
            A("Record what came back", "I heard back from {title} — I will paste the email or tell you what happened.", "primary", stages=["applied"]),
            A("Prep me", "Prep me for my {stage_label} with {title}: the role, my stories that fit, and what they will ask.", "primary", stages=["screen", "interview"]),
            A("Skip", "Skip {title} — ask me why first.", stages=["shortlist", "prepared"]),
        ],
    }
    doc["actions"] = [A("Run today's search", "Run today's job search: sweep the boards against my criteria and give me today's ranked shortlist.", "primary"),
                      A("How is it going?", "Show me the KPI: interview rate by archetype, score band and portal.")]
    doc["generated"] = max([str(r.get("date") or "") for r in rows] + [str(v.get("first_seen") or "") for v in seen.values()] + [""])
    STG.apply(doc, dest / "profile")          # the user's labels / hidden stages (profile/stages.json)
    probs = pdoc.check(doc)
    if probs:
        print("  ! pipeline.json not written: " + "; ".join(probs[:3]), file=sys.stderr)
        return None
    w.text("pipeline.json", pdoc.dumps(doc), machine=True)
    return doc

# ---------------------------------------------------------------- the run
def render(dest, quiet=False):
    root = state_root()
    w = Writer(dest, machinery_dir(root, dest) / MANIFEST, quiet)
    on_disk = scan_app_dirs(root)
    rows = merge_rows(load_outcomes(root), on_disk)
    known = org_index(dest)

    taken, labels = set(), {}
    for r in rows:
        key = r.get("job_key", "")
        app, day = find_app_dir(root, key)
        # Applications are grouped by DAY in the vault exactly as they are in the ledger,
        # so a folder with two hundred applications in it stays readable and "what went out
        # on Friday" is one click. Fall back to flat only when the day is unknowable.
        day = day or str(r.get("date") or "")
        base = f"applications/{day}/{key}" if DAY_RE.match(day or "") else f"applications/{key}"
        cvs = []
        note = safe(f"{r.get('company','?')} — {r.get('role','?')}")
        if app:
            # The working files job-apply writes beside the CV. Rendered under their own
            # titles — they are the interview-prep pack — and never mistaken for a CV,
            # which is what a bare "every .md but ANSWERS.md" rule would do.
            for fname, kind in WORKING_FILES.items():
                src = app / fname
                if src.is_file():
                    w.text(f"{base}/{note} · {kind}.md", src.read_text(encoding="utf-8"))
            for md in sorted(app.glob("*.md")):
                if md.name == "ANSWERS.md" or md.name in WORKING_FILES:
                    continue
                if not CV_NAME_RE.search(md.stem):
                    kind = re.sub(r"[-_]+", " ", md.stem).strip().capitalize() or md.stem
                    w.text(f"{base}/{note} · {kind}.md", flatten_links(md.read_text(encoding="utf-8")))
                    continue
                # One label per CV, allocated HERE. It used to be allocated once before the
                # loop and again at the end of every iteration, so each application burned a
                # spare name and a company's second role came out "CV Foo 2" rather than
                # "CV Foo Industries".
                label = cv_label(r.get("company", "?"), r.get("role", ""), taken)
                w.text(f"{base}/{label}.md",
                       retitle(md.read_text(encoding="utf-8"), label))
                pdf_src = md.with_suffix(".pdf")
                pdf_name = f"{label}.pdf" if pdf_src.is_file() else None
                if pdf_name:
                    w.binary(f"{base}/{pdf_name}", pdf_src)
                cvs.append((label, pdf_name))
            # The submission's confirmation screenshot (job-apply takes one small shot of the
            # "thank you" page), beside the note that embeds it.
            conf = app / "confirmation.png"
            if conf.is_file():
                w.binary(f"{base}/{note} · Confirmation.png", conf)
        r["_cv"] = cvs[0] if cvs else None
        if cvs:
            labels[key] = cvs[0]
        w.text(f"{base}/{note}.md", application_note(r, app, cvs, known))
        r["_note"] = f"{base}/{note}.md"

    reports = sorted((root / "reports").glob("*.md")) if (root / "reports").is_dir() else []
    for p in reports:
        body = report_note(p, labels)
        target = pathlib.Path(dest) / f"reports/Shortlist {p.stem}.md"
        if target.is_file() and merge_into_daily(target, body):
            continue           # the daily note owns the file; the report sits in its Shortlist section
        w.text(f"reports/Shortlist {p.stem}.md", body)

    doc = write_pipeline(w, root, rows, dest)
    w.text(LESSONS, lessons_note(root, rows))
    if doc:
        w.text(KPI, kpi_note(doc, rows))

    prof = pathlib.Path(dest) / "profile"
    w.text(DASHBOARD, dashboard_note(rows, reports, dest,
                                     prof if prof.is_dir() else "not onboarded yet", known))

    # our own manifest - deliberately NOT SBL's _GENERATED.json, so the vault engine treats these
    # as user files and never prunes them. profile/ is input and stays out of it.
    gone = w.finish()

    (machinery_dir(root, dest) / BUILD_REPORT).write_text(
        frontmatter([("type", "report"), ("title", "Job layer render report"),
                     ("date", TODAY), ("written", w.wrote), ("unchanged", w.same)],
                    ["jobsearch", "report", "build"])
        + f"# Render report\n\nRendered: {TODAY}\n\n"
        f"- source ledger: `{root}`\n- notes written: {w.wrote}\n- unchanged: {w.same}\n"
        f"- applications: {len(rows)}\n- reports: {len(reports)}\n"
        + (f"\n## Kept as you edited them ({len(w.kept)})\n\nThe fresh render sits beside each as `<name>.new.md`:\n\n"
           + "".join(f"- `{k}`\n" for k in w.kept) if w.kept else "")
        + (f"\n## No longer in the ledger ({len(gone)})\n\nLeft in place — nothing is deleted "
           "automatically. Remove them yourself if you want them gone:\n\n"
           + "".join(f"- `{g}`\n" for g in gone) if gone else ""), encoding="utf-8")

    if not quiet:
        print(f"\n{w.wrote} written · {w.same} unchanged · {len(w.kept)} kept (yours) · {len(rows)} applications "
              f"-> {dest}", file=sys.stderr)
        if gone:
            print(f"{len(gone)} file(s) no longer in the ledger, left in place — see "
                  f"{BUILD_REPORT}", file=sys.stderr)
    return w


# ---------------------------------------------------------------- migration
def migrate_layout(dest, dry_run=False):
    """One-time move to the layout this renderer now writes. MOVES ONLY — never deletes.

    Three things changed at once and an existing install has all three in the old shape:
      1. `45-jobs/applications/<key>/`        -> `45-jobs/applications/<day>/<key>/`
      2. `45-jobs/_state/`                    -> `<brain>/.plugins/job-search/`
      3. `_JOBS_GENERATED.json` / `_JOBS_BUILD_REPORT.md` -> beside the ledger

    Without (1) a re-render would simply write the dated folders NEXT TO the flat ones and
    leave the user with both. Every move is printed and an existing destination is refused
    rather than overwritten.
    """
    dest = pathlib.Path(dest)
    moves, skipped = [], []

    def plan(src, dst):
        if not src.exists():
            return
        if dst.exists():
            skipped.append((src, dst, "destination exists"))
            return
        moves.append((src, dst))

    # --- 2. the ledger leaves the vault tree ---------------------------------
    brain = brain_at_cwd(dest) or brain_at_cwd()
    legacy = dest / LEGACY_STATE_DIRNAME
    new_state = brain_state_root(brain) if brain else None
    if legacy.is_dir() and new_state is not None:
        plan(legacy, new_state)
    ledger = new_state if new_state is not None else state_root()

    # --- 1. applications group by day ----------------------------------------
    # The day comes from the ledger's own dated folders first, then the outcome row, then
    # the folder's mtime. A key we cannot date is reported, not guessed at silently.
    on_disk = scan_app_dirs(legacy if legacy.is_dir() else ledger)
    by_key = {r.get("job_key", ""): str(r.get("date") or "")
              for r in load_outcomes(legacy if legacy.is_dir() else ledger)}
    apps = dest / "applications"
    if apps.is_dir():
        for d in sorted(apps.iterdir()):
            if not d.is_dir() or DAY_RE.match(d.name):
                continue                       # already dated
            day = ""
            if d.name in on_disk:
                day = on_disk[d.name][1]
            if not DAY_RE.match(day or ""):
                day = by_key.get(d.name, "")
            if not DAY_RE.match(day or ""):
                day = datetime.date.fromtimestamp(d.stat().st_mtime).isoformat()
            plan(d, apps / day / d.name)

    # --- 3. the machinery files ----------------------------------------------
    target = new_state if new_state is not None else ledger
    for name in (MANIFEST, BUILD_REPORT):
        plan(dest / name, target / name)

    # --- 4. the standard layout: `Job Pipeline KPI.md` -> `Job KPI.md` (alias kept) ---------
    # through the manifest: a user-edited copy stays where it is and is reported, never moved.
    std = []
    if (dest / KPI_OLD).is_file() and not (dest / KPI).exists():
        mw = Writer(dest, target / MANIFEST, quiet=True)
        rep_ = mw.migrate_layout([(KPI_OLD, KPI, "Job pipeline KPI")], dry_run=dry_run)
        std = rep_["moved"]
        for left in rep_["left"]:
            skipped.append((dest / left, dest / KPI, "edited by you - left in place"))
        for a_, b_ in std:
            print(f"{'would move' if dry_run else 'move'}  {dest / a_}\n      -> {dest / b_}  (aliases: Job pipeline KPI)", file=sys.stderr)

    for src, dst in moves:
        print(f"{'would move' if dry_run else 'move'}  {src}\n      -> {dst}", file=sys.stderr)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    # The manifest still lists the flat paths, so without this every later render would
    # report all of them as "no longer in the ledger" forever — a permanent false alarm
    # about files that were moved, not lost.
    if not dry_run:
        mf = (new_state if new_state is not None else ledger) / MANIFEST
        if mf.is_file():
            try:
                data = json.loads(mf.read_text(encoding="utf-8")) or {}
            except json.JSONDecodeError:
                data = {}
            files, out = data.get("files") or {}, {}
            for rel, digest in files.items():
                parts = rel.split("/")
                if len(parts) >= 3 and parts[0] == "applications" and not DAY_RE.match(parts[1]):
                    key = parts[1]
                    day = on_disk.get(key, (None, ""))[1] or by_key.get(key, "")
                    if DAY_RE.match(day or ""):
                        parts = ["applications", day] + parts[1:]
                        rel = "/".join(parts)
                out[rel] = digest
            data["files"] = out
            mf.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"manifest repointed at the new paths ({len(out)} entries)", file=sys.stderr)
    for src, dst, why in skipped:
        print(f"SKIPPED {src} -> {dst}  ({why}; nothing was removed)", file=sys.stderr)
    print(f"\n{len(moves) + len(std)} moved, {len(skipped)} skipped. Nothing was deleted.", file=sys.stderr)
    return 0 if not skipped else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", help="render here instead of the resolved surface")
    ap.add_argument("--import-to", dest="import_to",
                    help="one-time copy of the rendered layer to another surface")
    ap.add_argument("--force", action="store_true", help="allow --import-to over an existing layer")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--migrate-layout", action="store_true",
                    help="one-time move to the dated-applications + hidden-ledger layout")
    ap.add_argument("--dry-run", action="store_true", help="with --migrate-layout: show, do not move")
    a = ap.parse_args()

    dest = pathlib.Path(os.path.expanduser(a.dest)) if a.dest else render_dir()
    if a.migrate_layout:
        return migrate_layout(dest, a.dry_run)
    if not a.quiet:
        print(f"surface: {surface_root()}\nrendering to: {dest}", file=sys.stderr)
    render(dest, a.quiet)

    if a.import_to:
        tgt = pathlib.Path(os.path.expanduser(a.import_to))
        if (tgt / MANIFEST).is_file() and not a.force:
            print(f"\nrefusing: {tgt} already holds a rendered layer. Re-run with --force only if "
                  "you mean to overwrite what is there.", file=sys.stderr)
            return 1
        n = 0
        for src in pathlib.Path(dest).rglob("*"):
            if src.is_dir() or "profile" in src.relative_to(dest).parts:
                continue          # profile is per-surface; importing it would fork it
            out = tgt / src.relative_to(dest)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            n += 1
        print(f"imported {n} files -> {tgt}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
