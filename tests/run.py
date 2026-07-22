#!/usr/bin/env python3
"""
tests/run.py — runnable check harness for Second Brain Link.

Builds a vault from each synthetic fixture export under tests/fixtures/<source>/
and asserts the invariants that must never regress:
  - valid YAML frontmatter on every note
  - every real [[wikilink]] resolves to a note basename (no dangling links)
  - all dates in frontmatter are ISO (YYYY-MM-DD / YYYY-MM / YYYY)
  - PII sweep: no emails / phones / known message-body fixtures leak into the vault
  - profiler runs and emits schema_map + mindmap + brain_structure
  - read_csv skips a 'Notes:' preamble (the real-LinkedIn drift we fixed)

Standard library only. Exit code 0 = all green, 1 = failure.

Usage: python3 tests/run.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "engine" / "scripts"
FIXTURES = REPO / "tests" / "fixtures"
# entity-foldered fixtures (consistent personal/company layout)
FX_ADA = FIXTURES / "personal" / "ada" / "linkedin"      # a person export
FX_ACME_LIC = FIXTURES / "company" / "acme" / "linkedin_company"
FX_ACME_GW = FIXTURES / "company" / "acme" / "google_workspace"
FX_ACME_SLACK = FIXTURES / "company" / "acme" / "slack"
sys.path.insert(0, str(SCRIPTS))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail and not cond else ""))


ISO = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\+?\d[\d ().-]{9,}\d")
DATE_KEYS = {"created", "updated", "last_contact"}


def parse_frontmatter(text):
    """Tiny YAML-frontmatter reader (key: scalar / list). Returns dict or raises."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    block = text[3:end].strip("\n").splitlines()
    fm, key = {}, None
    for ln in block:
        if re.match(r"^\s*-\s+", ln):
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(ln.strip()[2:].strip())
            continue
        m = re.match(r"^([A-Za-z0-9_]+):(.*)$", ln)
        if not m:
            raise ValueError(f"bad frontmatter line: {ln!r}")
        key, val = m.group(1), m.group(2).strip()
        fm[key] = val if val else []
    return fm


def vault_invariants(vault: Path, label: str, pii_needles):
    notes = list(vault.rglob("*.md"))
    basenames = {p.stem for p in notes}
    bad_yaml, bad_dates, dangling, pii_hits = [], [], [], []
    link_re = re.compile(r"\[\[([^\]|#]+)")
    code_re = re.compile(r"`[^`]*`")
    # Home.md (MOC) and the in-vault CLAUDE.md intentionally carry aspirational /
    # example wikilinks (e.g. [[target-companies]] which only exists when there's
    # career data, or `[[Acme]]` as a how-to example), so they're exempt from the
    # dangling-link check — but still validated for YAML/PII like every other note.
    MOC_EXEMPT = {"Home.md", "CLAUDE.md"}
    for p in notes:
        if "_quarantine" in p.parts:
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        try:
            fm = parse_frontmatter(txt)
        except Exception as e:
            bad_yaml.append(f"{p.name}: {e}")
            continue
        for k in DATE_KEYS:
            v = fm.get(k)
            if isinstance(v, str) and v and not ISO.match(v.strip('"')):
                bad_dates.append(f"{p.name}:{k}={v}")
        if p.name not in MOC_EXEMPT:
            scrubbed = code_re.sub("", txt)  # ignore links inside inline code
            for tgt in link_re.findall(scrubbed):
                t = tgt.strip().strip('"')
                if t and t not in basenames:
                    dangling.append(f"{p.name} -> [[{t}]]")
        for needle in pii_needles:
            if needle and needle in txt:
                pii_hits.append(f"{p.name}: {needle!r}")
    # generic PII regex sweep too
    for p in notes:
        if "_quarantine" in p.parts:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if EMAIL.search(t):
            pii_hits.append(f"{p.name}: email-pattern")
        if PHONE.search(t):
            pii_hits.append(f"{p.name}: phone-pattern")
    check(f"{label}: valid YAML on all notes", not bad_yaml, str(bad_yaml[:3]))
    check(f"{label}: ISO dates", not bad_dates, str(bad_dates[:3]))
    check(f"{label}: no dangling links", not dangling, str(dangling[:3]))
    check(f"{label}: PII sweep clean", not pii_hits, str(pii_hits[:3]))


def test_read_csv_preamble():
    from sources.common import read_csv
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "Connections.csv"
        p.write_text(
            'Notes:\n'
            '"When exporting your connection data, you may notice that some of '
            'the email addresses are missing."\n'
            '\n'
            'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
            'Ada,Lovelace,https://x/ada,,Analytical Engines,Engineer,01 Jan 2020\n',
            encoding="utf-8")
        rows = read_csv(p)
        keys = list(rows[0].keys()) if rows else []
        check("read_csv skips Notes: preamble",
              keys[:2] == ["First Name", "Last Name"] and len(rows) == 1, str(keys))
        # single-column file still works
        s = Path(d) / "Skills.csv"
        s.write_text("Name\nPython\nObsidian\n", encoding="utf-8")
        sr = read_csv(s)
        check("read_csv single-column ok",
              list(sr[0].keys()) == ["Name"] and len(sr) == 2, str(sr))


def test_urls():
    from sources.common import Collector, canonical_url, nk
    # canonical_url normalizes so the same profile dedupes
    a = canonical_url("https://www.LinkedIn.com/in/grace/?trk=x")
    b = canonical_url("http://linkedin.com/in/grace")
    check("canonical_url normalizes/dedupes", a == b == "https://linkedin.com/in/grace", f"{a!r} vs {b!r}")
    # add_person stores url and merge-fills it from a later source
    c = Collector()
    c.add_person("linkedin", "Grace Hopper", url="https://www.linkedin.com/in/grace/")
    c.add_person("facebook", "Grace Hopper")  # same person, no url
    rec = c.people[nk("Grace Hopper")]
    check("person url stored + merged across sources",
          rec["url"] == "https://linkedin.com/in/grace" and rec["sources"] == {"linkedin", "facebook"},
          str(rec))
    # add_org carries a url too
    c.add_org("linkedin", "Acme Cloud", "employer", url="https://acme.example/")
    check("org url stored", c.orgs["Acme Cloud"].get("url") == "https://acme.example", str(c.orgs.get("Acme Cloud")))


def test_selfheal():
    import selfheal
    # classify maps known errors to actionable causes
    cause_k, hint_k = selfheal.classify(KeyError("Company Name"))
    check("selfheal classifies KeyError", "column" in cause_k.lower() or "key" in cause_k.lower(), cause_k)
    cause_u, _ = selfheal.classify(UnicodeDecodeError("utf-8", b"", 0, 1, "bad"))
    check("selfheal classifies encoding error", "utf-8" in cause_u.lower() or "encoding" in cause_u.lower(), cause_u)
    # write_error_report produces a well-formed _ERROR.md
    with tempfile.TemporaryDirectory() as d:
        try:
            raise KeyError("Application Date")
        except Exception as e:
            p = selfheal.write_error_report(d, "unit-test", e)
        t = Path(p).read_text()
        check("_ERROR.md well-formed",
              "## To fix" in t and "## Traceback" in t and "Self-heal protocol" in t, p)
    # guarded_extract swallows a failing adapter (build continues)
    from sources.common import Collector
    class _Boom:
        NAME = "boom"
    logs = []
    out = selfheal.guarded_extract(_Boom(), lambda: (_ for _ in ()).throw(KeyError("x")),
                                   Collector(), log=logs.append)
    check("guarded_extract recovers", out == set() and any("boom" in l for l in logs), str(logs[:1]))


def test_doctor_and_autoheal():
    """Subprocess: --doctor writes _DOCTOR.md; a malformed file auto-recovers."""
    li = FX_ADA
    if not li.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(li),
                            "-o", str(out), "--doctor"], capture_output=True, text=True)
        check("--doctor runs + writes _DOCTOR.md",
              r.returncode == 0 and (out / "_DOCTOR.md").exists(), r.stderr[-200:])
    # auto-recover: copy fixture + inject a malformed file, build must still finish
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "exp"
        src.mkdir()
        for f in li.glob("*.csv"):
            (src / f.name).write_bytes(f.read_bytes())
        (src / "Garbage.csv").write_bytes(b"\xff\xfe not,a,valid\x00 csv\xff")  # bad bytes
        out = Path(d) / "out"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(src),
                            "-o", str(out)], capture_output=True, text=True)
        check("build auto-recovers from a malformed file",
              r.returncode == 0 and (out / "Home.md").exists(), r.stderr[-200:])


def test_full_mode():
    """--full captures PII + a raw-data layer; DEFAULT stays privacy-clean.
    (run_fixture already asserts the default build is PII-clean.)"""
    li = FX_ADA
    if not li.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "vault"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(li),
                            "-o", str(out), "--full"], capture_output=True, text=True)
        check("full build runs", r.returncode == 0 and (out / "Home.md").exists(), r.stderr[-200:])
        # the email fixture in Connections.csv must appear on the person note (owner wanted it)
        ppl_text = "\n".join(p.read_text() for p in (out / "10-people").glob("*.md")) if (out / "10-people").is_dir() else ""
        check("full mode captures email PII on person note",
              "fixture@example.com" in ppl_text, "email not on person note")
        # the owner's OWN quarantined records get folded into 00-me/ (not a raw-data tree)
        me_text = "\n".join(p.read_text() for p in (out / "00-me").glob("*.md")) if (out / "00-me").is_dir() else ""
        check("full mode folds owner quarantined records into 00-me",
              "fixture@example.com" in me_text, "Email Addresses not in 00-me")
        check("no redundant raw-data tree", not (out / "raw-data").exists(), "raw-data still present")


def test_company_and_gbrain():
    """Company adapters root on the org; quarantine + message-body rules hold;
    GBrain emitter produces a valid repo for both subjects; 4-cell matrix works."""
    S = SCRIPTS
    # linkedin_company → company-rooted Obsidian
    li_c = FX_ACME_LIC
    if li_c.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(S / "build_vault.py"), str(li_c),
                                "-o", str(out)], capture_output=True, text=True)
            check("company: linkedin_company builds", r.returncode == 0, r.stderr[-200:])
            check("company: roots on 00-org", (out / "00-org").is_dir())
            check("company: data-handling note", (out / "00-org" / "data-handling.md").exists())
            # default mode strips employee emails
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("company: employee email stripped by default",
                  "ghopper@example.com" not in allmd, "email leaked")
    # google_workspace → loginaudit quarantined
    gw = FX_ACME_GW
    if gw.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(S / "build_vault.py"), str(gw),
                                "-o", str(out)], capture_output=True, text=True)
            check("company: google_workspace builds", r.returncode == 0, r.stderr[-200:])
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("company: loginaudit quarantined", "loginaudit` — quarantined" in cov, cov[:200])
    # slack → message bodies never leak
    sl = FX_ACME_SLACK
    if sl.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(S / "build_vault.py"), str(sl),
                                "-o", str(out)], capture_output=True, text=True)
            check("company: slack builds", r.returncode == 0, r.stderr[-200:])
            leaked = any("secret-body-do-not-leak" in p.read_text() for p in out.rglob("*.md"))
            check("company: slack message bodies never leak", not leaked, "body leaked")
    # GBrain emitter (person) + 4-cell matrix smoke
    li = FX_ADA
    if li.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(S / "build_vault.py"), str(li),
                                "-o", str(out), "--emit", "both"], capture_output=True, text=True)
            check("gbrain: --emit both builds", r.returncode == 0, r.stderr[-200:])
            check("gbrain: obsidian subdir present", (out / "obsidian" / "Home.md").exists())
            check("gbrain: gbrain repo present", any((out / "gbrain" / "people").glob("*.md")))
            check("gbrain: manifest present", (out / "gbrain" / "gbrain.manifest.json").exists())
            # default gbrain repo stays PII-clean
            gtext = "\n".join(p.read_text() for p in (out / "gbrain").rglob("*.md"))
            check("gbrain: PII-clean by default", "fixture@example.com" not in gtext, "email leaked")


def test_company_deepening():
    """The deepened company-source features: Slack day-files are consumed (not
    double-handled into 99-uncategorized), channel membership/topic land on the
    vault, Org Unit / Department become department orgs + dept/<slug> person tags,
    calendar attendees render as wikilinks, and the company goals (onboarding,
    whoknows) build from those structure tags."""
    S = SCRIPTS
    # slack: coverage fix + membership tags + channel org notes
    if FX_ACME_SLACK.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(S / "build_vault.py"),
                            str(FX_ACME_SLACK), "-o", str(out)],
                           capture_output=True, text=True)
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("deepen: slack day-file consumed (not uncategorized)",
                  "`20240401` — mapped" in cov, cov[-300:])
            check("deepen: no 99-uncategorized dir for slack",
                  not (out / "99-uncategorized").exists()
                  or not any((out / "99-uncategorized").glob("*.md")))
            grace = out / "10-people" / "Grace Hopper.md"
            gtxt = grace.read_text() if grace.exists() else ""
            check("deepen: slack channel membership tag on person",
                  "channel/engineering" in gtxt, gtxt[:300])
            # obsidian_name strips the illegal '#' from the note filename
            chan = out / "15-organizations" / "general.md"
            check("deepen: slack channel org note", chan.exists())
    # google_workspace: departments + calendar attendees
    if FX_ACME_GW.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(S / "build_vault.py"),
                            str(FX_ACME_GW), "-o", str(out)],
                           capture_output=True, text=True)
            dept = out / "15-organizations" / "Engineering.md"
            check("deepen: workspace Org Unit → department org", dept.exists())
            grace = out / "10-people" / "Grace Hopper.md"
            gtxt = grace.read_text() if grace.exists() else ""
            check("deepen: dept tag on employee", "dept/engineering" in gtxt, gtxt[:300])
            # company subject → meetings live in 60-knowledge/meetings.md
            ev = out / "60-knowledge" / "meetings.md"
            etxt = ev.read_text() if ev.exists() else ""
            check("deepen: calendar attendees render as wikilinks",
                  "with: [[Grace Hopper]], [[Alan Turing]]" in etxt, etxt[:400])
            # a calendar attendee becomes a person note (links resolve)
            check("deepen: attendee registered as person",
                  (out / "10-people" / "Katherine Johnson.md").exists())
    # linkedin_company: Department column → department org + tag
    if FX_ACME_LIC.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(S / "build_vault.py"),
                            str(FX_ACME_LIC), "-o", str(out)],
                           capture_output=True, text=True)
            allmd = "\n".join(p.read_text() for p in (out / "10-people").glob("*.md")) \
                if (out / "10-people").is_dir() else ""
            has_dept_col = False
            for p in FX_ACME_LIC.glob("EmployeeList*.csv"):
                has_dept_col = "department" in p.read_text().splitlines()[0].lower()
            if has_dept_col:
                check("deepen: linkedin_company Department tag", "dept/" in allmd, allmd[:300])
    # company goals build from the whole acme entity
    acme_entity = FIXTURES / "company" / "acme"
    if acme_entity.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(S / "build_vault.py"),
                            str(acme_entity), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            r = subprocess.run([sys.executable, str(S / "analyze.py"), str(out),
                                "--goals", "onboarding,whoknows"],
                               capture_output=True, text=True)
            check("deepen: company goals run", r.returncode == 0, r.stderr[-300:])
            onb = out / "95-goals" / "onboarding.md"
            wkw = out / "95-goals" / "whoknows.md"
            check("deepen: onboarding.md written", onb.exists())
            check("deepen: whoknows.md written", wkw.exists())
            otxt = onb.read_text() if onb.exists() else ""
            wtxt = wkw.read_text() if wkw.exists() else ""
            check("deepen: onboarding lists teams", "## Teams and where people sit" in otxt
                  and "engineering" in otxt.lower(), otxt[:400])
            check("deepen: whoknows maps channels", "## By channel" in wtxt
                  and "#general" in wtxt, wtxt[:400])


def test_p0_fixes():
    """P0 regressions: a personal Takeout containing Mail/*.mbox must build ONE
    personal brain (no bogus company sibling) on the run() path; a loose mbox
    next to a personal export is demoted the same way; LinkedIn's previously
    silent files (saved items / rich media / job alerts) now extract or show
    honestly as skipped; deliberate data/company/<co>/email imports still work."""
    mail = FIXTURES / "personal" / "mailned"
    if (mail / "google").is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(mail / "google"), "-o", str(out)],
                               capture_output=True, text=True)
            check("p0: takeout-with-mail builds", r.returncode == 0, r.stderr[-300:])
            check("p0: takeout-with-mail → ONE personal brain (no company sibling)",
                  (out / "Home.md").exists() and not (out / "company-brain").exists()
                  and not (out / "personal-brain").exists(), str(list(out.iterdir())))
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("p0: takeout mail bodies/subjects never leak",
                  "secret-body-do-not-leak" not in allmd, "needle leaked")
    if (mail / "mixed").is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(mail / "mixed"), "-o", str(out)],
                               capture_output=True, text=True)
            check("p0: loose mbox beside personal export → demoted (single brain)",
                  r.returncode == 0 and (out / "Home.md").exists()
                  and not (out / "company-brain").exists(),
                  r.stdout[-200:] + r.stderr[-200:])
            check("p0: demotion says why", "skipping them here" in r.stdout, r.stdout[-300:])
    # deliberate company email import still fires (regression)
    glx_email = FIXTURES / "company" / "globex" / "email"
    if glx_email.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(glx_email), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            check("p0: deliberate email/ import still builds people",
                  (out / "10-people" / "Hank Scorpio.md").exists())
    # linkedin: saved-item titles → interests; job alerts → prefs; richmedia → skipped
    if FX_ADA.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(FX_ADA), "-o", str(out)], capture_output=True, text=True)
            interests = out / "30-voice" / "interests.md"
            itxt = interests.read_text() if interests.exists() else ""
            check("p0: linkedin saved-item title extracted",
                  "saved: The Analytical Engine explained" in itxt, itxt[:300])
            prefs = out / "40-career" / "preferences.md"
            ptxt = prefs.read_text() if prefs.exists() else ""
            check("p0: linkedin job alert criteria → prefs",
                  "mathematician remote" in ptxt, ptxt[:300])
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("p0: links-only richmedia shows as skipped (honest coverage)",
                  "`richmedia` — skipped (low-signal, by design" in cov, cov[-500:])


def test_google_expansion():
    """P1a: the Takeout slices the engine used to ignore now extract — semantic
    location visits (aggregated places), My Activity search/ads, YouTube
    likes/comments — and the excluded-by-design slices show as `skipped`."""
    owner_g = FIXTURES / "personal" / "owner" / "google"
    if not owner_g.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(owner_g), "-o", str(out)],
                           capture_output=True, text=True)
        check("p1a: takeout builds", r.returncode == 0, r.stderr[-300:])
        # semantic visits → aggregated place with visit count
        museum = out / "85-places" / "The British Museum.md"
        mtxt = museum.read_text() if museum.exists() else ""
        check("p1a: semantic location visit → place", museum.exists())
        check("p1a: visits aggregated (2 visits, one note)",
              "2 visit(s)" in mtxt, mtxt[:300])
        check("p1a: E7 coords converted", "lat: 51.5085" in mtxt, mtxt[:300])
        # My Activity
        allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
        check("p1a: my-activity search extracted",
              "analytical engine blueprints" in allmd)
        check("p1a: my-activity non-search rows ignored",
              "Visited some page" not in allmd)
        check("p1a: ads activity → mirror", "Science equipment retailers" in allmd)
        # YouTube likes + comments
        check("p1a: liked video title → interest",
              "Mechanical computing explained" in allmd)
        check("p1a: youtube comment → voice",
              "Wonderful restoration" in allmd)
        # photo spots aggregated (2 nearby sidecars → 1 pin; zero-geo skipped)
        spots = list((out / "85-places").glob("Photo spot*.md"))
        check("p1a: photo sidecars → ONE aggregated spot", len(spots) == 1,
              str([s.name for s in spots]))
        check("p1a: photo spot counts both shots",
              "2 photo(s)" in (spots[0].read_text() if spots else ""), )
        # excluded-by-design slices: honest skipped class + no leak
        cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
        check("p1a: Records.json skipped honestly",
              "`records` — skipped (low-signal, by design" in cov, cov[-800:])
        check("p1a: mail/fit skipped honestly",
              cov.count("skipped (low-signal, by design") >= 3, cov[-800:])
        check("p1a: takeout mail never leaks", "secret-body-do-not-leak" not in allmd)


def test_new_sources():
    """The 17-source build-out: full-entity builds of the ned (personal) and
    globex (company) fixture entities must consume EVERY file (the per-file
    coverage assertion the old Slack bug evaded), keep the privacy invariants
    (needles planted in chat/email/ticket bodies never surface), and land each
    source's signal in the right layer."""
    ned = FIXTURES / "personal" / "ned"
    glx = FIXTURES / "company" / "globex"

    if ned.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(ned), "-o", str(out)],
                               capture_output=True, text=True)
            check("new: ned entity builds (9 personal sources)", r.returncode == 0,
                  r.stderr[-300:])
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("new: ned coverage — 0 uncategorized", "(0 uncategorized" in cov,
                  cov[:200])
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("new: chat/DM/ticket bodies never leak (personal)",
                  "secret-body-do-not-leak" not in allmd, "needle leaked")
            # x → tweets in voice; retweets excluded
            posts = (out / "30-voice" / "posts.md")
            ptxt = posts.read_text() if posts.exists() else \
                "\n".join(p.read_text() for p in (out / "30-voice").rglob("*.md")) \
                if (out / "30-voice").is_dir() else ""
            check("new: x tweets land in voice", "okily dokily!" in ptxt.lower()
                  or "leftorium" in ptxt.lower(), ptxt[:200])
            check("new: x retweets excluded", "not my words" not in ptxt)
            # whatsapp → signal only, partner person exists
            maude = out / "10-people" / "Maude Flanders.md"
            check("new: whatsapp partner person", maude.exists())
            mtxt = maude.read_text() if maude.exists() else ""
            check("new: whatsapp signal recorded", "last_contact: 2024-03-13" in mtxt,
                  mtxt[:300])
            # github → repo voice + follower person
            check("new: github repo in voice", "left-handed-tools" in allmd)
            check("new: github follower person",
                  (out / "10-people" / "Homer S.md").exists())
            # strava → activity place with coordinates + event
            act = out / "85-places" / "Morning Run.md"
            check("new: strava GPX start → place", act.exists())
            atxt = act.read_text() if act.exists() else ""
            check("new: strava place has lat/lng", "lat: 44.4323" in atxt, atxt[:300])
            # spotify → interests + mirror
            check("new: spotify artist interest", "Organ Masters" in allmd)
            mirror = "\n".join(p.read_text() for p in (out / "50-mirror").rglob("*.md")) \
                if (out / "50-mirror").is_dir() else ""
            check("new: spotify inferences → 50-mirror",
                  "1P_Custom_Christian_Music_Listener" in mirror, mirror[:200])
            # youtube → search log + channel interest
            check("new: youtube search in 80-search",
                  "left handed hammer" in allmd)
            # reddit → voice + subreddit interest (post text = the body column)
            check("new: reddit post in voice", "bench for lefties" in allmd.lower())
            # tiktok → following person
            check("new: tiktok following person",
                  (out / "10-people" / "woodworkdaily.md").exists())
            # amazon → order becomes a purchase note in 35-shopping (the new layer)
            shop = out / "35-shopping" / "Left-Handed Notebook.md"
            check("new: amazon order → 35-shopping purchase", shop.exists(),
                  "no shopping note")
            stxt = shop.read_text() if shop.exists() else ""
            check("new: amazon purchase note typed + merchant-linked",
                  "type: purchase" in stxt and "[[Amazon]]" in stxt, stxt[:300])
            # amazon → review lands in voice; search in 80-search; audience in mirror
            check("new: amazon review in voice",
                  "sturdy and well made for lefties" in allmd.lower())
            check("new: amazon search in 80-search", "left handed stapler" in allmd)
            check("new: amazon audience → 50-mirror", "Left-Handed Living" in allmd)
            check("new: amazon prime-video title → interest", "The Sinister Left" in allmd)
            # amazon → payment instruments quarantined (card + needle never imported)
            check("new: amazon payment quarantined",
                  "paymentoptionspaymentinstruments` — quarantined" in cov, cov[:400])
            check("new: amazon card number never leaks", "4416" not in allmd)
            # amazon → cart item surfaces as an interest (consideration signal)
            check("new: amazon cart item → interest",
                  "Left-Handed Coffee Mug" in allmd)
            # amazon → Digital.Content.Ownership.5.json quarantined by PREFIX (not uncategorized)
            check("new: amazon content-ownership prefix-quarantined",
                  "digitalcontentownership5` — quarantined" in cov, cov[:600])

    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(glx), "-o", str(out), "--subject", "company"],
                               capture_output=True, text=True)
            check("new: globex entity builds (9 company sources)", r.returncode == 0,
                  r.stderr[-300:])
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("new: globex coverage — 0 uncategorized", "(0 uncategorized" in cov,
                  cov[:200])
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("new: email/teams/ticket bodies never leak (company)",
                  "secret-body-do-not-leak" not in allmd, "needle leaked")
            check("new: fixture emails never leak", "fixture@example.com" not in allmd,
                  "email leaked")
            # email mbox → people from headers + signal
            hank = out / "10-people" / "Hank Scorpio.md"
            check("new: email header people", hank.exists())
            # salesforce → account org geocoded + contact joined to account
            acct = out / "15-organizations" / "Acme Robotics.md"
            atxt = acct.read_text() if acct.exists() else ""
            check("new: salesforce account org geocoded", "lat: 37.7" in atxt, atxt[:300])
            grace = out / "10-people" / "Grace Hopper.md"
            gtxt = grace.read_text() if grace.exists() else ""
            check("new: salesforce contact joined to account",
                  'company: "[[Acme Robotics]]"' in gtxt, gtxt[:300])
            # jira → project org + assignee tagged
            check("new: jira project org",
                  (out / "15-organizations" / "Reactor Core.md").exists())
            check("new: jira ownership tag", "project/reactor-core" in allmd)
            # notion/confluence → pages in voice
            check("new: notion page in voice", "Engineering Handbook" in allmd)
            check("new: confluence page in voice", "Incident Response Runbook" in allmd)
            # zendesk → requester signal (ticket subject must NOT appear)
            check("new: zendesk ticket subject never imported",
                  "gripper jams" not in allmd)
            # teams → channel org + sender signal
            check("new: teams channel org",
                  (out / "15-organizations" / "reactor.md").exists()
                  or (out / "15-organizations" / "#reactor.md").exists())
            # hubspot → company org
            check("new: hubspot company org",
                  (out / "15-organizations" / "Hooli.md").exists())


def test_deepening_v2():
    """P1b/P1c: the second deepening wave — new files each source now extracts."""
    ned = FIXTURES / "personal" / "ned"
    if ned.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(ned), "-o", str(out)],
                               capture_output=True, text=True)
            check("v2: ned builds", r.returncode == 0, r.stderr[-300:])
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("v2: x note-tweet in voice",
                  "left-handed tool ergonomics" in allmd)
            check("v2: x list → interest", "list: Woodworkers" in allmd)
            check("v2: spotify followed artist", "Hymn Society" in allmd)
            check("v2: spotify playlist name + track artist",
                  "Workshop Tunes" in allmd)
            check("v2: tiktok comment in voice", "Great jig design" in allmd)
            reactions = out / "30-voice" / "reactions.md"
            rtxt = reactions.read_text() if reactions.exists() else ""
            check("v2: tiktok likes/favorites counted",
                  "favorite video" in rtxt, rtxt[:300])
            check("v2: reddit friend person",
                  (out / "10-people" / "maude_f.md").exists())
            check("v2: reddit multireddit interest", "handtools" in allmd)
            carl = out / "10-people" / "carpenter_carl.md"
            check("v2: reddit PM sender → signal person", carl.exists())
            check("v2: reddit PM subject/body never leak",
                  "secret-body-do-not-leak" not in allmd, "needle leaked")
            check("v2: youtube per-playlist video title",
                  "Japanese joinery basics" in allmd)
            check("v2: github org membership",
                  (out / "15-organizations" / "Leftorium Inc.md").exists())
            check("v2: github issue counts on repo note",
                  "2 issues" in allmd, "")
            check("v2: strava follower person (id-only row skipped)",
                  (out / "10-people" / "Homer Runner.md").exists())
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("v2: ned coverage still 0 uncategorized",
                  "(0 uncategorized" in cov, cov[:200])

    glx = FIXTURES / "company" / "globex"
    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                                str(glx), "-o", str(out), "--subject", "company"],
                               capture_output=True, text=True)
            check("v2: globex builds", r.returncode == 0, r.stderr[-300:])
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("v2: needles never leak (jira comments, case/ticket subjects)",
                  "secret-body-do-not-leak" not in allmd, "needle leaked")
            check("v2: jira component → interest", "component: Telemetry" in allmd)
            lenny = out / "10-people" / "Lenny Leonard.md"
            check("v2: jira comment author → person+signal", lenny.exists())
            check("v2: salesforce campaign event", "Campaign: Cobot Launch Webinar" in allmd)
            check("v2: hubspot ticket owner person",
                  (out / "10-people" / "Jared Dunn.md").exists())
            check("v2: confluence page author",
                  (out / "10-people" / "Frank Grimes.md").exists()
                  and "wiki author" in allmd)
            check("v2: confluence body excerpt",
                  "on-call engineer" in allmd)
            check("v2: notion breadcrumb", "Projects / Reactor Roadmap" in allmd)
            check("v2: notion intra-wiki link converted (no dangling wikilinks)",
                  "→ Engineering Handbook" in allmd and
                  "%20" not in allmd.split("Reactor Roadmap", 1)[-1][:400])
            cov = (out / "_COVERAGE.md").read_text() if (out / "_COVERAGE.md").exists() else ""
            check("v2: globex coverage still 0 uncategorized",
                  "(0 uncategorized" in cov, cov[:200])

    # GBrain enrichment: deals/meetings/strength emitted from the globex entity
    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(glx), "-o", str(out), "--subject", "company",
                            "--emit", "gbrain"], capture_output=True, text=True)
            deals = list((out / "deals").glob("*.md")) if (out / "deals").is_dir() else []
            check("gbrain2: deal pages emitted", len(deals) >= 1,
                  str(sorted(x.name for x in out.rglob("*.md"))[:20]))
            dtxt = "\n".join(p.read_text() for p in deals)
            check("gbrain2: deal_with edge to account",
                  "deal_with [[companies/acme-robotics]]" in dtxt, dtxt[:400])
            hank = out / "people" / "hank-scorpio.md"
            htxt = hank.read_text() if hank.exists() else ""
            check("gbrain2: people carry strength/last_contact",
                  "strength:" in htxt and "last_contact:" in htxt, htxt[:400])
            gtext = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("gbrain2: PII sweep still clean",
                  "secret-body-do-not-leak" not in gtext
                  and "fixture@example.com" not in gtext, "leak")
            man = out / "gbrain.manifest.json"
            check("gbrain2: manifest counts deals",
                  man.exists() and '"deals"' in man.read_text(), "")
    # meetings from acme calendar (attendees) via gbrain emit
    acme_gw = FIXTURES / "company" / "acme" / "google_workspace"
    if acme_gw.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(acme_gw), "-o", str(out), "--emit", "gbrain"],
                           capture_output=True, text=True)
            meets = list((out / "meetings").glob("*.md")) if (out / "meetings").is_dir() else []
            mtxt = "\n".join(p.read_text() for p in meets)
            check("gbrain2: meeting pages with attended edges",
                  len(meets) >= 1 and "attended [[people/grace-hopper]]" in mtxt,
                  mtxt[:400])

    fb = FIXTURES / "personal" / "fbtest"
    if fb.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(fb), "-o", str(out)], capture_output=True, text=True)
            ev = out / "60-learning" / "events.md"
            etxt = ev.read_text() if ev.exists() else ""
            check("v2: fb RSVP going", "Maker Faire Springfield" in etxt
                  and "going" in etxt, etxt[:400])
            check("v2: fb RSVP interested", "Woodturning Expo" in etxt
                  and "interested" in etxt, etxt[:400])
            allmd = "\n".join(p.read_text() for p in out.rglob("*.md"))
            check("v2: fb note → voice", "joy of hand tools" in allmd)


def test_model_v2():
    """M1 canonical-model upgrades: org business fields, person connected_on/dept,
    per-field provenance ('Also reported'), interests/search provenance +
    frontmatter on aggregate notes, canonical events, signal idempotence."""
    glx = FIXTURES / "company" / "globex"
    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(glx), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            acme = (out / "15-organizations" / "Acme Robotics.md")
            atxt = acme.read_text() if acme.exists() else ""
            check("model2: org industry from salesforce", "industry: Robotics" in atxt
                  or "industry:" in atxt and "Robotics" in atxt, atxt[:400])
            check("model2: org domain normalized",
                  "domain: acme-robotics.example" in atxt, atxt[:400])
            bill = out / "10-people" / "Bill Lumbergh.md"
            btxt = bill.read_text() if bill.exists() else ""
            check("model2: conflicting company preserved (alt_company)",
                  "alt_company" in btxt and "Initech GmbH" in btxt, btxt[:500])
            check("model2: Also reported section rendered",
                  "## Also reported" in btxt, btxt[:500])
            # slack channel topic now default-mode visible (org about)
    acme_e = FIXTURES / "company" / "acme"
    if acme_e.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(acme_e), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            gen = out / "15-organizations" / "general.md"
            gtxt = gen.read_text() if gen.exists() else ""
            check("model2: slack topic/purpose default-visible",
                  "Company-wide announcements" in gtxt, gtxt[:400])
            grace = (out / "10-people" / "Grace Hopper.md")
            gtxt = grace.read_text() if grace.exists() else ""
            check("model2: dept first-class wikilink",
                  'dept: "[[Engineering]]"' in gtxt, gtxt[:400])
    ada = FIXTURES / "personal" / "ada" / "linkedin"
    if ada.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(ada), "-o", str(out)], capture_output=True, text=True)
            ppl = list((out / "10-people").glob("*.md"))
            ptxt = "\n".join(x.read_text() for x in ppl)
            check("model2: connected_on unoverloaded",
                  "connected_on:" in ptxt, ptxt[:400])
            il = out / "30-voice" / "interests.md"
            itxt = il.read_text() if il.exists() else ""
            if itxt:
                check("model2: interests note has frontmatter + source grouping",
                      itxt.startswith("---") and "## linkedin" in itxt, itxt[:300])
            sl = out / "80-search" / "search-log.md"
            stxt = sl.read_text() if sl.exists() else ""
            if stxt:
                check("model2: search log has frontmatter + provenance",
                      stxt.startswith("---") and "linkedin" in stxt, stxt[:300])
    # signal idempotence: same slack export read twice (two dirs) → same strength
    sl = FIXTURES / "company" / "acme" / "slack"
    if sl.is_dir():
        with tempfile.TemporaryDirectory() as d:
            dup = Path(d) / "data" / "slack"
            import shutil as _sh
            _sh.copytree(sl, dup / "one")
            _sh.copytree(sl, dup / "two")   # duplicate day-files, different paths
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(dup), "-o", str(out)], capture_output=True, text=True)
            grace = out / "10-people" / "Grace Hopper.md"
            gtxt = grace.read_text() if grace.exists() else ""
            check("model2: duplicated archive does NOT inflate strength",
                  "strength: 2" in gtxt, gtxt[:400])


def test_layout_v2():
    """M2 subject-aware layout: company brains get company-named folders (from
    layout.json variants), deals become first-class pipeline notes, people carry
    relationship classes, personal layout is unchanged, and no hardcoded layer
    folder strings survive in the builder."""
    glx = FIXTURES / "company" / "globex"
    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(glx), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            check("layout2: company voice → 30-content",
                  (out / "30-content").is_dir() and not (out / "30-voice").exists(),
                  str(sorted(x.name for x in out.iterdir())))
            check("layout2: pipeline folder with deal notes",
                  (out / "40-pipeline").is_dir()
                  and any((out / "40-pipeline").glob("*.md")))
            deal = next(iter((out / "40-pipeline").glob("Deal*.md")), None)
            dtxt = deal.read_text() if deal else ""
            check("layout2: deal note typed deal", "type: deal" in dtxt, dtxt[:300])
            check("layout2: market-view + support + signals folders named",
                  not (out / "50-mirror").exists()
                  and not (out / "40-career").exists())
            grace = out / "10-people" / "Grace Hopper.md"
            gtxt = grace.read_text() if grace.exists() else ""
            check("layout2: company person relationship class",
                  "relationship: customer" in gtxt, gtxt[:400])
            check("layout2: _notes user space scaffolded",
                  (out / "_notes" / "README.md").exists())
            st = (out / "_STRUCTURE.md").read_text() if (out / "_STRUCTURE.md").exists() else ""
            check("layout2: _STRUCTURE reflects company variant",
                  "40-pipeline/" in st and "40-career/" not in st, st[:400])
    ned = FIXTURES / "personal" / "ned"
    if ned.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(ned), "-o", str(out)], capture_output=True, text=True)
            check("layout2: personal layout unchanged",
                  (out / "30-voice").is_dir() and (out / "85-places").is_dir()
                  and not (out / "30-content").exists())
            check("layout2: personal keeps warm/dormant status",
                  any("status:" in x.read_text()
                      for x in (out / "10-people").glob("*.md")))
    # grep guard: no hardcoded layer folder literals left in the builder
    src = (SCRIPTS / "build_vault.py").read_text()
    body = src.split("def layout_for", 1)[-1]  # everything after the defaults block
    import re as _re
    hard = [m for m in _re.findall(r'"([0-9]{2}-[a-z][a-z-]+)"', body)
            if m not in ("99-uncategorized",)]  # coverage default is variant-invariant
    check("layout2: no hardcoded layer folders in builder", not hard, str(hard))


def test_refresh_v2():
    """M3 incremental updates: --refresh preserves user notes and edits, updates
    unedited engine notes, adds new data, removes stale unedited notes, and a
    same-data refresh is a no-op."""
    import shutil as _sh
    ned = FIXTURES / "personal" / "ned"
    if not ned.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        data = Path(d) / "data"
        _sh.copytree(ned, data)
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(data), "-o", str(out)], capture_output=True, text=True)
        check("refresh: initial build ok", r.returncode == 0, r.stderr[-200:])
        check("refresh: manifest written", (out / "_GENERATED.json").exists())

        # ---- idempotent: same data → no conflicts, nothing stale ----
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(data), "-o", str(out), "--refresh"],
                           capture_output=True, text=True)
        check("refresh: same-data refresh runs", r.returncode == 0,
              r.stdout[-300:] + r.stderr[-300:])
        rep = (out / "_UPDATE_REPORT.md").read_text() \
            if (out / "_UPDATE_REPORT.md").exists() else ""
        check("refresh: no-op reports zero conflicts + zero stale",
              "conflicts (kept yours, fresh copy beside as *.new.md): 0" in rep
              and "stale removed (unedited, regenerable): 0" in rep, rep[:400])

        # ---- user content + edits, new data, stale data ----
        (out / "_notes" / "mine.md").write_text("# my private note\n", encoding="utf-8")
        (out / "10-people" / "Totally Mine.md").write_text("# mine\n", encoding="utf-8")
        maude = out / "10-people" / "Maude Flanders.md"
        maude.write_text(maude.read_text() + "\nMY EDIT: remember the casserole.\n",
                         encoding="utf-8")
        # new data: another whatsapp chat (new person + fresh Maude activity)
        (data / "whatsapp" / "WhatsApp Chat with Rod Flanders.txt").write_text(
            "20/04/24, 09:00 - Rod Flanders: secret-body-do-not-leak hi\n"
            "21/04/24, 10:00 - Maude Flanders: secret-body-do-not-leak news\n",
            encoding="utf-8")
        # stale data: remove the github followers shard (Homer S disappears)
        (data / "github" / "followers_000001.json").unlink()

        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(data), "-o", str(out), "--refresh"],
                           capture_output=True, text=True)
        check("refresh: update run ok", r.returncode == 0, r.stderr[-300:])
        check("refresh: user note in _notes survives",
              (out / "_notes" / "mine.md").exists())
        check("refresh: user-created note in a layer survives",
              (out / "10-people" / "Totally Mine.md").exists())
        mtxt = maude.read_text()
        check("refresh: user-edited engine note kept (edit intact)",
              "MY EDIT: remember the casserole." in mtxt, mtxt[-200:])
        check("refresh: fresh version beside as .new.md",
              (out / "10-people" / "Maude Flanders.new.md").exists())
        check("refresh: new person from new archive",
              (out / "10-people" / "Rod Flanders.md").exists())
        check("refresh: stale unedited note deleted",
              not (out / "10-people" / "Homer S.md").exists())
        rep = (out / "_UPDATE_REPORT.md").read_text()
        check("refresh: report lists the conflict",
              "Maude Flanders" in rep, rep[:500])
        allmd = "\n".join(x.read_text() for x in out.rglob("*.md"))
        check("refresh: needles still never leak", "secret-body-do-not-leak" not in allmd)

    # multi-entity refresh smoke (two personal entities)
    with tempfile.TemporaryDirectory() as d:
        data = Path(d) / "data" / "personal"
        _sh.copytree(FIXTURES / "personal" / "ada", data / "ada")
        _sh.copytree(FIXTURES / "personal" / "grace", data / "grace")
        out = Path(d) / "v"
        subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                        str(data.parent), "-o", str(out)], capture_output=True, text=True)
        keep = out / "personal" / "ada-brain" / "_notes" / "keepme.md"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("# keep\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(data.parent), "-o", str(out), "--refresh"],
                           capture_output=True, text=True)
        check("refresh: multi-entity refresh runs", r.returncode == 0,
              r.stdout[-300:] + r.stderr[-300:])
        check("refresh: multi-entity user note survives", keep.exists())
        check("refresh: correlations regenerated",
              (out / "_correlations" / "Home.md").exists())


def test_verification_matrix():
    """P4: every script works across the full source set — all 7 goals analyze on
    both flagship entities, --doctor passes, the profiler leaves zero unknown
    files, and the packaged skill ships the sources guide."""
    ALL_GOALS = "fundraising,bd,jobsearch,datamining,personalization,onboarding,whoknows"
    for ent, subj in (("personal/ned", None), ("company/globex", "company")):
        src = FIXTURES / Path(ent)
        if not src.is_dir():
            continue
        tag = src.name
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            cmd = [sys.executable, str(SCRIPTS / "build_vault.py"), str(src),
                   "-o", str(out)]
            if subj:
                cmd += ["--subject", subj]
            subprocess.run(cmd, capture_output=True, text=True)
            r = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"),
                                str(out), "--goals", ALL_GOALS],
                               capture_output=True, text=True)
            check(f"matrix: all 7 goals analyze on {tag}", r.returncode == 0,
                  r.stderr[-300:])
            # goal builders name their own files (bd → sales-bd.md, …)
            GOAL_FILES = ("fundraising.md", "sales-bd.md", "job-search.md",
                          "data-mining.md", "personalization.md",
                          "onboarding.md", "whoknows.md")
            for gf in GOAL_FILES:
                check(f"matrix: {tag} 95-goals/{gf}",
                      (out / "95-goals" / gf).exists())
            check(f"matrix: {tag} Dashboard + _DATA_POINTS",
                  (out / "Dashboard.md").exists()
                  and (out / "_DATA_POINTS.md").exists())
        # doctor preflight
        r = subprocess.run([sys.executable, str(SCRIPTS / "selfheal.py"),
                            "--doctor", str(src)], capture_output=True, text=True)
        check(f"matrix: doctor runs on {tag}", r.returncode == 0,
              (r.stdout + r.stderr)[-200:])
        # profiler: zero unknown files (full detection across the 17 new sources)
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "p"
            subprocess.run([sys.executable, str(SCRIPTS / "profile_export.py"),
                            str(src), "--out", str(prof)],
                           capture_output=True, text=True)
            sm = prof / "schema_map.md"
            smtxt = sm.read_text() if sm.exists() else ""
            check(f"matrix: profiler zero unknown files on {tag}",
                  "unknown 0," in smtxt or "unknown 0)" in smtxt, smtxt[:300])
    # the packaged skill ships the export/import guide
    skill_zip = REPO / "dist" / "claude" / "second-brain-link.skill"
    if skill_zip.exists():
        import zipfile
        names = zipfile.ZipFile(skill_zip).namelist()
        check("matrix: packaged skill ships references/SOURCES.md",
              any(n.endswith("references/SOURCES.md") for n in names))


def test_geocoder():
    """Offline geocoder: bundled gazetteer resolves unambiguous cities (with or
    without country/region qualifiers), refuses ambiguous ones, and the build
    stamps lat/lng frontmatter on identity/org notes that carry a location."""
    import geocode
    hit = geocode.resolve("London, England, United Kingdom")
    check("geo: London resolves", hit is not None and abs(hit[0] - 51.5) < 0.2,
          str(hit))
    check("geo: bare metro alias resolves", geocode.resolve("San Francisco Bay Area") is not None)
    check("geo: qualified small city resolves",
          (geocode.resolve("Paris, Texas") or (0, 0))[0] > 30
          and (geocode.resolve("Paris, Texas") or (0, 0))[1] < -90)
    check("geo: ambiguous city refused (precision-biased)",
          geocode.resolve("Springfield") is None)
    check("geo: unknown place refused", geocode.resolve("Nowhereville-XYZ") is None)
    check("geo: empty/None safe", geocode.resolve("") is None and geocode.resolve(None) is None)
    # integration: the acme org profile carries Location "San Francisco" → the
    # 00-org identity note gets lat/lng, and the org note carries them too
    if FX_ACME_LIC.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(FX_ACME_LIC), "-o", str(out)],
                           capture_output=True, text=True)
            org = out / "00-org" / "organization.md"
            otxt = org.read_text() if org.exists() else ""
            check("geo: org identity note stamped with lat/lng",
                  "lat: 37.7" in otxt and "lng: -122.4" in otxt, otxt[:400])
            comp = out / "15-organizations" / "Acme Robotics.md"
            ctxt = comp.read_text() if comp.exists() else ""
            check("geo: company org note stamped with lat/lng",
                  "lat: 37.7" in ctxt, ctxt[:400])


def test_sibling_split_and_providers():
    """A mixed (personal+company) export → two sibling vaults with the right roots
    and a clean split; --provider writes the right in-vault guide file; adapter
    auto-discovery finds all subfolders."""
    # auto-discovery
    sys.path.insert(0, str(SCRIPTS))
    import sources as _s
    names = {m.NAME for m in _s.ALL}
    check("auto-discovery finds personal+company adapters",
          {"linkedin", "facebook", "google", "instagram",
           "linkedin_company", "google_workspace", "slack"} <= names, str(sorted(names)))
    # provider guide file (single export)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                        str(FX_ADA), "-o", str(out),
                        "--provider", "openai"], capture_output=True, text=True)
        check("provider openai → AGENTS.md (not CLAUDE.md)",
              (out / "AGENTS.md").exists() and not (out / "CLAUDE.md").exists())


def test_multi_entity_and_correlation():
    """The whole tests/fixtures tree (personal/ada, personal/grace, company/acme)
    builds one brain per entity + a _correlations/ vault; verify roots, the
    cross-person note, the works_at edge, the negative-merge, and PII cleanliness."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(FIXTURES), "-o", str(out)],
                           capture_output=True, text=True)
        check("multi: build runs", r.returncode == 0, r.stderr[-300:])
        ada = out / "personal" / "ada-brain"
        grace = out / "personal" / "grace-brain"
        acme = out / "company" / "acme-brain"
        corr = out / "_correlations"
        check("multi: per-entity brains exist with right roots",
              (ada / "00-me").is_dir() and (grace / "00-me").is_dir()
              and (acme / "00-org").is_dir(), "missing a brain/root")
        check("multi: _correlations vault built", (corr / "Home.md").exists())
        # Ada appears in ada-self + grace's connections + acme → cross-person note
        check("multi: cross-person note for shared connection",
              (corr / "people" / "Ada Lovelace.md").exists())
        # grace works_at acme (from grace's Positions naming the company-entity)
        edges = (corr / "edges.md").read_text() if (corr / "edges.md").exists() else ""
        check("multi: works_at edge grace→acme", "grace" in edges and "acme" in edges
              and "works_at" in edges, edges[-200:])
        # negative: Margaret Hamilton is only in grace's brain → NOT a cross-person
        check("multi: no false cross-merge (Margaret only in one brain)",
              not (corr / "people" / "Margaret Hamilton.md").exists())
        # PII clean across the whole multi-vault (default mode)
        leaks = [p.name for p in out.rglob("*.md")
                 if "_quarantine" not in p.parts
                 and EMAIL.search(p.read_text(encoding="utf-8", errors="replace"))]
        check("multi: PII sweep clean across all brains", not leaks, str(leaks[:3]))


def test_graphdata_and_avatars():
    """graph.json (sbl-graph/1) sidecar + avatar extraction: emitted for personal
    AND company brains + _correlations, edges typed/weighted with endpoints that
    exist, company-variant folders respected, PII-clean, manifest-managed (exactly
    one after --refresh), the analyze.py --graph-data retrofit works, and the
    owner's vCard photo lands in _assets/avatars/ with `avatar:` frontmatter."""
    import json as _json
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(FIXTURES), "-o", str(out)],
                           capture_output=True, text=True)
        check("graphdata: multi build runs", r.returncode == 0, r.stderr[-300:])
        ada_g = out / "personal" / "ada-brain" / "graph.json"
        acme_g = out / "company" / "acme-brain" / "graph.json"
        corr_g = out / "_correlations" / "graph.json"
        check("graphdata: graph.json at every brain root",
              ada_g.exists() and acme_g.exists() and corr_g.exists())
        ga = _json.loads(ada_g.read_text(encoding="utf-8"))
        gc = _json.loads(acme_g.read_text(encoding="utf-8"))
        check("graphdata: schema sbl-graph/1",
              ga.get("schema") == "sbl-graph/1" and gc.get("schema") == "sbl-graph/1")
        ids = {n["id"] for n in ga["nodes"]}
        dangling = [e for e in ga["edges"] if e["a"] not in ids or e["b"] not in ids]
        check("graphdata: every edge endpoint is a node", not dangling,
              str(dangling[:2]))
        on_disk = [n for n in ga["nodes"]
                   if not (out / "personal" / "ada-brain" / n["path"]).exists()]
        check("graphdata: every node path exists on disk", not on_disk,
              str(on_disk[:2]))
        check("graphdata: ada has a typed works_at edge",
              any(e["type"] == "works_at" for e in ga["edges"]))
        check("graphdata: edge weights in (0,1]",
              all(0 < e["w"] <= 1 for e in ga["edges"] + gc["edges"]))
        # company brains use the company-named variant folders in layers[]
        folders = {l["folder"] for l in gc["layers"]}
        check("graphdata: company layer variant folders",
              not ({"20-reputation", "30-voice"} & folders),
              str(sorted(folders)))
        check("graphdata: correlations graph has a correlated edge",
              any(e["type"] == "correlated"
                  for e in _json.loads(corr_g.read_text())["edges"]))
        check("graphdata: PII sweep (no emails in graph.json)",
              not EMAIL.search(ada_g.read_text() + acme_g.read_text()))
        # avatar: owner's vCard photo → _assets/avatars/ + frontmatter + graph node
        owner = out / "personal" / "owner-brain"
        av = owner / "_assets" / "avatars" / "Ada Byron.jpg"
        check("avatar: vCard photo written to _assets/avatars/", av.exists())
        note = (owner / "10-people" / "Ada Byron.md")
        check("avatar: frontmatter carries avatar path",
              note.exists() and "avatar: _assets/avatars/Ada Byron.jpg"
              in note.read_text(encoding="utf-8"))
        man = _json.loads((owner / "_GENERATED.json").read_text(encoding="utf-8"))
        check("avatar: image manifest-tracked",
              "_assets/avatars/Ada Byron.jpg" in man["files"])
        go = _json.loads((owner / "graph.json").read_text(encoding="utf-8"))
        check("avatar: graph.json node carries avatar field",
              any(n.get("avatar") for n in go["nodes"]))
        # --refresh keeps exactly one graph.json + doesn't duplicate the avatar
        r2 = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                             str(FIXTURES), "-o", str(out), "--refresh"],
                            capture_output=True, text=True)
        check("graphdata: --refresh runs", r2.returncode == 0, r2.stderr[-300:])
        check("graphdata: one graph.json per brain after refresh",
              sum(1 for _ in (out / "personal" / "ada-brain").rglob("graph.json")) == 1
              and sum(1 for _ in owner.rglob("*.jpg")) == 1)
        # analyze.py --graph-data retrofit: delete + regenerate without rebuild
        ada_g.unlink()
        r3 = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"),
                             str(out / "personal" / "ada-brain"),
                             "--goals", "jobsearch", "--graph-data"],
                            capture_output=True, text=True)
        check("graphdata: --graph-data retrofit regenerates",
              r3.returncode == 0 and ada_g.exists(), r3.stderr[-300:])
        # smart-brain layer (health.py, run by analyze): health report + graph
        # insights + overview canvas — deterministic, suspicions-only, PII-clean
        ada = out / "personal" / "ada-brain"
        hj = ada / "_HEALTH.json"
        check("health: _HEALTH.md + .json written",
              (ada / "_HEALTH.md").exists() and hj.exists())
        if hj.exists():
            h = _json.loads(hj.read_text(encoding="utf-8"))
            check("health: schema + honest link stats",
                  h.get("schema") == "sbl-health/1"
                  and h["links"]["unresolved"] <= h["links"]["total"])
            check("health: PII sweep (no emails)",
                  not EMAIL.search(hj.read_text(encoding="utf-8")))
        check("health: graph-insights synthesis note",
              (ada / "90-synthesis" / "graph-insights.md").exists())
        cv = ada / "_canvas" / "brain-overview.canvas"
        check("health: overview canvas is valid JSON Canvas",
              cv.exists() and "nodes" in _json.loads(cv.read_text(encoding="utf-8")))


def test_mapping_engine():
    """The JSON mapping interpreter: selector mini-language, mapping-wins-over-.py,
    and IG/Google mappings extract from the synthetic fixtures."""
    import mapping
    rf = mapping.resolve_field
    # IG wrappers + GeoJSON + first-of + const + numeric index
    ig = {"string_list_data": [{"value": "ada", "href": "https://i/ada", "timestamp": 9}]}
    check("selector: string_list_data[].value", rf(ig, "string_list_data[].value") == ["ada"])
    check("selector: string_map_data.*.value",
          rf({"string_map_data": {"Name": {"value": "travel"}}}, "string_map_data.*.value") == ["travel"])
    feat = {"geometry": {"coordinates": [2.3, 48.8]}, "properties": {"location": {"name": "Cafe"}}}
    check("selector: geojson coords[0]/[1]",
          rf(feat, "geometry.coordinates[0]") == [2.3] and rf(feat, "geometry.coordinates[1]") == [48.8])
    check("selector: first-of", rf({"caption": "hi"}, ["title", "caption"]) == ["hi"])
    check("selector: const", rf({}, {"const": "x"}) == ["x"])
    # label predicate — Facebook/Instagram {label,value} shape: pick value by sibling label
    lv = {"label_values": [{"label": "Message", "value": "hello"},
                           {"label": "Detected dialect", "value": "Romanian"}]}
    check("selector: label predicate", rf(lv, "label_values[label=Message].value") == ["hello"])
    vec = {"label_values": [{"label": "Friend suggestions", "vec": [{"value": "Ann"}, {"value": "Bob"}]}]}
    check("selector: label predicate + vec",
          rf(vec, "label_values[label=Friend suggestions].vec[].value") == ["Ann", "Bob"])
    # mapping-wins: instagram + facebook are JsonMapping, linkedin/google are modules
    # (google is a Python adapter — Takeout mixes vCard/ICS/HTML the mapping can't parse)
    import sources
    sources.register_mappings()
    check("mapping wins over .py (instagram/facebook)",
          all(type(sources.BY_NAME[n]).__name__ == "JsonMapping"
              for n in ("instagram", "facebook")), str({n: type(sources.BY_NAME[n]).__name__ for n in ("instagram","facebook","linkedin","google")}))
    check("python adapter kept (linkedin, google)",
          type(sources.BY_NAME["linkedin"]).__name__ == "module"
          and type(sources.BY_NAME["google"]).__name__ == "module")


def test_places_and_mappings_build():
    """Build the owner fixture (IG + Google Maps via mappings) and assert the mapping
    engine populates people/posts/interests + an 85-places layer from GeoJSON, with
    the review note captured and PII clean in default mode."""
    owner = FIXTURES / "personal" / "owner"
    if not owner.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(owner),
                            "-o", str(out)], capture_output=True, text=True)
        check("mappings: owner build runs", r.returncode == 0, r.stderr[-300:])
        # multi-entity discovery makes vault/personal/owner-brain
        brain = out / "personal" / "owner-brain"
        brain = brain if brain.is_dir() else out
        places = brain / "85-places"
        check("mappings: 85-places layer built from Google Maps GeoJSON",
              places.is_dir() and any(places.glob("*.md")))
        ptext = "\n".join(p.read_text() for p in places.glob("*.md")) if places.is_dir() else ""
        check("mappings: saved place rendered (Eiffel Tower)", "Eiffel Tower" in ptext)
        check("mappings: review note captured", "Best coffee in the Marais" in ptext)
        # IG followers → people, posts → voice
        ppl = "\n".join(p.read_text() for p in (brain / "10-people").glob("*.md")) if (brain / "10-people").is_dir() else ""
        check("mappings: IG follower → person", "ada_dev" in ppl or "Ada Dev" in ppl)
        # synced contacts → people; last-known-location → 85-places
        check("mappings: IG synced contact → person", "Synced Contact One" in ppl)
        check("mappings: IG last-known-location → place",
              "last known location" in ptext.lower())
        # precise rules + quarantine reflected in coverage
        cov = (brain / "_COVERAGE.md").read_text() if (brain / "_COVERAGE.md").exists() else ""
        check("mappings: synced_contacts mapped", "syncedcontacts` — mapped" in cov, cov[:0])
        check("mappings: threads_viewed mapped", "threadsviewed` — mapped" in cov, cov[:0])
        check("mappings: login_activity quarantined (not 'needs a mapping')",
              "loginactivity` — quarantined" in cov, cov[:0])
        # _SUMMARY.md seed-counts snapshot
        summ = (brain / "_SUMMARY.md").read_text() if (brain / "_SUMMARY.md").exists() else ""
        check("summary: _SUMMARY.md written with per-layer counts",
              bool(summ) and "Notes per layer" in summ and "people:" in summ, summ[:0])
        # default-mode PII clean across the brain
        leak = [p.name for p in brain.rglob("*.md")
                if "_quarantine" not in p.parts and EMAIL.search(p.read_text(encoding="utf-8", errors="replace"))]
        check("mappings: default-mode PII clean", not leak, str(leak[:3]))


def test_google_takeout_subsources():
    """The Google Python adapter ingests the multi-FORMAT sub-products the old JSON
    mapping couldn't: vCard contacts, .ics calendar, labeled-places GeoJSON, Saved
    place-list CSV, YouTube subscriptions + search-history HTML — across a Takeout
    tree — landing in the right layers with PII clean in default mode."""
    with tempfile.TemporaryDirectory() as d:
        g = Path(d) / "personal" / "adi" / "google" / "Takeout"
        (g / "Contacts").mkdir(parents=True)
        (g / "Calendar").mkdir()
        (g / "Maps" / "My labeled places").mkdir(parents=True)
        (g / "Saved").mkdir()
        yt = g / "YouTube and YouTube Music"
        (yt / "subscriptions").mkdir(parents=True)
        (yt / "history").mkdir()
        # vCard: one real contact (with an email that must NOT leak) + one email-only (dropped)
        (g / "Contacts" / "All Contacts.vcf").write_text(
            "BEGIN:VCARD\nVERSION:3.0\nFN:Grace Hopper\nORG:US Navy\nTITLE:Rear Admiral\n"
            "EMAIL;TYPE=INTERNET:grace@example.com\nEND:VCARD\n"
            "BEGIN:VCARD\nVERSION:3.0\nitem1.EMAIL;TYPE=INTERNET:spam@example.com\nEND:VCARD\n")
        (g / "Calendar" / "cal.ics").write_text(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team Offsite\nDTSTART:20240615T090000Z\n"
            "END:VEVENT\nEND:VCALENDAR\n")
        (g / "Maps" / "My labeled places" / "Labeled places.json").write_text(json.dumps({
            "features": [{"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [27.58, 47.14]},
                          "properties": {"name": "Home", "address": "Carpati 7, Iasi"}}]}))
        (g / "Saved" / "Want to go.csv").write_text(
            "Title,Note,URL,Tags,Comment\nTokyo Tower,,https://maps.google.com/?cid=9,,must visit\n")
        (yt / "subscriptions" / "subscriptions.csv").write_text(
            "Channel Id,Channel Url,Channel Title\nUC1,http://x,Veritasium\n")
        (yt / "history" / "search-history.html").write_text(
            'Searched for <a href="https://www.youtube.com/results?search_query=neural+nets">'
            'neural nets</a>')
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(Path(d)), "-o", str(out)], capture_output=True, text=True)
        check("google: build runs", r.returncode == 0, r.stderr[-300:])
        brain = out / "personal" / "adi-brain"
        brain = brain if brain.is_dir() else out
        allmd = "\n".join(p.read_text() for p in brain.rglob("*.md"))
        check("google: vCard contact → person", "Grace Hopper" in allmd)
        check("google: email-only vCard dropped", "spam@example.com" not in allmd)
        check("google: .ics event captured", "Team Offsite" in allmd)
        check("google: labeled place → 85-places",
              (brain / "85-places").is_dir() and "Home" in allmd)
        check("google: Saved-list place captured", "Tokyo Tower" in allmd)
        check("google: YouTube subscription → interest", "Veritasium" in allmd)
        check("google: search-history → search log", "neural nets" in allmd)
        leak = [p.name for p in brain.rglob("*.md")
                if "_quarantine" not in p.parts
                and EMAIL.search(p.read_text(encoding="utf-8", errors="replace"))]
        check("google: default-mode PII clean (vCard email not leaked)", not leak, str(leak[:3]))


def test_harvester_rescues_unmapped():
    """An unknown-shape file with NO mapping still yields records via the universal
    harvester, and is flagged 'needs a mapping' in coverage."""
    import harvester
    from sources.common import Collector
    with tempfile.TemporaryDirectory() as d:
        # a novel shape: list of dicts with name+url (no adapter/mapping claims it)
        f = Path(d) / "mystery_people.json"
        f.write_text(json.dumps([{"name": "Zara Q", "url": "https://x/zara", "title": "CTO"}]), encoding="utf-8")
        c = Collector()
        hits, shape = harvester.harvest(c, "harvested", f)
        check("harvester: rescues unknown people shape", hits >= 1 and len(c.people) >= 1, f"hits={hits}")
        # geojson place
        g = Path(d) / "spots.json"
        g.write_text(json.dumps({"features": [{"geometry": {"coordinates": [1.0, 2.0]},
                     "properties": {"location": {"name": "Spot A"}}}]}), encoding="utf-8")
        c2 = Collector()
        h2, _ = harvester.harvest(c2, "harvested", g)
        check("harvester: rescues geojson place", h2 >= 1 and len(c2.places) >= 1, f"hits={h2}")


def run_fixture(source_dir: Path, pii_needles):
    label = source_dir.name
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "vault"
        prof = Path(d) / "_profile"
        r1 = subprocess.run([sys.executable, str(SCRIPTS / "profile_export.py"),
                             str(source_dir), "--out", str(prof)],
                            capture_output=True, text=True)
        check(f"{label}: profiler runs", r1.returncode == 0, r1.stderr[-300:])
        for f in ("schema_map.md", f"{label}_mindmap.md", "brain_structure.json"):
            # mindmap stem is the detected source, which may differ from folder name;
            # accept any *_mindmap.md
            if f.endswith("_mindmap.md"):
                ok = any(prof.glob("*_mindmap.md"))
            else:
                ok = (prof / f).exists()
            check(f"{label}: profiler emits {f}", ok)
        struct = next(prof.glob("brain_structure.json"), None)
        cmd = [sys.executable, str(SCRIPTS / "build_vault.py"), str(source_dir),
               "-o", str(out)]
        if struct:
            cmd += ["--structure", str(struct)]
        r2 = subprocess.run(cmd, capture_output=True, text=True)
        check(f"{label}: build runs", r2.returncode == 0, r2.stderr[-300:])
        if out.exists():
            # a mixed (personal+company) export builds two sibling vaults instead
            # of a single top-level one — validate each sibling.
            siblings = [out / s for s in ("personal-brain", "company-brain")
                        if (out / s).exists()]
            roots = siblings or [out]
            for rt in roots:
                tag = f"{label}/{rt.name}" if siblings else label
                check(f"{tag}: Home.md exists", (rt / "Home.md").exists())
                vault_invariants(rt, tag, pii_needles)


def test_analyze_org_trim_identity():
    """Build the owner fixture with --min-org-refs, then run analyze.py: assert the
    goal notes + Dashboard + Copilot prompts are generated, the identity note uses
    the real Name (not the email IG lists first), and invariants still hold."""
    owner = FIXTURES / "personal" / "owner"
    if not owner.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(owner),
                            "-o", str(out), "--min-org-refs", "2"],
                           capture_output=True, text=True)
        check("analyze: --min-org-refs build runs", r.returncode == 0, r.stderr[-300:])
        brain = out / "personal" / "owner-brain"
        brain = brain if brain.is_dir() else out
        # identity fix: real Name wins, never the email
        idt = (brain / "00-me" / "identity.md").read_text() if (brain / "00-me" / "identity.md").exists() else ""
        check("identity: uses real Name not email/ig_profile_picture",
              "Owner Realname" in idt and "owner@example.com" not in idt and "ig_profile_picture" not in idt,
              idt[:160])
        # analyze.py goal layer
        a = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(brain),
                            "--goals", "fundraising,bd,jobsearch"], capture_output=True, text=True)
        check("analyze: runs", a.returncode == 0, a.stderr[-300:])
        g = brain / "95-goals"
        check("analyze: 95-goals notes written",
              all((g / f).exists() for f in ("fundraising.md", "sales-bd.md", "job-search.md")))
        dash = (brain / "Dashboard.md").read_text() if (brain / "Dashboard.md").exists() else ""
        check("analyze: Dashboard has a dataview block", "```dataview" in dash, dash[:80])
        check("analyze: Copilot prompts written",
              any((brain / "copilot-prompts").glob("*.md")))
        summ = (brain / "_SUMMARY.md").read_text() if (brain / "_SUMMARY.md").exists() else ""
        check("analyze: _SUMMARY.md updated with goal workspaces",
              "Goal workspaces (analyze.py)" in summ, summ[-200:])
        # invariants still hold (no dangling links despite org _mentions/ subfolder)
        vault_invariants(brain, "analyze", [])


def test_template_folder_autoname():
    """A user may drop a real export into the shipped rename-me template folder
    (data/personal/your-name/) without renaming it. The builder must NOT ship a
    'your-name-brain' — it names the brain after the detected identity instead.
    Build a data root with personal/your-name/<owner instagram fixture> and assert
    the brain folder is the identity slug ('owner-realname-brain'), not 'your-name'."""
    owner_ig = FIXTURES / "personal" / "owner" / "instagram"
    if not owner_ig.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "data"
        (root / "personal").mkdir(parents=True)
        shutil.copytree(owner_ig, root / "personal" / "your-name" / "instagram")
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(root),
                            "-o", str(out)], capture_output=True, text=True)
        check("template: build runs", r.returncode == 0, r.stderr[-300:])
        check("template: brain NOT named your-name-brain",
              not (out / "personal" / "your-name-brain").exists())
        check("template: brain named after detected identity (owner-realname-brain)",
              (out / "personal" / "owner-realname-brain").exists(),
              "\n".join(p.name for p in (out / "personal").iterdir()) if (out / "personal").is_dir() else "(none)")
        check("template: prints rename tip", "rename-me template" in (r.stdout + r.stderr))


def test_facebook_mapping():
    """Build the fbtest fixture (a Facebook export) and assert the comprehensive
    mapping: friends→people (tagged source/facebook + person/friend), ad-interests→
    50-mirror via the new mirror emit, check-in→place, event→event, liked page→
    interest, your_pages→org, profile→identity, and the security file is quarantined
    (not 'needs a mapping'). Also that the always-on _STRUCTURE.md vault map exists."""
    fb = FIXTURES / "personal" / "fbtest"
    if not fb.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(fb),
                            "-o", str(out)], capture_output=True, text=True)
        check("facebook: build runs", r.returncode == 0, r.stderr[-300:])
        brain = out / "personal" / "fbtest-brain"
        brain = brain if brain.is_dir() else out
        ppl = {p.stem: p.read_text(encoding="utf-8") for p in (brain / "10-people").glob("*.md")} \
            if (brain / "10-people").is_dir() else {}
        ptext = "\n".join(ppl.values())
        check("facebook: friend → person", "Bob Builder" in ptext, ptext[:120])
        check("facebook: follower → person", "Dora Watch" in ptext)
        bob = next((t for t in ppl.values() if "Bob Builder" in t), "")
        check("facebook: person tagged source/facebook", "source/facebook" in bob, bob[:200])
        check("facebook: person tagged person/friend (mapping tag)", "person/friend" in bob, bob[:200])
        mir = (brain / "50-mirror" / "inferences.md")
        mirt = mir.read_text(encoding="utf-8") if mir.exists() else ""
        check("facebook: ad-interest → 50-mirror (mirror emit)", "Artificial Intelligence" in mirt, mirt[:120])
        adp = (brain / "50-mirror" / "ad-profile.md")
        adpt = adp.read_text(encoding="utf-8") if adp.exists() else ""
        check("facebook: ad_preferences → ad-profile (ad_segment emit)", "SaaS" in adpt, adpt[:120])
        post_txt = "\n".join(p.read_text(encoding="utf-8") for p in (brain / "30-voice" / "posts").glob("*.md")) \
            if (brain / "30-voice" / "posts").is_dir() else ""
        check("facebook: posts_on_other_pages → post (label predicate)",
              "Congrats on the launch" in post_txt and "English" not in post_txt, post_txt[:160])
        plc = "\n".join(p.read_text(encoding="utf-8") for p in (brain / "85-places").glob("*.md")) \
            if (brain / "85-places").is_dir() else ""
        check("facebook: check-in → place", "Blue Bottle Coffee" in plc, plc[:120])
        ev = (brain / "60-learning" / "events.md")
        check("facebook: event invitation → event",
              ev.exists() and "Founders Dinner" in ev.read_text(encoding="utf-8"))
        ints = (brain / "30-voice" / "interests.md")
        check("facebook: liked page → interest",
              ints.exists() and "SpaceX" in ints.read_text(encoding="utf-8"))
        orgs = "\n".join(p.read_text(encoding="utf-8") for p in (brain / "15-organizations").rglob("*.md")) \
            if (brain / "15-organizations").is_dir() else ""
        check("facebook: your page → org", "My Startup Page" in orgs, orgs[:120])
        idt = (brain / "00-me" / "identity.md")
        check("facebook: profile → identity name",
              idt.exists() and "Fab Tester" in idt.read_text(encoding="utf-8"))
        cov = (brain / "_COVERAGE.md").read_text(encoding="utf-8") if (brain / "_COVERAGE.md").exists() else ""
        check("facebook: ip_address quarantined (not 'needs a mapping')",
              "ipaddressactivity` — quarantined" in cov, cov[:0])
        st = (brain / "_STRUCTURE.md")
        check("facebook: _STRUCTURE.md vault map written",
              st.exists() and "Vault structure" in st.read_text(encoding="utf-8"))
        vault_invariants(brain, "facebook", [])


def test_data_catalog():
    """Run analyze.py over the fbtest brain (all goals + --graph-config): assert the
    _DATA_POINTS.md catalog (entities + relations + field-enrichment-by-source +
    mermaid), the datamining + personalization goals, the /mine + /for-me Copilot
    prompts, _GRAPH.md, and a graph.json merge that PRESERVES the user's settings and
    writes a .bak."""
    fb = FIXTURES / "personal" / "fbtest"
    if not fb.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(fb), "-o", str(out)],
                       capture_output=True, text=True)
        brain = out / "personal" / "fbtest-brain"
        brain = brain if brain.is_dir() else out
        gj = out / ".obsidian" / "graph.json"
        gj.parent.mkdir(parents=True, exist_ok=True)
        gj.write_text(json.dumps({"scale": 1.7,
                      "colorGroups": [{"query": "tag:#keepme", "color": {"a": 1, "rgb": 42}}]}),
                      encoding="utf-8")
        a = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(brain),
                            "--goals", "fundraising,bd,jobsearch,datamining,personalization",
                            "--graph-config", str(gj)], capture_output=True, text=True)
        check("catalog: analyze runs", a.returncode == 0, a.stderr[-300:])
        dp = (brain / "_DATA_POINTS.md").read_text(encoding="utf-8") if (brain / "_DATA_POINTS.md").exists() else ""
        check("catalog: _DATA_POINTS.md written",
              "Data points (nodes)" in dp and "Relations (edges)" in dp, dp[:80])
        check("catalog: field-enrichment-by-source matrix",
              "Field enrichment by source" in dp and "facebook" in dp, dp[:0])
        check("catalog: mermaid schema", "```mermaid" in dp)
        g = brain / "95-goals"
        check("catalog: data-mining goal note", (g / "data-mining.md").exists())
        check("catalog: personalization goal note", (g / "personalization.md").exists())
        cp = brain / "copilot-prompts"
        check("catalog: /mine + /for-me prompts", (cp / "mine.md").exists() and (cp / "for-me.md").exists())
        gr = (brain / "_GRAPH.md")
        check("catalog: _GRAPH.md written",
              gr.exists() and "color legend" in gr.read_text(encoding="utf-8").lower())
        merged = json.loads(gj.read_text(encoding="utf-8"))
        queries = [grp.get("query") for grp in merged.get("colorGroups", [])]
        check("catalog: graph.json preserves user scale", merged.get("scale") == 1.7, str(merged.get("scale")))
        check("catalog: graph.json preserves user color group", "tag:#keepme" in queries, str(queries))
        check("catalog: graph.json adds source/facebook group", "tag:#source/facebook" in queries, str(queries))
        check("catalog: graph.json .bak written", gj.with_suffix(gj.suffix + ".bak").exists())


def test_final_sweep():
    """Final completeness sweep: analyze.py + the profiler diagrams are
    subject-aware — a COMPANY brain's _DATA_POINTS/goals/prompts count and name
    the company-variant folders (30-content, 85-locations, 40-pipeline, …),
    meetings are counted beside events, deals get their own catalog row, the
    profiler designs a company-named structure, and no hardcoded layer-folder
    path survives in analyze.py."""
    glx = FIXTURES / "company" / "globex"
    if glx.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(glx), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            r = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"),
                                str(out), "--goals", "datamining,personalization"],
                               capture_output=True, text=True)
            check("final: analyze runs on company brain", r.returncode == 0,
                  r.stderr[-300:])
            dp = (out / "_DATA_POINTS.md").read_text() \
                if (out / "_DATA_POINTS.md").exists() else ""
            check("final: company posts counted under 30-content",
                  re.search(r"\| Posts \| [1-9]\d* \| `30-content/posts/`", dp),
                  dp[:600])
            check("final: company catalog has a Deals & campaigns row",
                  re.search(r"\| Deals & campaigns \| [1-9]\d* \| `40-pipeline/`", dp),
                  dp[:600])
            check("final: company catalog names 85-locations (not 85-places)",
                  "85-locations" in dp and "85-places" not in dp)
            pers = (out / "95-goals" / "personalization.md").read_text() \
                if (out / "95-goals" / "personalization.md").exists() else ""
            check("final: personalization grounded in company folders",
                  "85-locations" in pers and "50-market-view" in pers, pers[:400])
            forme = (out / "copilot-prompts" / "for-me.md").read_text() \
                if (out / "copilot-prompts" / "for-me.md").exists() else ""
            check("final: copilot prompts rewritten to company folders",
                  "85-locations" in forme and "85-places" not in forme, forme[:400])
    acme = FIXTURES / "company" / "acme"
    if acme.is_dir():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"),
                            str(acme), "-o", str(out), "--subject", "company"],
                           capture_output=True, text=True)
            subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"),
                            str(out), "--goals", "onboarding,whoknows"],
                           capture_output=True, text=True)
            dp = (out / "_DATA_POINTS.md").read_text() \
                if (out / "_DATA_POINTS.md").exists() else ""
            check("final: company meetings counted in the events row",
                  re.search(r"\| Events & meetings \| [1-9]\d* \| `60-knowledge/`", dp),
                  dp[:600])
        # profiler designs a company-named structure for a company export
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "p"
            subprocess.run([sys.executable, str(SCRIPTS / "profile_export.py"),
                            str(acme), "--out", str(prof)],
                           capture_output=True, text=True)
            bs = (prof / "brain_structure.md").read_text() \
                if (prof / "brain_structure.md").exists() else ""
            check("final: profiler company design uses 30-content",
                  "`30-content/`" in bs and "`30-voice/`" not in bs, bs[:400])
            check("final: profiler company design routes files (not all unmapped)",
                  "`10-people/`" in bs and "`00-org/`" in bs, bs[:400])
    ned = FIXTURES / "personal" / "ned"
    if ned.is_dir():
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "p"
            subprocess.run([sys.executable, str(SCRIPTS / "profile_export.py"),
                            str(ned), "--out", str(prof)],
                           capture_output=True, text=True)
            bs = (prof / "brain_structure.md").read_text() \
                if (prof / "brain_structure.md").exists() else ""
            check("final: profiler person design unchanged (30-voice, no company names)",
                  "`30-voice/`" in bs and "30-content" not in bs
                  and "85-locations" not in bs, bs[:400])
    # grep guard: no hardcoded layer-folder PATH construction left in analyze.py
    # (folder names inside prompt/prose text are rewritten at emit time via the
    # layout map — only Path building must go through _L/brain_layout).
    # allowed: "00-org" is the subject-detection probe itself; "95-goals" is
    # analyze's own output dir, variant-invariant by design.
    asrc = (SCRIPTS / "analyze.py").read_text()
    hard = [f for f in re.findall(r'brain / "([0-9]{2}-[a-z-]+)"', asrc)
            if f not in ("00-org", "95-goals")] + \
        re.findall(r'scan_layer\(brain, "', asrc) + \
        re.findall(r'_iter_fm\(brain / "', asrc) + \
        re.findall(r'_count_bullets\(brain / "', asrc) + \
        re.findall(r'_top_bullets\(brain / "', asrc)
    check("final: no hardcoded layer paths in analyze.py", not hard, str(hard))
    dsrc = (SCRIPTS / "diagrams.py").read_text()
    check("final: diagrams.apply_layout is subject-aware",
          'def apply_layout(layout, subject="person")' in dsrc)
    psrc = (SCRIPTS / "profile_export.py").read_text()
    check("final: profiler re-applies the company layout",
          'apply_layout(_mapping.load_brain_layout(), "company")' in psrc)


def main():
    print("Second Brain Link — test harness\n")
    test_read_csv_preamble()
    test_urls()
    test_selfheal()
    test_doctor_and_autoheal()
    test_full_mode()
    test_company_and_gbrain()
    test_company_deepening()
    test_p0_fixes()
    test_google_expansion()
    test_new_sources()
    test_deepening_v2()
    test_model_v2()
    test_layout_v2()
    test_refresh_v2()
    test_verification_matrix()
    test_geocoder()
    test_sibling_split_and_providers()
    test_multi_entity_and_correlation()
    test_graphdata_and_avatars()
    test_mapping_engine()
    test_places_and_mappings_build()
    test_google_takeout_subsources()
    test_harvester_rescues_unmapped()
    test_analyze_org_trim_identity()
    test_template_folder_autoname()
    test_facebook_mapping()
    test_data_catalog()
    test_final_sweep()
    # Per-source fixtures live at tests/fixtures/<personal|company>/<entity>/<source>/.
    # Build each single source export on its own (exercises every adapter + the
    # vault invariants), independent of the multi-entity orchestration above.
    fixtures = []
    for zone in ("personal", "company"):
        zbase = FIXTURES / zone
        if not zbase.is_dir():
            continue
        for entity in sorted(zbase.iterdir()):
            if not entity.is_dir() or entity.name.startswith((".", "_")):
                continue
            for src in sorted(entity.iterdir()):
                if src.is_dir() and any(p.suffix.lower() in
                                        (".csv", ".json", ".ics", ".js", ".txt",
                                         ".md", ".xml", ".mbox", ".eml", ".gpx")
                                        for p in src.rglob("*")):
                    fixtures.append(src)
    if not fixtures:
        print("  (no source fixtures under tests/fixtures/<zone>/<entity>/<source>/)")
    # PII needles a fixture may plant to prove they never leak:
    pii_needles = ["secret-body-do-not-leak", "fixture@example.com", "+15555550123"]
    for fx in fixtures:
        print(f"\nFixture: {fx.relative_to(FIXTURES)}")
        run_fixture(fx, pii_needles)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
