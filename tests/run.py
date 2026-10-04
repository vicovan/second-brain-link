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
        # new on-device Timeline format → visited pins (home skipped, raw signals ignored)
        vis = list((out / "85-places").glob("Visited spot*.md"))
        vtxt = vis[0].read_text() if vis else ""
        check("travel: timeline (new format) visit → place", len(vis) == 1, str([v.name for v in vis]))
        check("travel: timeline visits aggregated by placeId", "2 visit(s)" in vtxt, vtxt[:300])
        check("travel: timeline HOME segment never becomes a pin", "48.85," not in allmd)
        check("travel: timeline no longer reported skipped",
              "`timeline` — skipped" not in cov, cov[-600:])
        # T-E5: country/city/kind are fields on place notes
        eif = out / "85-places" / "Eiffel Tower.md"
        etxt = eif.read_text() if eif.exists() else ""
        check("travel: place note carries country/city/kind fields",
              "country: FR" in etxt and "city: Paris" in etxt and "kind: saved" in etxt, etxt[:400])


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
            check("new: strava place has lat/lng", "lat: 38.7223" in atxt, atxt[:300])
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



def _job_search_gates(js):
    """The gates that stop an application being sent: knock-out screen, CV lint, answers lint,
    and learn.py refusing `applied` without them. All synthetic — a fictional candidate."""
    import subprocess as _sp, tempfile as _tf, json as _js, os as _os, pathlib, sys
    ko = js / "skills/job-apply/scripts/knockout.py"
    lint = js / "skills/cv-tailor/scripts/lint_cv.py"
    learn = js / "skills/job-scout/scripts/learn.py"
    for f in (ko, lint):
        check(f"job-search: {f.name} present", f.is_file())
    if not (ko.is_file() and lint.is_file()):
        return
    tmp = pathlib.Path(_tf.mkdtemp(prefix="sbl-js-"))
    run = lambda *a, **kw: _sp.run([sys.executable, *map(str, a)], capture_output=True, text=True, **kw)

    # --- knock-out screen ---------------------------------------------------------------
    ans = tmp / "application-answers.md"
    ans.write_text("# a\n## Knock-outs\n- right_to_work: EU, EEA\n- sponsorship_acceptable: GB\n"
                   "- based_in: PT\n- relocate_to: EU\n- nationalities: PT\n"
                   "- languages: English, Portuguese\n- degrees: BSc Mathematics\n"
                   "- years_experience: 15\n- salary_floor: EUR 100000\n## Next\n", encoding="utf-8")
    def jd(name, text):
        (tmp / name).write_text(text, encoding="utf-8")
        return tmp / name
    uk = jd("uk.txt", "Director of Engineering, London. You must have the right to work in the UK. "
                      "We are unable to offer visa sponsorship.")
    eu = jd("eu.txt", "Engineering Director. Remote across the EU. German is a plus.")
    lang = jd("lang.txt", "Head of Engineering, Helsinki. Fluent Finnish required.")
    low = jd("low.txt", "VP Engineering, Berlin. Salary €70,000 - €85,000.")
    nat = jd("nat.txt", "CTO, Riyadh. Saudi nationals only.")
    r = run(ko, "--jd", uk, "--answers", ans)
    check("knockout: UK right-to-work without sponsorship STOPs", r.returncode == 1 and "STOP" in r.stdout, r.stdout)
    r = run(ko, "--jd", eu, "--answers", ans)
    check("knockout: remote-EU role passes (flag only)", r.returncode == 0 and "STOP" not in r.stdout, r.stdout)
    for name, f in (("required language", lang), ("band below floor", low), ("nationality gate", nat)):
        r = run(ko, "--jd", f, "--answers", ans)
        check(f"knockout: {name} STOPs", r.returncode == 1, r.stdout)
    form = jd("form.txt", "Are you currently located in the United Kingdom?")
    r = run(ko, "--jd", eu, "--form", form, "--answers", ans)
    check("knockout: form location question STOPs", r.returncode == 1, r.stdout)
    r = run(ko, "--jd", eu, "--answers", tmp / "missing.md")
    check("knockout: no profile block exits 2", r.returncode == 2)

    # --- CV lint ------------------------------------------------------------------------
    prof = tmp / "profile.md"
    prof.write_text("# Profile\n### Tidewater Labs — VP Engineering\n- grew the team to 42 engineers\n"
                    "### Harbor Freight Data — Engineering Manager\n- cut build time by 37%\n", encoding="utf-8")
    good = """---
type: cv
name: Ada Example
headline: "VP Engineering · platform teams"
role: VP Engineering
email: ada@example.com
phone: "+00 000 000 000"
---

## Professional Summary
<!-- blocks: prose -->

**VP Engineering** who grew a platform organisation to 42 engineers. Short proof here.

## Work Experience
<!-- blocks: mixed -->

### VP Engineering | Tidewater Labs
*01/2021 – Present*
Lisbon, Portugal

- Grew the platform team to 42 engineers across two sites.
- Rebuilt the release process.

### Engineering Manager | Harbor Freight Data
*01/2016 – 12/2020*
Porto, Portugal

- Cut build time by 37% for the data platform.
"""
    cv = tmp / "app1" / "Ada_Example_CV_Acme.md"
    cv.parent.mkdir()
    cv.write_text(good, encoding="utf-8")
    r = run(lint, "cv", cv, "--profile", prof)
    check("lint_cv: clean CV passes", r.returncode == 0, r.stdout)
    check("lint_cv: writes gates.json", (cv.parent / "gates.json").is_file())
    bad_cases = {
        "roles out of date order": good.replace("*01/2016 – 12/2020*", "*01/2023 – 12/2024*"),
        "Why section": good + "\n## Why Acme\n<!-- blocks: mixed -->\n\n- Because.\n",
        "self-disqualifier": good.replace("Short proof here.", "I have not run a public company."),
        "banned phrase": good.replace("Rebuilt the release process.", "Spearheaded a seamless release process."),
        "number not in profile": good.replace("37%", "61%"),
        "negative parallelism": good.replace("Rebuilt the release process.", "Not just shipped features but rebuilt the release process."),
        "colon-list bullets": good.replace("- Grew the platform team to 42 engineers across two sites.\n- Rebuilt the release process.",
                                           "- Platform: grew the team to 42 engineers, two sites.\n- Release: rebuilt the process, the tooling and the cadence."),
        "summary sentence too long": good.replace("Short proof here.", "Ran the platform organisation through a "
                                                  "complete rebuild of the release process while the team kept shipping weekly "
                                                  "and grew across two sites and three product lines at the same time."),
        "headline without the target title": good.replace('headline: "VP Engineering · platform teams"',
                                                           'headline: "Engineering leader · platform teams"'),
        "level echo": good.replace("Rebuilt the release process.", "Director-level scope over the release process."),
        "mixed date formats": good.replace("*01/2016 – 12/2020*", "*2016 – 2020*"),
        "mixed British and American spelling": good.replace("Rebuilt the release process.",
            "Rebuilt the release process and organised the on-call rota for the analyzer team."),
        "mixed title forms": good.replace("### Engineering Manager | Harbor Freight Data",
            "### Chief Technology Officer | Harbor Freight Data").replace("### VP Engineering | Tidewater Labs", "### CTO | Tidewater Labs"),
        "present tense in an ended role": good.replace("- Cut build time by 37% for the data platform.",
            "- Cuts build time by 37% for the data platform."),
        "generic bullets": good.replace("- Grew the platform team to 42 engineers across two sites.\n- Rebuilt the release process.",
            "- Improved the engineering culture.\n- Rebuilt the release process."),
        "skills grid above the work history": good.replace("## Work Experience",
            "## Core Competencies\n<!-- blocks: kv -->\n\n- **Platform:** Kafka · Kubernetes\n\n## Work Experience"),
    }
    for label, text in bad_cases.items():
        cv.write_text(text, encoding="utf-8")
        r = run(lint, "cv", cv, "--profile", prof)
        check(f"lint_cv: {label} FAILs", r.returncode == 1, r.stdout[-300:])
    cv.write_text(good, encoding="utf-8")
    run(lint, "cv", cv, "--profile", prof)

    # A bullet wrapped over several source lines is ONE bullet — a split one renders its second
    # half at the left margin as a stray paragraph.
    sys.path.insert(0, str(lint.parent))
    import cv_md as _cvmd
    wrapped = good.replace("- Rebuilt the release process.",
                           "- Rebuilt the release process\n  for the data platform and\n  its two sister teams.")
    blocks = [b for sec in _cvmd.md_to_content(wrapped)["sections"] for b in sec["blocks"]]
    tail = [b for b in blocks if "sister teams" in (b.get("text") or "")]
    check("cv_md: a wrapped bullet stays one bullet",
          len(tail) == 1 and tail[0]["type"] == "bullet" and "Rebuilt" in tail[0]["text"], str(tail))

    # --- answers lint + learn.py refusal ------------------------------------------------
    env = dict(_os.environ, JOB_SEARCH_HOME=str(tmp / "state"))
    r = run(learn, "log-outcome", "--company", "Acme", "--role", "VP", "--job-key", "acme-vp",
            "--status", "filled", env=env)
    check("learn: filled logs", r.returncode == 0, r.stderr)
    appdir = next((tmp / "state" / "applications").glob("*/acme-vp"))
    r = run(learn, "log-outcome", "--company", "Acme", "--role", "VP", "--job-key", "acme-vp",
            "--status", "applied", env=env)
    check("learn: applied refused without answers.json and gates", r.returncode != 0 and "REFUSING" in (r.stderr + r.stdout))
    (appdir / "answers.json").write_text(_js.dumps({"Expected salary": "DEFLECT: ask first"}), encoding="utf-8")
    r = run(lint, "answers", appdir / "answers.json")
    check("lint_cv: placeholder in an answer FAILs", r.returncode == 1, r.stdout)
    (appdir / "answers.json").write_text(_js.dumps({"Expected salary": "EUR 120000",
        "Why this role": "Acme's move to self-serve onboarding is the problem I spent the last four years on "
                         "at Tidewater Labs, where the platform team grew to 42 engineers."}), encoding="utf-8")
    r = run(lint, "answers", appdir / "answers.json", "--profile", prof)
    check("lint_cv: a specific, clean answer passes", r.returncode == 0, r.stdout)
    (appdir / "gates.json").write_text((cv.parent / "gates.json").read_text(encoding="utf-8"), encoding="utf-8")
    run(lint, "answers", appdir / "answers.json", "--profile", prof)
    r = run(learn, "log-outcome", "--company", "Acme", "--role", "VP", "--job-key", "acme-vp",
            "--status", "applied", env=env)
    check("learn: applied refused without a recruiter review", r.returncode != 0)
    run(lint, "review", appdir, "--verdict", "shortlist", "--reads-generated")
    r = run(lint, "status", appdir)
    check("lint_cv: a shortlist that reads generated still blocks", r.returncode == 1, r.stdout)
    run(lint, "review", appdir, "--verdict", "shortlist")
    r = run(learn, "log-outcome", "--company", "Acme", "--role", "VP", "--job-key", "acme-vp",
            "--status", "applied", env=env)
    check("learn: applied accepted once every gate is green", r.returncode == 0, r.stderr + r.stdout)
    r = run(learn, "set-result", "--all-open", "--result", "rejected", "--note", "generic", env=env)
    check("learn: set-result --all-open records a result", r.returncode == 0 and "rejected" in r.stdout)
    r = run(learn, "kpi", env=env)
    check("learn: kpi leads with interviews", "INTERVIEWS" in r.stdout, r.stdout[:200])

def _fundraising_checks(fr):
    """The fundraising plugin's own invariants: the ledger's state machine, list import,
    the filter chain, the claims linter, form detection, the never-send rule, and the
    shipped defaults. Every run happens in a scratch state root, never the user's."""
    import subprocess as _sp, tempfile as _tf, json as _js, os as _os
    S = fr / "skills/raise-research/scripts"
    A = fr / "skills/raise-apply/scripts"
    with _tf.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = dict(_os.environ, FUNDRAISE_HOME=str(tmp / "state"), CLAUDE_PROJECT_DIR=str(tmp))
        prof_dir = tmp / "46-fundraising" / "profile"
        prof_dir.mkdir(parents=True)
        (prof_dir / "round.md").write_text(
            "---\ntype: fundraising-profile\nmin_net_cash: 150000\ngeography_ok: [global, europe]\n"
            "relocation: ok\nexclusions: [crypto]\nthesis_keywords: [ai, developer, data]\n"
            "off_thesis: [consumer]\n---\n", encoding="utf-8")
        (prof_dir / "company.md").write_text(
            "# Co\n- 25 sources, 609 tests.\n## Do not claim\n- users — none published\n",
            encoding="utf-8")

        def run(script, *args, stdin=None):
            r = _sp.run([sys.executable, str(script), *args], cwd=tmp, env=env,
                        capture_output=True, text=True, input=stdin)
            return r

        csvf = tmp / "list.csv"
        csvf.write_text(
            "Name,About,Website,Location\n"
            "Alpha Seed,Invests $25k - $50k in anything,alpha.example,Global\n"
            "Beta Ventures,Pre-seed AI and developer tools; checks $250K-$1M,beta.example,Europe\n"
            "Gamma Chain,Web3 and token infrastructure; $500K checks,gamma.example,Global\n"
            "Delta Local,Consumer brands only; $200K checks,delta.example,North America\n",
            encoding="utf-8")
        r = run(S / "ledger.py", "import-csv", str(csvf), "--origin", "fixture")
        check("fundraising: import-csv runs", r.returncode == 0, r.stderr[-300:])
        r2 = run(S / "ledger.py", "import-csv", str(csvf), "--origin", "fixture")
        check("fundraising: import-csv is idempotent",
              r2.returncode == 0 and '"created": 0' in r2.stdout, r2.stdout[-200:])
        txt = tmp / "list.txt"
        txt.write_text("500 Global Flagship Accelerator\n1) Epsilon Labs | by Epsilon\n"
                       "- Zeta Fund\nJane Roe - Eta Capital\n", encoding="utf-8")
        r = run(S / "ledger.py", "import-text", str(txt), "--origin", "fixture-text", "--kind", "program")
        names = {_js.loads(l)["name"] for l in (tmp / "state" / "targets.jsonl").read_text(encoding="utf-8").split("\n") if l.strip()}
        check("fundraising: import-text keeps a leading number that is part of the name",
              "500 Global Flagship Accelerator" in names and "Global Flagship Accelerator" not in names, str(sorted(names)))
        check("fundraising: import-text strips list numbers and bullets",
              "Epsilon Labs" in names and "Zeta Fund" in names and "Eta Capital" in names, str(sorted(names)))
        r = run(S / "ledger.py", "remove", "zeta-fund", "--why", "fixture")
        check("fundraising: remove archives instead of deleting",
              r.returncode == 0 and "zeta-fund" in (tmp / "state" / "removed.jsonl").read_text(encoding="utf-8"))
        recs = {}
        for line in (tmp / "state" / "targets.jsonl").read_text(encoding="utf-8").split("\n"):
            if line.strip():
                o = _js.loads(line)
                recs[o["key"]] = o
        check("fundraising: imports are desk-screened, never verified",
              all(r["status"] in ("screened", "out") and not r["claims"] for r in recs.values()))
        why = lambda k: (recs[k].get("out_reason") or "")  # noqa: E731
        check("fundraising: floor removes a sub-floor cheque", why("alpha-seed").startswith("floor"), why("alpha-seed"))
        check("fundraising: exclusions remove crypto", why("gamma-chain").startswith("exclusions"), why("gamma-chain"))
        check("fundraising: off-thesis removed", why("delta-local").startswith("thesis"), why("delta-local"))
        check("fundraising: an on-thesis fund survives", recs["beta-ventures"]["status"] == "screened")

        # the never-send rule: only the founder can mark a target contacted
        run(S / "ledger.py", "log-draft", "beta-ventures", "--path", "outreach/x/B.md")
        r = run(S / "ledger.py", "set-status", "beta-ventures", "contacted", "--by", "agent")
        check("fundraising: agent cannot mark an email sent", r.returncode != 0 and "only the founder" in (r.stderr + r.stdout))
        r = run(S / "ledger.py", "sent", "beta-ventures")
        check("fundraising: founder 'sent' starts the follow-up clock", r.returncode == 0 and '"follow-up"' in r.stdout, r.stdout + r.stderr)
        run(S / "ledger.py", "log-outcome", "beta-ventures", "passed")
        r = run(S / "ledger.py", "set-status", "beta-ventures", "queued", "--by", "founder")
        check("fundraising: re-queue after a no needs --different", r.returncode != 0)
        r = run(S / "ledger.py", "set-status", "beta-ventures", "queued", "--by", "founder",
                "--different", "a cofounder joined")
        check("fundraising: re-queue with a stated difference is allowed", r.returncode == 0, r.stderr[-200:])

        r = run(S / "render_brain.py", "--quiet")
        dash = tmp / "46-fundraising" / "Fundraising Dashboard.md"
        check("fundraising: render writes the dashboard", r.returncode == 0 and dash.is_file(), r.stderr[-300:])
        check("fundraising: manifest kept beside the ledger, not in the layer",
              (tmp / "state" / "_FUNDRAISE_GENERATED.json").is_file()
              and not (tmp / "46-fundraising" / "_FUNDRAISE_GENERATED.json").exists())
        check("fundraising: target note titled '(target)' so it never shadows an org note",
              (tmp / "46-fundraising" / "targets" / "Beta Ventures (target).md").is_file())

        draft = tmp / "answers.json"
        draft.write_text(_js.dumps({"fields": [
            {"label": "Traction", "answer": "5,000 users and 609 tests. [CONFIRM: date]",
             "required": True, "limit": {"n": 20, "unit": "chars"}},
            {"label": "Why now", "answer": "GDPR Art. 20 made 25 sources possible.",
             "limit": {"n": 100, "unit": "words"}}]}), encoding="utf-8")
        r = run(S / "lint_claims.py", str(draft))
        red = r.stdout
        check("fundraising: lint stops on [CONFIRM]", r.returncode == 1 and "CONFIRM" in red)
        check("fundraising: lint stops on a do-not-claim term", "users" in red)
        check("fundraising: lint stops on a number not in the profile", "5,000" in red)
        check("fundraising: lint stops on an over-limit answer", "> limit 20" in red)
        check("fundraising: lint ignores legal references and known numbers",
              "«20»" not in red and "«25»" not in red, red[-400:])
        check("fundraising: gates.json written", (tmp / "gates.json").is_file())
        d2 = tmp / "small.json"
        d2.write_text(_js.dumps({"fields": [{"label": "Why you",
                                              "answer": "I founded five startups."}]}), encoding="utf-8")
        r = run(S / "lint_claims.py", str(d2), "--out", str(tmp / "g2.json"))
        d3 = tmp / "neg.json"
        d3.write_text(_js.dumps({"fields": [{"label": "Traction", "answer": "Pre-users, 609 tests."}]}), encoding="utf-8")
        r3 = run(S / "lint_claims.py", str(d3), "--out", str(tmp / "g3.json"))
        check("fundraising: a hyphenated negation ('pre-users') is not a do-not-claim hit",
              r3.returncode == 0, r3.stdout[-300:])
        check("fundraising: lint stops on a spelled-out count the profile does not state",
              r.returncode == 1 and "five startups" in r.stdout, r.stdout[-300:])

        r = run(A / "detect_form.py", "https://tally.so/r/abc")
        check("fundraising: detect_form classifies tally", '"tally"' in r.stdout)
        page = tmp / "p.html"
        page.write_text('<input type="password"> Application fee: $50. Record a 1 minute video.', encoding="utf-8")
        r = run(A / "detect_form.py", "https://example.org/apply", "--html", str(page))
        o = _js.loads(r.stdout)
        check("fundraising: detect_form flags login, fee and video",
              o["needs_login"] and o["fee_signal"] and o["video_signal"], r.stdout)

        # --- v0.2: mailto, packages, the investor-review gate, Ready to send, import_doc ---
        import importlib.util as _iu
        spec = _iu.spec_from_file_location("sbl_mailto", S / "mailto.py")
        mm = _iu.module_from_spec(spec); spec.loader.exec_module(mm)
        from urllib.parse import urlparse as _up, parse_qs as _pq
        u, fb = mm.build("a@b.co", "x & y | ?#", "l1\nl2 é")
        q = _pq(_up(u).query)
        check("fundraising: mailto round-trips subject and body (CRLF, unicode, & | ? #)",
              not fb and q["subject"][0] == "x & y | ?#" and q["body"][0] == "l1\r\nl2 é" and "|" not in u, u)
        check("fundraising: an over-long mailto drops the body, keeps to + subject",
              mm.build("a@b.co", "s", "x" * 3000) == ("mailto:a@b.co?subject=s", True))
        PK = fr / "skills/raise-outreach/scripts/package.py"
        (tmp / "00-me").mkdir(exist_ok=True)
        (tmp / "00-me" / "identity.md").write_text("---\ntitle: Test Founder\n---\n", encoding="utf-8")
        benv = dict(env); benv.pop("FUNDRAISE_HOME", None)   # a brain: the state lives in .plugins/
        def brun(script, *args):
            return _sp.run([sys.executable, str(script), *args], cwd=tmp, env=benv, capture_output=True, text=True)
        brun(S / "ledger.py", "upsert", "--json", _js.dumps({"name": "Pkg Fund", "claims": {
            "thesis": {"v": "ai data infrastructure", "stamp": "✅", "src": "https://pkg.example", "at": "2026-01-15"},
            "cheque": {"v": "$250K-$1M", "stamp": "✅"}, "geography": {"v": "global", "stamp": "✅"},
            "cold_path": {"v": "email hello@pkg.example", "stamp": "✅"}}}))
        brun(S / "ledger.py", "rescreen")
        r = brun(PK, "init", "pkg-fund")
        pdir = Path(_js.loads(r.stdout)["package"]) if r.returncode == 0 else tmp
        check("fundraising: package init writes brief.md with a From-memory block",
              (pdir / "brief.md").is_file() and "## From memory" in (pdir / "brief.md").read_text(encoding="utf-8"), r.stderr[-300:])
        r = brun(PK, "fit", "pkg-fund", "--comparable", "10", "--why", "a comparable")
        fit = _js.loads(r.stdout) if r.returncode == 0 else {}
        check("fundraising: package fit scores and bands", fit.get("band") == "prepare" and fit.get("score", 0) >= 75, r.stdout + r.stderr[-200:])
        (pdir / "email.md").write_text('---\ntype: fundraising-email\ntitle: "Pkg Fund — email"\nto: hello@pkg.example\n'
                                       'subject: "Hello"\nhook_stamp: ✅\n---\nHi,\n\n609 tests.\n', encoding="utf-8")
        brun(PK, "mail", "pkg-fund"); brun(PK, "mail", "pkg-fund")
        em = (pdir / "email.md").read_text(encoding="utf-8")
        check("fundraising: mail writes both buttons once, and the mailto into frontmatter",
              em.count("[✉ Open in Mail") == 1 and "sbl-ask:" in em and "\nmailto: " in em, em[-400:])
        r = brun(PK, "status", "pkg-fund")
        check("fundraising: a package without a review is not ready", r.returncode == 1 and "review" in r.stdout)
        brun(S / "lint_claims.py", str(pdir / "email.md"), "--out", str(pdir / "gates.json"))
        brun(S / "lint_claims.py", "review", str(pdir), "--verdict", "pass", "--reason", "wrong stage")
        brun(S / "render_brain.py", "--quiet")
        dash = (tmp / "46-fundraising" / "Fundraising Dashboard.md").read_text(encoding="utf-8")
        check("fundraising: a 'pass' review renders no Mail button", "[✉ Open in Mail]" not in dash)
        brun(S / "lint_claims.py", "review", str(pdir), "--verdict", "take-meeting", "--reason", "strong")
        r = brun(PK, "status", "pkg-fund")
        brun(S / "render_brain.py", "--quiet")
        dash = (tmp / "46-fundraising" / "Fundraising Dashboard.md").read_text(encoding="utf-8")
        check("fundraising: lint green + take-meeting → PASS and a Mail button on the dashboard",
              r.returncode == 0 and "## Ready to send" in dash and "[✉ Open in Mail](mailto:hello@pkg.example" in dash, r.stdout)
        check("fundraising: a package index note is rendered", any(pdir.glob("* package *.md")))
        flat = tmp / "46-fundraising" / "outreach" / "2026-01-15"
        flat.mkdir(parents=True, exist_ok=True)
        (flat / "Old — email 2026-01-15.md").write_text("old body\n", encoding="utf-8")
        brun(S / "ledger.py", "upsert", "--json", _js.dumps({"name": "Old Fund"}))
        r = brun(PK, "adopt", "old-fund", str(flat / "Old — email 2026-01-15.md"))
        check("fundraising: adopt moves a flat draft into its package",
              not (flat / "Old — email 2026-01-15.md").exists()
              and (flat / "old-fund" / "email.md").read_text(encoding="utf-8") == "old body\n", r.stdout + r.stderr[-200:])
        srcdoc = tmp / "plan-src" / "Plan.md"
        srcdoc.parent.mkdir(exist_ok=True)
        (srcdoc.parent / "list.csv").write_text("Name\nX\n", encoding="utf-8")
        srcdoc.write_text("See [the list](list.csv), [facts](../YC/FACTS.md) and [site](https://x.example).\n", encoding="utf-8")
        r = brun(S / "import_doc.py", str(srcdoc), "--title", "Imported Plan")
        imp = tmp / "46-fundraising" / "research" / "Imported Plan.md"
        itxt = imp.read_text(encoding="utf-8") if imp.is_file() else ""
        check("fundraising: import_doc rewrites relative links, keeps http, copies the CSV",
              "[site](https://x.example)" in itxt and "](../YC" not in itxt and "`../YC/FACTS.md`" in itxt
              and (tmp / "46-fundraising" / "profile" / "materials" / "list.csv").is_file(), r.stdout + r.stderr[-200:])

    # shipped defaults and rails
    tmpl = (fr / "skills/raise-onboarding/references/answers-template.md").read_text(encoding="utf-8")
    check("fundraising: answers template defaults to supervised",
          "level: supervised" in tmpl and "level: autonomous" not in tmpl)
    sj = _json_load(fr / "studio.json")
    check("fundraising: studio tools never include a send-capable wildcard",
          not any("gmail" in t.lower() and t.endswith("*") for t in sj.get("tools", [])))
    # Personal needles are NOT listed here — this file is public, and a list of words to
    # guard against would itself publish them (see the test_plugins docstring). The local
    # sweep reads them from $SBL_PERSONAL_NEEDLES (a path outside the repo, one term per
    # line) and is skipped in CI. What CI enforces is structural: no founder-shaped example
    # is the shipped default, and the templates' worked example is fictional.
    import os as _os2
    nf = _os2.environ.get("SBL_PERSONAL_NEEDLES")
    if nf and Path(nf).is_file():
        import re as _re_n
        # one term per line; `re:` = a regex; an optional $SBL_PERSONAL_ALLOW file lists
        # "path-substring | term" pairs judged generic (lookup data, not a life)
        needles = []
        for l in Path(nf).read_text(encoding="utf-8").split("\n"):
            l = l.strip()
            if l and not l.startswith("#"):
                needles.append((l, _re_n.compile(l[3:] if l.startswith("re:") else _re_n.escape(l), _re_n.I)))
        af = _os2.environ.get("SBL_PERSONAL_ALLOW")
        allow = [tuple(x.strip().lower() for x in l.split("|", 1)) for l in
                 (Path(af).read_text(encoding="utf-8").split("\n") if af and Path(af).is_file() else [])
                 if "|" in l and not l.strip().startswith("#")]
        hits = []
        for f in fr.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".py", ".json", ".sh", ".yaml", ".txt") \
                    and "__pycache__" not in f.parts:
                txt = f.read_text(encoding="utf-8", errors="replace")
                rel = str(f.relative_to(fr))
                for raw, rx in needles:
                    m = rx.search(txt)
                    if m and not any((a == "*" or a in rel.lower()) and (b == "*" or b == m.group(0).lower())
                                     for a, b in allow):
                        hits.append(f"{rel}:{m.group(0)}")
        check("fundraising: no personal needles in the shipped plugin (local sweep)", not hits,
              str(hits[:6]))
    rt = (fr / "skills/raise-onboarding/references/round-template.md").read_text(encoding="utf-8")
    check("fundraising: round template ships a worked-example floor",
          bool(__import__("re").search(r"min_net_cash:\s*\d+", rt)))


def _json_load(p):
    import json as _j
    return _j.loads(Path(p).read_text(encoding="utf-8"))


def test_plugins():
    """plugins/ — the capability-pack surface. Structural guards only.

    A test that grepped for the author's real name, employer or salary would have to
    CONTAIN them, which is exactly what must not be in this repo. So the personal-needle
    sweep is a local pre-commit step; what CI enforces is the structure that makes a
    leak unlikely and a plugin portable.
    """
    plugins = REPO / "plugins"
    if not plugins.is_dir():
        return
    names = sorted(d.name for d in plugins.iterdir()
                   if d.is_dir() and (d / ".claude-plugin" / "plugin.json").is_file())
    check("plugins: at least one plugin present", bool(names), str(names))
    check("plugins: job-search is present", "job-search" in names, str(names))

    # --- job-search specifics -------------------------------------------------
    js = plugins / "job-search"
    if js.is_dir():
        learn = (js / "skills/job-scout/scripts/learn.py").read_text(encoding="utf-8")
        render = (js / "skills/job-scout/scripts/render_brain.py").read_text(encoding="utf-8")
        import re as _re0
        statuses = set(_re0.findall(r"\"([a-z_]+)\"",
                                    _re0.search(r"STATUSES = \[(.*?)\]", learn, _re0.S).group(1)))
        glyphs = set(_re0.findall(r"\"([a-z_]+)\":",
                                  _re0.search(r"STATUS_GLYPH = \{(.*?)\}", render, _re0.S).group(1)))
        # An application can only be RENDERED in a state the writer can RECORD. When
        # "filled" existed as a glyph but not as a status, an application that was built
        # and filled but not yet sent could not be logged, so it never reached the vault.
        results = set(_re0.findall(r"\"([a-z_]+)\"",
                                   _re0.search(r"RESULTS = \[(.*?)\]", learn, _re0.S).group(1)))
        vocab = statuses | results
        missing = sorted(g for g in glyphs if g not in vocab and not g.startswith("skipped"))
        check("job-search: every rendered status can be logged", not missing, str(missing))

        # Auto-submit is opt-in. The shipped template must not arrive set to autonomous:
        # a stranger installing this from the repo would find it applying in their name.
        tmpl = (js / "skills/job-onboarding/references/answers-template.md").read_text(encoding="utf-8")
        check("job-search: answers template defaults to supervised",
              "level: supervised" in tmpl and "level: autonomous" not in tmpl.split("```")[1])

        _job_search_gates(js)

    # --- fundraising specifics ------------------------------------------------
    fr = plugins / "fundraising"
    if fr.is_dir():
        _fundraising_checks(fr)

    import json as _json
    for name in names:
        root = plugins / name
        meta = _json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        for key in ("name", "version", "description", "license"):
            check(f"{name}: plugin.json has {key}", bool(meta.get(key)))
        check(f"{name}: plugin.json name matches folder", meta.get("name") == name,
              f"{meta.get('name')} != {name}")
        check(f"{name}: README.md present", (root / "README.md").is_file())

        # A plugin that reaches the network declares it — the engine's zero-network
        # promise stays true because plugins are a separate surface that says so.
        py = " ".join(f.read_text(encoding="utf-8", errors="replace")
                      for f in root.rglob("*.py"))
        if "urllib.request" in py or "http.client" in py:
            net = meta.get("network") or {}
            check(f"{name}: network use is declared in plugin.json", bool(net.get("required")))
            check(f"{name}: network declaration lists endpoints", bool(net.get("endpoints")))

        # Every SKILL.md obeys the repo's frontmatter rules (§8).
        skills = sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").is_dir() else []
        check(f"{name}: has skills", bool(skills), str(len(skills)))
        for sk in skills:
            txt = sk.read_text(encoding="utf-8")
            check(f"{name}/{sk.parent.name}: frontmatter present", txt.startswith("---\n"))
            fm = txt[4:txt.index("\n---\n", 4)] if "\n---\n" in txt else ""
            desc = [l for l in fm.split("\n") if l.startswith("description:")]
            check(f"{name}/{sk.parent.name}: has description", bool(desc))
            if desc:
                val = desc[0].split("description:", 1)[1].strip()
                check(f"{name}/{sk.parent.name}: description < 1024", len(val) < 1024, str(len(val)))
                check(f"{name}/{sk.parent.name}: no bare colon in description", ": " not in val)
            check(f"{name}/{sk.parent.name}: declares allowed-tools",
                  any(l.startswith("allowed-tools:") for l in fm.split("\n")))

        # Portability + privacy guards across every text file in the plugin.
        import re as _re, ast as _ast
        bad_path, bad_state, bad_pronoun, bad_date = [], [], [], []
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix not in (".md", ".py", ".sh", ".json", ".txt"):
                continue
            body = f.read_text(encoding="utf-8", errors="replace")
            rel = f.relative_to(root)
            # A home-relative install path is a leftover when it is baked into CODE, and
            # documentation when the README names where `--install` puts things — which it
            # has to, since Studio reads that same location and ships no copy of its own.
            # An ABSOLUTE path is one machine's, and is never right anywhere.
            install_doc = str(rel) == "README.md"
            if "/Users/" in body or (
                not install_doc
                and ("~/.claude/skills/" in body or "~/.agents/skills/" in body)
            ):
                bad_path.append(str(rel))
            # "<state root>" is fine as prose in a docstring or comment. As a real
            # string literal it is a find-replace artifact that silently resolves to
            # a nonexistent directory — the exact bug this guard exists to catch.
            if f.suffix == ".py":
                try:
                    tree = _ast.parse(body)
                    docs = {id(_ast.get_docstring(n, clean=False))
                            for n in _ast.walk(tree)
                            if isinstance(n, (_ast.Module, _ast.FunctionDef,
                                              _ast.AsyncFunctionDef, _ast.ClassDef))}
                    for node in _ast.walk(tree):
                        if (isinstance(node, _ast.Constant) and isinstance(node.value, str)
                                and "<state root>" in node.value
                                and id(node.value) not in docs):
                            bad_state.append(f"{rel}:{node.lineno}")
                except SyntaxError:
                    pass
            if _re.search(r"\b(he|his|him|himself)\b", body, _re.I):
                bad_pronoun.append(str(rel))
            for m in _re.findall(r"20\d\d-\d\d-\d\d", body):
                if m != "2026-01-15":          # the one neutral example date
                    bad_date.append(f"{rel}:{m}")
        check(f"{name}: no absolute or install-specific paths", not bad_path, str(bad_path))

        # The application layout is DATED. A doc still describing the flat
        # applications/<job_key>/ shape sends the model to a folder the renderer no
        # longer writes, which is how an application became invisible in the vault.
        flat = [f"{f.relative_to(root)}:{i + 1}"
                for f in root.rglob("*.md") if f.is_file()
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").split("\n"))
                if "applications/<job_key>" in line]
        check(f"{name}: applications paths are dated, not flat", not flat, str(flat))
        check(f"{name}: no placeholder tokens left in code", not bad_state, str(bad_state))
        check(f"{name}: no gendered pronouns", not bad_pronoun, str(bad_pronoun))
        check(f"{name}: no run-history datestamps", not bad_date, str(bad_date[:5]))

        # Two SHAPES that a real de-personalisation leak took, caught structurally so
        # this file never has to contain the words it is guarding against.
        #
        # 1. A named attribution in prose — `- <Company>: "…"`. A reference file's
        #    examples come from the shipped fictional persona; a real company credited
        #    by name beside a quote means the example came from someone's actual run.
        # 2. A bold placeholder — `**<current employer>**`. Replacing the NAME while
        #    leaving the description beside it does not redact anything, and the
        #    emphasis is the tell: a table cell that had to be filled in from a life.
        attrib, boldph = [], []
        for f in sorted((root / "skills").rglob("references/*.md")) if (root / "skills").is_dir() else []:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").split("\n")):
                if _re.match(r"\s*-\s+[A-Z][A-Za-z]+:\s*\*?\"", line):
                    attrib.append(f"{f.relative_to(root)}:{i + 1}")
                if _re.search(r"\*\*<[a-z][a-z0-9 -]*>\*\*", line):
                    boldph.append(f"{f.relative_to(root)}:{i + 1}")
        check(f"{name}: no named attributions in reference examples", not attrib, str(attrib))
        check(f"{name}: no bold placeholders in reference tables", not boldph, str(boldph))

        # A user's ledger must never be committed. __pycache__ is excluded here on
        # purpose: simply RUNNING the plugin creates it, and both plugins/.gitignore
        # and build_plugin.py already drop it — failing the suite for a local run
        # would train people to ignore this check, which is the opposite of the point.
        leaks = [str(f.relative_to(root)) for f in root.rglob("*")
                 if f.is_file()
                 and "__pycache__" not in f.parts
                 and (f.suffix in (".pdf", ".jsonl", ".docx")
                      or f.name in ("seen.json", "brain-path.txt", ".DS_Store"))]
        check(f"{name}: no user state committed", not leaks, str(leaks))

        # Never hardcode a layer folder — resolve it, as the engine does.
        hard = []
        for f in root.rglob("*.py"):
            # paths.py is the plugin's own resolver: the folder names are DEFINED there,
            # exactly as the engine defines them in layout_for()'s fallback block, which
            # that guard exempts too. Everywhere else must go through layer(brain, key).
            if f.name == "paths.py":
                continue
            for m in _re.findall(r'"(\d\d-[a-z]+)"', f.read_text(encoding="utf-8", errors="replace")):
                hard.append(f"{f.relative_to(root)}:{m}")
        check(f"{name}: no stray layer-folder literals", not hard, str(hard))

        # A Studio agent needs its grounding file to actually exist.
        sj = root / "studio.json"
        if sj.is_file():
            s = _json.loads(sj.read_text(encoding="utf-8"))
            for key in ("id", "label", "grounding", "entrySkill", "layer"):
                check(f"{name}: studio.json has {key}", bool(s.get(key)))
            check(f"{name}: studio grounding file exists", (root / s["grounding"]).is_file(),
                  s.get("grounding", ""))
            check(f"{name}: studio entrySkill exists",
                  (root / "skills" / s["entrySkill"] / "SKILL.md").is_file(), s.get("entrySkill", ""))

    # Both packagings of every plugin must build, and must not carry each other's
    # manifest. The openai one is FLATTENED (Codex has no plugin concept), so it is
    # also where a script- or reference-name collision would first show up.
    for name in names:
        root = plugins / name
        if not (root / "providers" / "openai" / "SKILL.md").is_file():
            continue
        oz = REPO / "dist" / "plugins" / "openai" / (name + ".skill")
        cz = REPO / "dist" / "plugins" / "claude" / (name + ".zip")
        import zipfile as _zf2
        if oz.is_file():
            n = _zf2.ZipFile(oz).namelist()
            check(f"{name}: openai packaging has a flat scripts/",
                  any(x.startswith(name + "/scripts/") for x in n))
            check(f"{name}: openai packaging has a SKILL.md",
                  (name + "/SKILL.md") in n)
            check(f"{name}: openai packaging routes to workflow references",
                  any(x.startswith(name + "/references/") and
                      x[len(name) + 12:-3] in {d.name for d in (root / "skills").iterdir()}
                      for x in n))
            check(f"{name}: openai packaging drops the plugin-root variable",
                  not any("CLAUDE_PLUGIN_ROOT" in
                          _zf2.ZipFile(oz).read(x).decode("utf-8", "replace")
                          for x in n if x.endswith((".md", ".sh"))))
            check(f"{name}: openai packaging carries no claude manifest",
                  not any(".claude-plugin" in x for x in n))
        if cz.is_file():
            n = _zf2.ZipFile(cz).namelist()
            check(f"{name}: claude packaging carries no openai manifest",
                  not any("/providers/" in x for x in n))

    # The engine skill must NOT carry plugins — that is what keeps its zero-network
    # promise true and verifiable.
    skill_zip = REPO / "dist" / "claude" / "second-brain-link.skill"
    if skill_zip.is_file():
        import zipfile as _zf
        with _zf.ZipFile(skill_zip) as z:
            inside = [n for n in z.namelist() if "plugins/" in n]
        check("plugins: engine .skill does not bundle plugins", not inside, str(inside[:3]))

    # The layer key resolves per subject and is never hardcoded by a plugin.
    import build_vault as _bv
    check("plugins: travel layer key resolves (person+company)",
          _bv.layout_for("person")["travel"] == _bv.layout_for("company")["travel"] == "47-travel")
    check("plugins: jobs layer key resolves (person)", _bv.layout_for("person")["jobs"] == "45-jobs")
    check("plugins: jobs layer key resolves (company)", _bv.layout_for("company")["jobs"] == "45-hiring")
    check("plugins: fundraising layer key resolves (person)", _bv.layout_for("person")["fundraising"] == "46-fundraising")
    check("plugins: fundraising layer key resolves (company)", _bv.layout_for("company")["fundraising"] == "46-fundraising")



def test_travel_plugin():
    """travel-planner: the itinerary invariants, virtual-interlining refusal + stopover
    promotion, the map projection, render idempotence, and that an engine --refresh leaves
    the plugin's layer alone. Runs the plugin's own scripts inside a freshly built brain."""
    tp = REPO / "plugins" / "travel-planner"
    if not tp.is_dir():
        return
    S = tp / "skills" / "trip-planner" / "scripts"
    owner = FIXTURES / "personal" / "owner"
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "v"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(owner), "-o", str(out)],
                           capture_output=True, text=True)
        brain = out / "personal" / "owner-brain"
        brain = brain if brain.is_dir() else out
        env = {k: v for k, v in __import__("os").environ.items()
               if k not in ("TRAVEL_HOME", "CLAUDE_PROJECT_DIR", "SECOND_BRAIN_HOME")}

        def run(*args):
            return subprocess.run([sys.executable, str(S / args[0])] + list(args[1:]),
                                  capture_output=True, text=True, cwd=str(brain), env=env)

        pl = run("places.py", "--json")
        recs = json.loads(pl.stdout or "[]")
        check("travel: places.py reads the places layer with coordinates",
              any(x["name"] == "Eiffel Tower" and x["lat"] and x["country"] == "FR" for x in recs), pl.stderr[-300:])
        r1 = run("itinerary.py", "new", "--id", "paris-test", "--title", "Paris test")
        r2 = run("itinerary.py", "add-stop", "paris-test", "--place", "Paris", "--arrive", "2030-05-01", "--nights", "2")
        r3 = run("itinerary.py", "brain-pois", "paris-test", "--stop", "s1")
        r4 = run("itinerary.py", "plan-days", "paris-test")
        check("travel: itinerary new/add-stop/brain-pois/plan-days run",
              all(x.returncode == 0 for x in (r1, r2, r3, r4)), (r1.stderr + r2.stderr + r3.stderr + r4.stderr)[-400:])
        tdir = brain / "47-travel" / "trips" / "paris-test"
        it = json.loads((tdir / "itinerary.json").read_text()) if (tdir / "itinerary.json").exists() else {}
        pois = it.get("pois") or []
        check("travel: brain places become from_brain POIs linked to real notes",
              pois and all(p["from_brain"] and (brain / p["brain_note"]).is_file() for p in pois), str(pois)[:300])
        check("travel: plan-days allocates every POI to a day",
              sorted(i for s in it.get("stops", []) for dd in s.get("days", []) for i in dd["items"])
              == sorted(p["id"] for p in pois))
        gj = json.loads((tdir / "map.geojson").read_text()) if (tdir / "map.geojson").exists() else {}
        feats = gj.get("features") or []
        check("travel: map.geojson is a FeatureCollection with day-numbered POIs",
              gj.get("type") == "FeatureCollection" and any(f["properties"].get("feature") == "poi"
                                                            and f["properties"].get("day") for f in feats))
        check("travel: from_brain POIs carry a note_id Studio can resolve",
              all((brain / (f["properties"]["note_id"] + ".md")).is_file() for f in feats
                  if f["properties"].get("note_id")))
        bad = run("set-stay" if False else "itinerary.py", "set-stay", "paris-test", "--stop", "s1",
                  "--name", "Hotel", "--price", "100")
        check("travel: a price without quoted_at is refused", bad.returncode != 0 and "quoted-at" in bad.stderr)
        web = run("itinerary.py", "add-poi", "paris-test", "--stop", "s1", "--name", "Nowhere Cafe")
        check("travel: a place not in the brain needs coordinates (never invented)", web.returncode != 0)
        sys.path.insert(0, str(S))
        try:
            import itinerary as _it  # noqa
            bad_it = json.loads(json.dumps(it))
            bad_it["stops"][0]["role"] = "stopover"; bad_it["stops"][0]["nights"] = 0
            bad_it["pois"].append({"id": "px", "stop": "s1", "name": "Fake", "lat": 48.8, "lng": 2.3,
                                   "from_brain": True, "brain_note": "85-places/Not A Place.md"})
            errs = _it.validate(bad_it, brain)
            check("travel: a zero-night stopover is invalid", any("stopover" in e for e in errs), str(errs))
            check("travel: from_brain with no such note is invalid", any("from_brain" in e for e in errs), str(errs))
        finally:
            sys.path.remove(str(S))
            for m in ("itinerary", "geo", "paths", "places", "taste"):
                sys.modules.pop(m, None)
        # interline: a sub-floor connection is refused; an overnight 14h+ one becomes a stop
        fares = [
            {"id": "a", "provider": "x", "price": 300, "currency": "EUR", "quoted_at": "2030-01-01T10:00",
             "segments": [{"carrier": "EK", "number": "EK1", "from": "DXB", "to": "ICN",
                           "dep": "2030-05-01T03:00", "arr": "2030-05-01T16:00"}]},
            {"id": "b", "provider": "x", "price": 90, "currency": "EUR", "quoted_at": "2030-01-01T10:05",
             "segments": [{"carrier": "KE", "number": "KE2", "from": "ICN", "to": "HND",
                           "dep": "2030-05-02T09:00", "arr": "2030-05-02T11:30"}]},
            {"id": "c", "provider": "x", "price": 60, "currency": "EUR", "quoted_at": "2030-01-01T10:06",
             "segments": [{"carrier": "OZ", "number": "OZ3", "from": "ICN", "to": "HND",
                           "dep": "2030-05-01T17:00", "arr": "2030-05-01T19:20"}]}]
        fpath = Path(d) / "fares.json"
        fpath.write_text(json.dumps(fares))
        js = run("interline.py", "--fares", str(fpath), "--from", "DXB", "--to", "TYO", "--json")
        jl = json.loads(js.stdout or "[]")
        check("travel: interline refuses a sub-floor self-transfer",
              jl and not any(any(f["id"] == "c" for f in j["fares"]) for j in jl), js.stderr[-300:])
        check("travel: interline promotes an overnight layover to a stopover",
              any(j["stopovers"] == ["Seoul"] for j in jl), str(jl)[:300])
        run("itinerary.py", "new", "--id", "japan-test", "--title", "Japan test")
        pk = run("interline.py", "--fares", str(fpath), "--from", "DXB", "--to", "HND", "--pick", "1",
                 "--trip", "japan-test")
        jt = json.loads((brain / "47-travel" / "trips" / "japan-test" / "itinerary.json").read_text()) \
            if pk.returncode == 0 else {}
        so = [s for s in jt.get("stops", []) if s.get("role") == "stopover"]
        st_legs = [l for l in jt.get("legs", []) if l.get("self_transfer")]
        check("travel: the stopover is a real stop with a night",
              len(so) == 1 and so[0]["nights"] >= 1, pk.stderr[-300:])
        check("travel: the self-transfer leg carries risk and points at the stopover",
              st_legs and st_legs[0].get("stopover_stop") == so[0]["id"] and st_legs[0]["risk"]["why"]
              if so else False)
        # render: layer written, twice is a no-op, machinery hidden, no place shadowed
        run("itinerary.py", "activate", "paris-test")
        run("scout.py")
        a1 = run("render_brain.py")
        a2 = run("render_brain.py")
        layer = brain / "47-travel"
        check("travel: render writes the dashboard, ideas, love and the current trip map",
              all((layer / f).is_file() for f in ("Travel Dashboard.md", "Trip Ideas.md",
                                                   "Places I Love.md", "Current Trip.geojson")), a1.stderr[-300:])
        check("travel: a second render writes nothing", " 0 written" in a2.stdout, a2.stdout)
        check("travel: manifest lives in the hidden ledger, not the layer",
              (brain / ".plugins" / "travel-planner" / "_TRAVEL_GENERATED.json").is_file()
              and not (layer / "_TRAVEL_GENERATED.json").exists())
        places_titles = {p.stem.lower() for p in (brain / "85-places").glob("*.md")}
        shadow = [p.name for p in layer.rglob("*.md") if p.stem.lower() in places_titles]
        check("travel: no travel note shadows a place note", not shadow, str(shadow))
        jn = next(layer.rglob("Japan test — Flights.md"), None)
        check("travel: self-transfer risk is printed where the user reads",
              jn is not None and "Self-transfer" in jn.read_text() and "seen " in jn.read_text())
        # suggestion sets: a brain name is linked, a far coordinate refused, the Map layers written
        s1 = run("suggest.py", "new", "--id", "paris-coffee", "--title", "Coffee in Paris", "--near", "Paris")
        s2 = run("suggest.py", "add", "paris-coffee", "--name", "Eiffel Tower")
        s3 = run("suggest.py", "add", "paris-coffee", "--name", "Web Cafe", "--lat", "48.86", "--lng", "2.35",
                 "--kind", "cafe", "--why", "third-wave")
        far = run("suggest.py", "add", "paris-coffee", "--name", "Lyon Cafe", "--lat", "45.76", "--lng", "4.83")
        check("travel: suggest new/add run", all(x.returncode == 0 for x in (s1, s2, s3)),
              (s1.stderr + s2.stderr + s3.stderr)[-400:])
        check("travel: a suggestion far from its city is refused (never drawn in the wrong place)",
              far.returncode != 0 and "km from" in far.stderr, far.stderr[-200:])
        sset = json.loads((layer / "suggestions" / "paris-coffee.json").read_text()) \
            if (layer / "suggestions" / "paris-coffee.json").exists() else {}
        sp = {p["name"]: p for p in sset.get("picks") or []}
        check("travel: a brain place in a suggestion set is linked, a web pick is marked web only",
              sp.get("Eiffel Tower", {}).get("from_brain") and (brain / sp["Eiffel Tower"]["brain_note"]).is_file()
              and sp.get("Web Cafe", {}).get("why", "").startswith("no brain signal — web only")
              and not sp.get("Web Cafe", {}).get("from_brain"), str(sp)[:300])
        sg = json.loads((layer / "Suggestions.geojson").read_text()) if (layer / "Suggestions.geojson").exists() else {}
        sf = [f["properties"] for f in sg.get("features") or []]
        check("travel: Suggestions.geojson carries the active set and the trip ideas",
              (sg.get("properties") or {}).get("layer") == "suggestions"
              and sum(1 for f in sf if f["feature"] == "suggestion") == 2
              and any(f["feature"] == "idea" for f in sf), str(sf)[:300])
        ag = json.loads((layer / "All Trips.geojson").read_text()) if (layer / "All Trips.geojson").exists() else {}
        check("travel: All Trips.geojson has every trip, the current one flagged",
              (ag.get("properties") or {}).get("layer") == "trips"
              and {f["properties"]["trip_id"] for f in ag.get("features") or []} >= {"paris-test", "japan-test"}
              and all(f["properties"]["current"] == (f["properties"]["trip_id"] == "paris-test")
                      for f in ag.get("features") or []), str(ag.get("properties")))
        check("travel: the current trip's map is tagged as the trip layer",
              json.loads((layer / "Current Trip.geojson").read_text())["properties"].get("layer") == "trip")
        # quote sets: real prices only with when/where; tags; pick → trip; rendered as a list
        seg = lambda n, f, t, d, a: {"carrier": "TK", "carrier_name": "Turkish Airlines", "number": n,
                                     "from": f, "to": t, "dep": d, "arr": a}
        fl = [{"provider": "Google Flights", "url": "https://www.google.com/travel/flights", "price": 412,
               "currency": "EUR", "quoted_at": "2030-01-01T10:00", "total_min": 545,
               "segments": [seg("TK 873", "DXB", "IST", "2030-05-01T07:40", "2030-05-01T11:35"),
                            seg("TK 1827", "IST", "CDG", "2030-05-01T13:20", "2030-05-01T16:05")]},
              {"provider": "Emirates", "url": "https://www.emirates.com", "price": 620, "currency": "EUR",
               "quoted_at": "2030-01-01T10:04", "total_min": 445,
               "segments": [dict(seg("EK 73", "DXB", "CDG", "2030-05-01T08:30", "2030-05-01T13:55"), carrier="EK")]}]
        q1 = run("quotes.py", "new", "flights", "--id", "dxb-cdg", "--title", "Madrid to Paris",
                 "--from", "DXB", "--to", "CDG", "--date", "2030-05-01", "--trip", "paris-test")
        q2 = run("quotes.py", "add", "dxb-cdg", "--json", json.dumps(fl))
        noq = run("quotes.py", "add", "dxb-cdg", "--json", json.dumps(dict(fl[0], quoted_at="")))
        check("travel: quotes new/add run", q1.returncode == 0 and q2.returncode == 0, (q1.stderr + q2.stderr)[-300:])
        check("travel: a quoted price without quoted_at is refused", noq.returncode != 0 and "quoted_at" in noq.stderr)
        qs = json.loads((layer / "quotes" / "dxb-cdg.json").read_text()) if (layer / "quotes" / "dxb-cdg.json").exists() else {}
        tg = {o["id"]: o.get("tags", []) for o in qs.get("options") or []}
        check("travel: quote options are tagged Cheapest / Fastest",
              "Cheapest" in tg.get("f1", []) and "Fastest" in tg.get("f2", []), str(tg))
        check("travel: layovers computed at the same airport",
              (qs.get("options") or [{}])[0].get("layovers") == [{"at": "IST", "min": 105}], str(qs.get("options", [{}])[0].get("layovers")))
        fz = run("quotes.py", "fence", "dxb-cdg")
        check("travel: quotes fence prints the Studio card fence",
              fz.stdout.startswith("```flights") and '"quotes": "dxb-cdg"' in fz.stdout, fz.stdout)
        pk2 = run("quotes.py", "pick", "dxb-cdg", "f2")
        pt = json.loads((brain / "47-travel" / "trips" / "paris-test" / "itinerary.json").read_text())
        check("travel: picking a flight writes a priced, timestamped leg into the trip",
              pk2.returncode == 0 and any(l.get("quote") == "dxb-cdg:f2" and l["tickets"][0]["quoted_at"]
                                          for l in pt.get("legs", [])), pk2.stderr[-300:])
        run("quotes.py", "new", "stays", "--id", "paris-stay", "--title", "Paris stays", "--city", "Paris",
            "--checkin", "2030-05-01", "--checkout", "2030-05-03", "--trip", "paris-test", "--stop", "s1")
        st1 = run("quotes.py", "add", "paris-stay", "--json", json.dumps(
            {"provider": "Booking.com", "url": "https://www.booking.com/x", "name": "Hotel Test",
             "price_night": 150, "currency": "EUR", "quoted_at": "2030-01-01T10:10", "rating": 8.9, "reviews": 900}))
        sq = json.loads((layer / "quotes" / "paris-stay.json").read_text()) if (layer / "quotes" / "paris-stay.json").exists() else {}
        check("travel: a stay priced per night gets its total over the stay's nights",
              st1.returncode == 0 and (sq.get("options") or [{}])[0].get("price_total") == 300, st1.stderr[-200:])
        run("render_brain.py")
        a3 = run("render_brain.py")
        check("travel: each quote set renders a list note",
              (layer / "quotes" / "Madrid to Paris.md").is_file()
              and "| f2 ✔ picked |" in (layer / "quotes" / "Madrid to Paris.md").read_text()
              if (layer / "quotes" / "Madrid to Paris.md").is_file() else False)
        check("travel: a suggestion set renders a note, and a second render writes nothing",
              (layer / "suggestions" / "Coffee in Paris.md").is_file() and " 0 written" in a3.stdout, a3.stdout)
        # an engine --refresh leaves the plugin's layer byte-identical
        before = {p.relative_to(layer).as_posix(): p.read_bytes() for p in layer.rglob("*") if p.is_file()}
        rr = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(owner), "-o", str(out),
                             "--refresh"], capture_output=True, text=True)
        after = {p.relative_to(layer).as_posix(): p.read_bytes() for p in layer.rglob("*") if p.is_file()}
        check("travel: build_vault --refresh leaves 47-travel byte-identical",
              rr.returncode == 0 and before == after, rr.stderr[-300:])
        check("travel: --refresh leaves the plugin manifest intact",
              (brain / ".plugins" / "travel-planner" / "_TRAVEL_GENERATED.json").is_file())


def test_harness():
    """The Harness (engine/scripts/harness.py): goals, routines, reports and activity under the
    `agentwork` layer — the five steps every run follows (check before starting, pick up from the
    last report, work within limits, verified Done, clean handoff), deterministic and offline."""
    import json as _json
    import filecmp as _fc
    import importlib.util as _iu
    print("\n[harness]")
    sys.path.insert(0, str(SCRIPTS))
    import build_vault as _bv
    check("harness: agentwork layer in both subjects",
          _bv.layout_for("person").get("agentwork") == "96-agents"
          and _bv.layout_for("company").get("agentwork") == "96-agents")
    hsrc = (SCRIPTS / "harness.py").read_text(encoding="utf-8")
    check("harness: no non-portable strftime (Windows)", "%-d" not in hsrc and "%-H" not in hsrc)
    copies = [REPO / "plugins" / n / rel for n, rel in (
        ("job-search", "skills/job-scout/scripts/harness.py"),
        ("fundraising", "skills/raise-research/scripts/harness.py"),
        ("travel-planner", "skills/trip-planner/scripts/harness.py"))]
    check("harness: plugin copies are byte-identical to the engine's",
          all(c.is_file() and _fc.cmp(SCRIPTS / "harness.py", c, shallow=False) for c in copies))
    spec = _iu.spec_from_file_location("harness_t", SCRIPTS / "harness.py")
    H = _iu.module_from_spec(spec)
    spec.loader.exec_module(H)
    import datetime as _d
    # schedules
    ps = H.parse_schedule
    check("harness: schedule grammar", ps("WEEKDAYS 07:00") and ps("MON,THU 08:30") and ps("MONTHLY 1 07:00")
          and ps("EVERY 6h") and ps("manual")["kind"] == "manual" and ps("NOPE 7") is None and ps("DAILY 25:00") is None)
    mon9 = _d.datetime(2026, 10, 5, 9, 0)        # a Monday
    check("harness: last slot of a weekday schedule",
          H.last_slot(ps("WEEKDAYS 07:00"), mon9) == _d.datetime(2026, 10, 5, 7, 0)
          and H.last_slot(ps("WEEKDAYS 07:00"), _d.datetime(2026, 10, 4, 9, 0)) == _d.datetime(2026, 10, 2, 7, 0))
    check("harness: plain-English schedule", H.describe_schedule("WEEKDAYS 07:00") == "Weekdays at 07:00")
    # flat frontmatter round-trip (Obsidian Properties + the engine reader only take flat keys)
    fm, body = H.parse_note(H.render_fm({"a": "[[X]]", "b": True, "c": 3, "d": ["x: y", "[[Z]]"], "e": None})
                            + "\nbody")
    check("harness: frontmatter round-trips", fm == {"a": "[[X]]", "b": True, "c": 3, "d": ["x: y", "[[Z]]"], "e": None}
          and body == "body", str(fm))
    ada = FIXTURES / "personal" / "ada" / "linkedin"
    if not ada.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        brain = Path(d) / "ada-brain"
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(ada), "-o", str(brain)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            check("harness: fixture brain builds", False, r.stderr[-300:])
            return

        def hx(*args, now=None):
            cmd = [sys.executable, str(SCRIPTS / "harness.py"), "--brain", str(brain), "--json"]
            if now:
                cmd += ["--now", now]
            rr = subprocess.run(cmd + list(args), capture_output=True, text=True)
            try:
                return rr.returncode, _json.loads(rr.stdout) if rr.stdout.strip() else None
            except _json.JSONDecodeError:
                return rr.returncode, rr.stdout

        rc, w = hx("where")
        check("harness: resolves the agentwork folder", rc == 0 and w and w.get("folder") == "96-agents", str(w))
        rc, made = hx("routine-new", "--agent", "brain", "--title", "Weekly network review",
                      "--schedule", "MON 08:00", "--body", "Find three strong ties gone quiet.")
        check("harness: creates a routine note", rc == 0 and (brain / made["path"]).is_file(), str(made))
        hx("set", "Weekly network review", "enabled", "true")
        rc, due = hx("due", now="2026-10-05T09:00:00")
        row = next((x for x in due if x["routine"] == "Weekly network review"), {})
        check("harness: an enabled routine past its slot is due", row.get("action") == "run", str(row))
        hx("fired", "Weekly network review", "--slot", row.get("slot", ""))
        rc, due = hx("due", now="2026-10-05T09:30:00")
        row = next((x for x in due if x["routine"] == "Weekly network review"), {})
        check("harness: once fired, it waits for the next slot", row.get("action") == "wait", str(row))
        # dry run: the whole lifecycle with no model
        rc, res = hx("run", "Weekly network review")
        check("harness: --provider none writes an Activity note and a report",
              rc == 0 and (brain / res["run"]).is_file() and (brain / res["report"]).is_file(), str(res))
        check("harness: a run with nothing new is quiet (not in the inbox)", res.get("news") is False)
        rc, block = hx("last-report", "--routine", "Weekly network review", "--block")
        check("harness: the next run gets a LAST REPORT handoff block",
              isinstance(block, str) and "LAST REPORT" in block and "Next step" in block, str(block)[:200])
        # a real run: handoff fence + an open question -> news, Needs you, Inbox
        rc, op = hx("run-open", "--agent", "brain", "--routine", "Weekly network review", "--trigger", "schedule")
        runp = brain / op["run"]
        H2 = subprocess.run([sys.executable, str(SCRIPTS / "harness.py"), "--brain", str(brain), "run-append",
                             op["run"], "--line", "read 10-people"], capture_output=True, text=True)
        final = Path(d) / "final.txt"
        final.write_text("Done.\n```report\n" + _json.dumps({
            "done": [{"text": "Drafted 2 notes", "evidence": "`" + made["path"] + "`"}, {"text": "Claimed with no evidence"}],
            "not_done": ["One tie has no recent context"], "next": ["Send the drafts Thursday"],
            "needs_you": [], "news": True}) + "\n```\n", encoding="utf-8")
        asks = Path(d) / "asks.json"
        asks.write_text(_json.dumps([{"question": "Send the note to the first tie?", "answered": True,
                                       "answer": "No", "reason": "wrong timing"},
                                      {"question": "Which tie first?", "answered": False}]), encoding="utf-8")
        rc, cl = hx("run-close", op["run"], "--status", "awaiting", "--final-file", str(final),
                    "--asks-file", str(asks), "--wrote", made["path"])
        rep = (brain / cl["report"]).read_text(encoding="utf-8") if cl and cl.get("report") else ""
        check("harness: run-close writes Done / Not done yet / Next step / Needs you",
              all(h in rep for h in ("## Done", "## Not done yet", "## Next step", "## Needs you"))
              and "Which tie first?" in rep and "Send the drafts Thursday" in rep, rep[:300])
        check("harness: the pass-gate marks Done items verified or not, in the report itself",
              "Drafted 2 notes ✓" in rep and "Claimed with no evidence (couldn't verify)" in rep
              and "verified: 1 of 2" in rep, rep[:400])
        runtxt = runp.read_text(encoding="utf-8")
        check("harness: the Activity note records steps, the answer and the deny reason",
              "read 10-people" in runtxt and "wrong timing" in runtxt and "status: awaiting" in runtxt)
        rc, inbox = hx("inbox")
        kinds = {i["kind"] for i in inbox}
        waiting = [i for i in inbox if i["kind"] == "needs-you"]
        check("harness: inbox shows the waiting run ONCE, carrying its report's Needs you",
              len(waiting) == 1 and waiting[0].get("report") == cl["report"]
              and "Which tie first?" in waiting[0].get("needs_you", "")
              and not any(i["kind"] == "report" and i["path"] == cl["report"] for i in inbox), str(inbox)[:400])
        rid = waiting[0]["id"]
        rc, inbox2 = hx("inbox", "--dismiss", rid)
        check("harness: a dismissed inbox item stays dismissed", all(i["id"] != rid for i in inbox2))
        # pass-gate: Done needs evidence
        rc, ver = hx("verify", cl["report"])
        vmap = {v["text"]: v["verified"] for v in ver} if isinstance(ver, list) else {}
        check("harness: verify passes evidence-backed Done and fails evidence-free Done",
              vmap.get("Drafted 2 notes") is True and vmap.get("Claimed with no evidence") is False, str(vmap))
        # the write block's double-check: a routine run that changed a knowledge note is flagged
        rc, op2 = hx("run-open", "--agent", "brain", "--routine", "Weekly network review", "--trigger", "schedule")
        import time as _t
        _t.sleep(1.1)
        people = sorted((brain / "10-people").glob("*.md"))
        if people:
            people[0].write_text(people[0].read_text(encoding="utf-8") + "\n", encoding="utf-8")
        rc, cl2 = hx("run-close", op2["run"], "--status", "done")
        rep2 = (brain / cl2["report"]).read_text(encoding="utf-8") if cl2 and cl2.get("report") else ""
        rc, rv = hx("review", "list")
        check("harness: a routine that wrote outside its folder is flagged and queued for review",
              bool(people) and "outside its own folder" in rep2 and cl2.get("news") is True
              and any(x.get("kind") == "unexpected" for x in (rv or [])), rep2[:300])
        rc, wh = hx("where", "--agent", "job-search")
        check("harness: a job-search routine may not write people, orgs or another agent's folder",
              isinstance(wh, dict) and "10-people" in wh.get("protected", []) and "46-fundraising" in wh.get("protected", [])
              and "45-jobs" not in wh.get("protected", []), str(wh))
        # conditions are the agent's OWN scripts only
        ok, why = H.eval_condition(H.Brain(str(brain)), "job-search", "cmd: build_vault.py --help | exit 0")
        check("harness: a condition can't run a script outside its own plugin", ok is False, why)
        ok, why = H.eval_condition(H.Brain(str(brain)), "job-search", "cmd: ../../evil.py | exit 0")
        check("harness: a condition rejects path tricks", ok is False, why)
        sd = brain / ".plugins" / "job-search"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "last-run.txt").write_text(H.now().date().isoformat(), encoding="utf-8")
        ok, why = H.eval_condition(H.Brain(str(brain)), "job-search", "stamp_not_today: last-run.txt")
        check("harness: stamp_not_today honours the plugin's own stamp", ok is False, why)
        # check before starting: a missing agent fails with a plain reason, zero tokens
        rc, made2 = hx("routine-new", "--agent", "no-such-agent", "--title", "Ghost routine")
        rc, res2 = hx("run", "Ghost routine")
        check("harness: a failed check becomes a preflight-failed run that needs you",
              res2.get("status") == "preflight-failed" and res2.get("news") is True, str(res2))
        # seeding never overwrites an edit
        tpl = Path(d) / "tpl"
        (tpl / "routines").mkdir(parents=True)
        (tpl / "routines" / "Seeded one.md").write_text(H.render_fm({"schema": "sbl-routine/1", "type": "routine",
            "tags": ["routine"], "agent": "brain", "schedule": "manual", "enabled": True}) + "\n# Seeded one\n\nv1\n",
            encoding="utf-8")
        rc, sd1 = hx("seed", "--from", str(tpl), "--agent", "brain")
        seeded = brain / "96-agents" / "Routines" / "Seeded one.md"
        check("harness: seeded templates are created OFF", rc == 0 and "enabled: false" in seeded.read_text())
        seeded.write_text(seeded.read_text().replace("v1", "MY EDIT"), encoding="utf-8")
        (tpl / "routines" / "Seeded one.md").write_text((tpl / "routines" / "Seeded one.md").read_text()
                                                        .replace("v1", "v2"), encoding="utf-8")
        rc, sd2 = hx("seed", "--from", str(tpl), "--agent", "brain")
        check("harness: a user-edited routine is never overwritten (new version beside it)",
              "MY EDIT" in seeded.read_text() and (seeded.parent / "Seeded one.new.md").is_file(), str(sd2))
        (seeded.parent / "Seeded one.new.md").unlink()
        # goals: met only from the counter, and the goal's routines switch off
        rc, g = hx("goal-new", "--agent", "brain", "--title", "Reconnect", "--metric", "manual", "--target", "2",
                   "--routine", "Weekly network review")
        gp = brain / g["path"]
        rc, pr = hx("goal-progress", "Reconnect", "--check")
        check("harness: a goal below target stays active", pr.get("status") == "active", str(pr))
        txt = gp.read_text(encoding="utf-8")
        gp.write_text(txt.replace("status: active", "status: active\nprogress: 2"), encoding="utf-8")
        rc, pr = hx("goal-progress", "Reconnect", "--check")
        rfm = H.read_note(brain / "96-agents" / "Routines" / "Weekly network review.md")[0]
        check("harness: reaching the target marks the goal met and pauses its routines",
              pr.get("status") == "met" and rfm.get("enabled") is False, str(pr))
        rc, inbox_g = hx("inbox")
        check("harness: a met goal leaves one report in the inbox",
              len([i for i in inbox_g if i["kind"] == "report" and i["title"].startswith("Goal met")]) == 1,
              str([i["title"] for i in inbox_g]))
        # a goal whose routine runs without the counter moving stops itself — checked at run close
        hx("routine-new", "--agent", "brain", "--title", "Quiet routine", "--schedule", "manual")
        rc, g2 = hx("goal-new", "--agent", "brain", "--title", "Quiet goal", "--metric", "manual", "--target", "5",
                    "--routine", "Quiet routine")
        hx("set", "Quiet goal", "stop_after_runs", "2")
        hx("set", "Quiet routine", "goal", "[[Quiet goal]]")
        qfm = H.read_note(brain / "96-agents" / "Routines" / "Quiet routine.md")[0]
        check("harness: setting a goal link keeps it a link (the Studio editor sends [[Goal]])",
              qfm.get("goal") == "[[Quiet goal]]" and H._unscalar("[[A]]") == "[[A]]"
              and H._unscalar("[a, b]") == ["a", "b"], repr(qfm.get("goal")))
        hx("goal-progress", "Quiet goal", "--check")
        closes = []
        for _ in range(2):
            rc, o = hx("run-open", "--agent", "brain", "--routine", "Quiet routine", "--goal", "Quiet goal")
            rc, c = hx("run-close", o["run"], "--status", "done")
            closes.append(c)
        g2fm = H.read_note(brain / g2["path"])[0]
        check("harness: a goal with no progress in N runs stops, with the reason, and says so at run close",
              g2fm.get("status") == "stopped" and "No progress" in str(g2fm.get("stopped_why"))
              and (closes[-1] or {}).get("goal", {}).get("status") == "stopped"
              and (closes[0] or {}).get("goal") is None, str(closes))
        # the `changed:` condition compares against the routine's last real run
        HB = H.Brain(str(brain))
        ok0, _w = H.eval_condition(HB, "brain", "changed: 10-people/*.md", "Never ran")
        ok1, _w1 = H.eval_condition(HB, "brain", "changed: 10-people/*.md", "Quiet routine")
        people = sorted((brain / "10-people").glob("*.md"))
        if people:
            later = _d.datetime.now().timestamp() + 5
            __import__("os").utime(people[0], (later, later))
        ok2, _w2 = H.eval_condition(HB, "brain", "changed: 10-people/*.md", "Quiet routine")
        bad, _w3 = H.eval_condition(HB, "brain", "changed: ../*.md", "Quiet routine")
        check("harness: `changed:` runs on the first run, waits when nothing changed, fires on a change",
              ok0 and not ok1 and ok2 and not bad, f"{_w} | {_w1} | {_w2} | {_w3}")
        # review queue
        rc, it = hx("review", "add", "--kind", "duplicate", "--title", "Two Ada notes?", "--note", "10-people/Ada Lovelace.md")
        rc, inbox3 = hx("inbox")
        check("harness: a suggestion reaches the inbox", any(i["kind"] == "suggestion" for i in inbox3))
        # the health check's suspicions become suggestions — once, and never again once decided
        import health as _health
        fake_h = {"duplicate_suspicions": [["Ada Lovelace", "Ada King"]], "conflicts": []}
        fake_g = {"nodes": [{"type": "person", "title": "Ada Lovelace", "path": "10-people/Ada Lovelace.md"},
                            {"type": "person", "title": "Ada King", "path": "10-people/Ada King.md"}]}
        _health.queue_suggestions(brain, fake_h, fake_g)
        _health.queue_suggestions(brain, fake_h, fake_g)
        rc, rv = hx("review", "list")
        dups = [x for x in (rv or []) if x.get("kind") == "duplicate" and "Ada King" in x.get("title", "")]
        check("harness: health suspicions reach the review queue once", len(dups) == 1, str(rv))
        if dups:
            hx("review", "resolve", dups[0]["id"], "--resolution", "Kept them separate")
            _health.queue_suggestions(brain, fake_h, fake_g)
            rc, rv2 = hx("review", "list")
            check("harness: a suggestion you decided is never asked again",
                  not [x for x in (rv2 or []) if x.get("kind") == "duplicate" and "Ada King" in x.get("title", "")], str(rv2))
        # everything the harness wrote is a valid, link-clean, PII-clean note
        vault_invariants(brain, "harness brain", [])
        # an engine --refresh leaves the agentwork layer byte-identical
        layer = brain / "96-agents"
        before = {q.relative_to(layer).as_posix(): q.read_bytes() for q in layer.rglob("*") if q.is_file()}
        rr = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(ada), "-o", str(brain), "--refresh"],
                            capture_output=True, text=True)
        after = {q.relative_to(layer).as_posix(): q.read_bytes() for q in layer.rglob("*") if q.is_file()}
        check("harness: build_vault --refresh leaves 96-agents byte-identical", rr.returncode == 0 and before == after,
              rr.stderr[-300:])
        # analyze seeds the goal prompts as routines, idempotently
        a1 = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(brain), "--goals", "jobsearch,datamining"],
                            capture_output=True, text=True)
        a2 = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(brain), "--goals", "jobsearch,datamining"],
                            capture_output=True, text=True)
        check("harness: analyze turns goal prompts into routines (once)",
              (layer / "Routines" / "Find warm intros at my target companies.md").is_file()
              and "routine:" in a1.stdout and "routine:" not in a2.stdout, a1.stdout[-300:])
    # continuity (company): who is the ONLY link to a team / channel / organisation
    acme = FIXTURES / "company" / "acme"
    if acme.is_dir():
        with tempfile.TemporaryDirectory() as d2:
            cb = Path(d2) / "acme"
            subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(acme), "-o", str(cb)], capture_output=True, text=True)
            subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(cb), "--goals", "continuity"], capture_output=True, text=True)
            cf = cb / "95-goals" / "continuity.md"
            txt = cf.read_text(encoding="utf-8") if cf.is_file() else ""
            check("harness: the continuity report names single points of failure",
                  "| Person | Only link to | What |" in txt and "[[" in txt, txt[:200])
            check("harness: the continuity prompt becomes a handover routine",
                  (cb / "96-agents" / "Routines" / "Draft handovers for single points of failure.md").is_file())
    # every plugin's templates parse and carry valid schedules + known outcome counters
    for name in ("job-search", "fundraising", "travel-planner"):
        root = REPO / "plugins" / name
        sj = _json.loads((root / "studio.json").read_text(encoding="utf-8"))
        tdir = root / sj.get("templates", "harness")
        rts = sorted((tdir / "routines").glob("*.md"))
        gls = sorted((tdir / "goals").glob("*.md"))
        okr = all(H.parse_schedule(H.read_note(p)[0].get("schedule")) is not None
                  and H.read_note(p)[0].get("enabled") is False for p in rts)
        okg = all(str(H.read_note(p)[0].get("metric")) in (sj.get("outcomes") or {}) for p in gls)
        check(f"harness: {name} ships routine + goal templates (valid, off, counted)", rts and gls and okr and okg)



def test_dev_tools():
    """Step 9 (for developers): retrieval.py matches Studio's brain-retrieval.ts exactly (golden
    file generated by the TypeScript), query.py is read-only, `sbl eval --harness` passes with no
    model, the `sbl` dispatcher and the stdio MCP server answer."""
    import json as _json
    print("\n[dev tools]")
    sys.path.insert(0, str(SCRIPTS))
    import retrieval as _r
    gdir = FIXTURES / "retrieval"
    if (gdir / "golden.json").is_file():
        g = _json.loads((gdir / "graph.json").read_text(encoding="utf-8"))
        gold = _json.loads((gdir / "golden.json").read_text(encoding="utf-8"))["packs"]
        bad = []
        for gp in gold:
            pk = _r.build_pack(gp["query"], g["notes"], g["edges"])
            diff = max([abs(pk["activations"][k] - gp["activations"][k]) for k in gp["activations"]] or [0])
            if (list(pk["activations"]) != list(gp["activations"]) or diff > 1e-12 or pk["seeds"] != gp["seeds"]
                    or pk["waves"] != gp["waves"] or pk["triples"] != gp["triples"]):
                bad.append(gp["query"])
        check("retrieval.py reproduces brain-retrieval.ts exactly (golden file)", not bad, str(bad))
    acme = FIXTURES / "company" / "acme"
    with tempfile.TemporaryDirectory() as d:
        brain = Path(d) / "acme"
        subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(acme), "-o", str(brain)], capture_output=True, text=True)
        q = subprocess.run([sys.executable, str(SCRIPTS / "query.py"), str(brain), "--ask", "counts", "--json"], capture_output=True, text=True)
        rows = _json.loads(q.stdout or "[]")
        check("query.py counts notes by layer and type", any(r.get("type") == "person" for r in rows), q.stderr[-200:])
        w = subprocess.run([sys.executable, str(SCRIPTS / "query.py"), str(brain), "--sql", "DELETE FROM notes"], capture_output=True, text=True)
        check("query.py refuses anything but a SELECT", w.returncode != 0)
        a = subprocess.run([sys.executable, str(SCRIPTS / "retrieval.py"), str(brain), "Grace Hopper", "--json"], capture_output=True, text=True)
        pack = _json.loads(a.stdout or "{}")
        check("retrieval.py answers from a built brain", any("Grace" in k for k in pack.get("activations", {})), a.stderr[-200:])
        sbl = subprocess.run([sys.executable, str(REPO / "sbl"), "query", str(brain), "--ask", "counts"], capture_output=True, text=True)
        check("sbl dispatches to the engine scripts", sbl.returncode == 0 and "person" in sbl.stdout)
        msgs = "\n".join(_json.dumps(m) for m in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "sbl_query", "arguments": {"brain": str(brain), "ask": "counts"}}}]) + "\n"
        mcp = subprocess.run([sys.executable, str(REPO / "integrations" / "mcp" / "server.py")], input=msgs, capture_output=True, text=True, timeout=120)
        out = [_json.loads(l) for l in mcp.stdout.splitlines() if l.strip()]
        ok = (len(out) == 3 and out[0]["result"]["serverInfo"]["name"] == "second-brain-link"
              and len(out[1]["result"]["tools"]) >= 5 and "person" in out[2]["result"]["content"][0]["text"])
        check("the MCP server initializes, lists its tools and answers a call (stdio, no port)", ok, mcp.stderr[-300:])
    ev = subprocess.run([sys.executable, str(SCRIPTS / "eval.py"), "--harness"], capture_output=True, text=True, timeout=600)
    check("sbl eval --harness: every safety rule holds with no model", ev.returncode == 0, ev.stdout[-600:])


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
                           {"label": "Detected dialect", "value": "Portuguese"}]}
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
        check("travel: IG post venue → named place with coordinates",
              "title: Le Petit Zinc" in ptext and "lat: 48.854" in ptext, ptext[:0])
        check("travel: IG caption without coordinates is never a place",
              "shipping a new feature today" not in ptext and "sunrise over the city" not in ptext)
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
        g = Path(d) / "personal" / "john" / "google" / "Takeout"
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
                          "properties": {"name": "Home", "address": "12 Sycamore Row, Springfield"}}]}))
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
        brain = out / "personal" / "john-brain"
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
        check("travel: FB event location on events.md",
              ev.exists() and "📍 Harbor Loft" in ev.read_text(encoding="utf-8"))
        check("travel: FB event places → 85-places",
              "title: Harbor Loft" in plc and "title: Springfield Expo Hall" in plc, plc[:0])
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


def _tree_snapshot(root: Path):
    """(rel, size, mtime_ns, sha256) of every file under root — incl. .git/."""
    import hashlib
    import os as _os
    snap = {}
    for dp, dn, fn in _os.walk(root, followlinks=False):
        for f in fn:
            p = Path(dp) / f
            if p.is_symlink():
                snap[str(p.relative_to(root))] = ("link", _os.readlink(p))
                continue
            st = p.stat()
            snap[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns,
                                              hashlib.sha256(p.read_bytes()).hexdigest())
    return snap


def test_docs_sources():
    """Document-store sources (git_docs / google_drive): linked read-only through
    _SOURCE_LINK.json, tiered by the local scanner, rendered into the docs layer.
    Sensitive content never reaches the vault; every walked path is accounted
    for; originals (and .git/) stay byte-identical; --refresh is a no-op."""
    import os as _os
    sys.path.insert(0, str(REPO / "tools"))
    import gen_docs_fixture as gdf
    import docscan
    import doctax
    import doclink
    from sources.common import scrub_body

    # ---- scanner units: positive + guarded negative per rule family ----
    r = docscan.load_rules()
    pos = {"aws-access-key": f"k {gdf.FAKE_AWS}", "private-key-block": gdf.FAKE_PEM,
           "generic-assignment": gdf.FAKE_PASSWORD_LINE,
           "jwt": "eyJhbGciOiJIUzI1NiJ9a.eyJzdWIiOiIxMjM0NTY3ODkwIn0a.dozjgNryP4J3jVmNHl0w5N",
           "postman-environment": '{"_postman_variable_scope": "environment"}',
           "db-connection-string": "postgres://app:" + "s3cretPw@db.internal:5432/x"}
    for rid, text in pos.items():
        check(f"docscan: {rid} fires", rid in docscan.content_reasons(text, r))
    check("docscan: placeholder value is not a secret",
          not docscan.content_reasons("password = <your-password>", r))
    check("docscan: public test PAN is not a card leak",
          "card-luhn" not in docscan.content_reasons("test card 4111 1111 1111 1111", r))
    check("docscan: tokenization prose is clean",
          not docscan.content_reasons("The TSP issues a network token per device.", r))
    nm = lambda n: docscan.name_reasons({"name": n, "rel": n, "ext": ""}, r)
    check("docscan: credentials sheet flagged by name", "name-credentials" in nm("Acme-Access-Credentials.md"))
    check("docscan: password-policy doc allowed", not nm("password-policy-technical-specification.md"))
    check("docscan: tokenization doc allowed", not nm("Device Tokenization Guide.md"))
    check("docscan: .env flagged", bool(nm(".env.production")))
    t, m, enc, _ = docscan.extract_ooxml(gdf._ooxml("docx", ["hello agreement"]), 10 ** 6)
    check("docscan: OOXML text extracted (stdlib)", "hello agreement" in t and m == "ooxml")
    t, m, enc = docscan.extract_pdf(gdf._pdf("Quarterly plan"), 10 ** 6)
    check("docscan: PDF Tj text extracted (best effort)", "Quarterly plan" in t)
    check("scrub_body: phone + email masked, dates kept",
          scrub_body(f"call {gdf.PLANTED_PHONE}, {gdf.PLANTED_EMAIL}, 2025-03-01 - 2025-04-01")
          == "call [phone removed], [email removed], 2025-03-01 - 2025-04-01")
    # ---- taxonomy units ----
    tr = doctax.load_rules()
    c = doctax.classify("customers/Northwind-Data-Access-Credentials.md", tr)
    check("doctax: customer entity from filename prefix",
          c["category"] == "customers" and c["entity"] == "Northwind Data", str(c))
    check("doctax: folder outranks filename token",
          doctax.classify("product/Launch-Plan.md", tr)["category"] == "product")
    ka = doctax.version_info("Deck-v2", [], tr)
    kb = doctax.version_info("Deck-final", [], tr)
    kc = doctax.version_info("Deck-v1", [], tr)
    check("doctax: version ordering v1 < v2 < final",
          ka[0] == kb[0] == kc[0] and kc[2] < ka[2] < kb[2])

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        store = gdf.generate(d / "store")
        drive = gdf.generate_drive(d / "drive")
        data = d / "data"
        for kind, root in (("git_docs", store), ("google_drive", drive)):
            r_ = subprocess.run([sys.executable, str(SCRIPTS / "doclink.py"), "init", "--kind", kind,
                                 "--root", str(root), "--out", str(data / "company" / "initech" / kind),
                                 "--label", f"Initech {kind}"], capture_output=True, text=True)
            check(f"doclink: init {kind}", r_.returncode == 0, r_.stdout + r_.stderr)
        # refuse a dangerous root
        r_ = subprocess.run([sys.executable, str(SCRIPTS / "doclink.py"), "init", "--kind", "git_docs",
                             "--root", str(Path.home()), "--out", str(d / "x" / "git_docs")],
                            capture_output=True, text=True)
        check("doclink: refuses to link the home folder", r_.returncode != 0)
        # a git history (temp repo, local only) for the git metadata path
        git_ok = shutil.which("git") is not None
        if git_ok:
            env = dict(_os.environ, GIT_AUTHOR_NAME="Grace Hopper", GIT_AUTHOR_EMAIL="g" + "@example.com",
                       GIT_COMMITTER_NAME="Grace Hopper", GIT_COMMITTER_EMAIL="g" + "@example.com",
                       GIT_AUTHOR_DATE="2024-02-01T10:00:00", GIT_COMMITTER_DATE="2024-02-01T10:00:00")
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "docs"]):
                subprocess.run(["git", "-C", str(store), *args], env=env, capture_output=True)
            (store / "untracked-note.md").write_text("# Untracked\n\nnot committed yet\n", encoding="utf-8")
        before = _tree_snapshot(store)
        before_drive = _tree_snapshot(drive)
        out = d / "vault"
        _os.chmod(store, 0o555)
        try:
            r_ = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(data), "-o", str(out)],
                                capture_output=True, text=True)
        finally:
            _os.chmod(store, 0o755)
        check("docs: build with a read-only store succeeds", r_.returncode == 0, (r_.stdout + r_.stderr)[-600:])
        brain = out / "company" / "initech-brain"
        docs = brain / "65-documents"
        check("docs: documents layer written", (docs / "Documents.md").exists())
        check("docs: originals byte-identical after build (incl. .git/)", _tree_snapshot(store) == before)
        check("docs: drive folder byte-identical after build", _tree_snapshot(drive) == before_drive)

        alltext = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                            for p in brain.rglob("*") if p.is_file() and p.suffix in (".md", ".json"))
        allbytes = b"".join(p.read_bytes() for p in brain.rglob("*") if p.is_file())
        for needle in (gdf.NEEDLE_BODY, gdf.FAKE_AWS, gdf.FAKE_PEM, "Tr0ub4dor", gdf.PLANTED_EMAIL,
                       "zq81Lr0PAm2Nx7Kd", "lead3@example.org"):
            check(f"docs: planted secret never reaches the vault ({needle[:12]}…)",
                  needle not in alltext and needle.encode() not in allbytes)
        check("docs: docscan audit of the brain is clean", not docscan.audit(brain))

        def note(rel):
            p = docs / rel
            return p.read_text(encoding="utf-8") if p.exists() else ""
        cred = note("customers/northwind-data/northwind-data-access-credentials.md")
        check("docs: credentials sheet is a metadata-only stub",
              "sensitivity: sensitive-name" in cred and "content not imported" in cred
              and 'entity: "[[Northwind Data]]"' in cred, cred[:300])
        for rel, tier in (("ops/config/env.md", "sensitive-name"),
                          ("ops/postman/initech-postman-environment.md", "sensitive-name"),
                          ("compliance-security/pen-tests/q1-scan-report.md", "sensitive-path"),
                          ("engineering/notes-on-setup.md", "secret-detected"),
                          ("inbox/sales/contacts.md", "pii-dense"),
                          ("inbox/sales/intro-call.md", "sensitive-name"),
                          ("inbox/exports/bundle.md", "archive")):
            check(f"docs: {rel} → {tier} stub", f"sensitivity: {tier}" in note(rel), note(rel)[:200])
        lp = note("product/launch-plan.md")
        check("docs: clean md imported with body, links rewritten, pdf render copied",
              "# Launch plan" in lp and "[[pricing-model|" in lp and "[[deployment-guide|" in lp
              and "_files/" in lp and "[phone removed]" in lp and "[email removed]" in lp, lp[-700:])
        check("docs: version chain (v2 is latest)",
              "superseded_by: \"[[launch-plan-v2]]\"" in lp
              and 'is_latest: "true"' in note("product/launch-plan-v2.md"))
        check("docs: password policy stays clean", "sensitivity: clean" in note("compliance-security/password-policy.md"))
        check("docs: test PAN doc stays clean (number masked in body)",
              "sensitivity: clean" in note("product/device-tokenization.md")
              and "[card number removed]" in note("product/device-tokenization.md"))
        check("docs: office files imported with extracted text + copy",
              "Initech seed round" in note("fundraising/seed-deck.md")
              and "file_status: copied" in note("fundraising/seed-deck.md"))
        dg = note("engineering/deployment-guide.md")
        check("docs: byte-identical duplicate kept once (non-archive path wins)",
              "archive-old/Deployment-Guide.md" in dg, dg[:600])
        sv = note("engineering/system-architecture.md")
        check("docs: SVG document renders as an image (no XML source, viewBox intact in the copy)",
              "![System-Architecture](" in sv and "<svg" not in sv
              and any("0 0 1000 700" in f.read_text() for f in (docs / "_files").rglob("*.svg")), sv[-400:])
        check("docs: people named with a role in clean docs become people notes",
              (brain / "10-people" / "Bill Lumbergh.md").exists() and (brain / "10-people" / "Milton Waddams.md").exists()
              and (brain / "10-people" / "Samir Nagheenanajar.md").exists()
              and "relationship: founder" in (brain / "10-people" / "Bill Lumbergh.md").read_text()
              and "relationship: advisor" in (brain / "10-people" / "Milton Waddams.md").read_text())
        check("docs: nobody is mined from a metadata-only document",
              not any((brain / "10-people").glob("Lead*.md")))
        org = (brain / "00-org" / "organization.md")
        check("docs: doc-only company brain gets its organization note + logo",
              org.exists() and "avatar:" in org.read_text() and (brain / "_assets" / "logo.svg").exists())
        abrain = d / "analyzed-brain"
        shutil.copytree(brain, abrain)
        r_ = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), str(abrain), "--goals", "onboarding"],
                            capture_output=True, text=True)
        cg = (abrain / "95-goals" / "company-goals.md")
        vault_invariants(abrain, "analyzed docs brain", [gdf.NEEDLE_BODY, gdf.PLANTED_EMAIL])
        sys.path.insert(0, str(SCRIPTS))
        import build_vault as _bv
        st_ = _bv.refresh_sync(brain, abrain)
        check("analyze's own rewrites (Home, _SUMMARY, graph.json) never show up as refresh conflicts",
              not st_["conflicts"] and not list(abrain.glob("*.new.*")), str(st_["conflicts"]))
        check("docs: analyze derives company goals from the documents",
              r_.returncode == 0 and cg.exists() and "Reach 10 paying customers by Q4 2025" in cg.read_text()
              and "not a goal" not in cg.read_text(), (r_.stdout + r_.stderr)[-300:])
        gl = note("engineering/glyph.md")
        gcopy = next(iter((docs / "_files").rglob("Glyph.svg")), None)
        check("docs: an SVG without xmlns is namespaced in the vault copy (original untouched)",
              gcopy is not None and b"http://www.w3.org/2000/svg" in gcopy.read_bytes()
              and b"xmlns" not in (store / "engineering" / "Glyph.svg").read_bytes() and "![Glyph](" in gl)
        ri = note("product/remote-image.md")
        check("docs: a remote image with a local twin renders from the local copy",
              "](https://example.com" not in ri and "![flow](65-documents/_files/" in ri, ri[-300:])
        # ---- graph structure: areas, root, no author star ----
        gjs = json.loads((brain / "graph.json").read_text(encoding="utf-8"))
        gnodes = {n["id"]: n for n in gjs["nodes"]}
        gdeg = {}
        for e_ in gjs["edges"]:
            gdeg[e_["a"]] = gdeg.get(e_["a"], 0) + 1
            gdeg[e_["b"]] = gdeg.get(e_["b"], 0) + 1
        doc_ids = [i for i, n in gnodes.items() if n.get("type") == "document"]
        in_cat = {e_["a"] for e_ in gjs["edges"] if e_["type"] == "in_category"}
        check("graph: every document sits in an area (in_category edge)",
              doc_ids and all(i in in_cat for i in doc_ids),
              str([i for i in doc_ids if i not in in_cat][:3]))
        check("graph: category hub notes exist and hang under Documents",
              any(n.get("type") == "document-category" for n in gnodes.values())
              and "[[Documents]]" in (docs / "product" / "Product.md").read_text(encoding="utf-8"))
        check("graph: the company root is connected",
              gdeg.get("00-org/organization", 0) > 0, str(gdeg.get("00-org/organization")))
        if git_ok:
            check("graph: a dominant author is not linked from every document",
                  not any(e_["type"] == "authored" for e_ in gjs["edges"])
                  and "documents_authored:" in (brain / "10-people" / "Grace Hopper.md").read_text(encoding="utf-8"))
        check("graph: document sub-layers are listed for Studio's lanes",
              any(l.get("parent") == "docs" for l in gjs["layers"]) or len(doc_ids) < 60)
        check("graph: no plain 'linked' edge duplicates a typed one",
              not any(e_["type"] == "linked" and e_["a"] in doc_ids and gnodes.get(e_["b"], {}).get("type") == "document-category"
                      for e_ in gjs["edges"]))
        check("docs: agent tooling categorised", (docs / "engineering" / "agent-tooling").is_dir())
        gd = note("company/strategy/vision-2025.md")
        check("docs: .gdoc → url + id only, account email never read",
              "docs.google.com/document/d/abc123" in gd and gdf.PLANTED_EMAIL not in gd, gd[:400])
        check("docs: no .md under _files/", not list((docs / "_files").rglob("*.md")))
        check("docs: no absolute path in any note", str(d) not in alltext.replace(
            (brain / ".claude" / "settings.json").read_text(encoding="utf-8") if (brain / ".claude" / "settings.json").exists() else "", ""))
        st = json.loads((brain / ".claude" / "settings.json").read_text(encoding="utf-8"))
        check("docs: agent deny rules cover the original roots",
              any(str(store.resolve()).lstrip("/") in x and x.startswith("Read(//") for x in st["permissions"]["deny"]),
              str(st)[:300])
        cov = note("_DOCS_COVERAGE.md")
        walked = sum(1 for x in doclink.walk({"root_path": store.resolve(), "include": ["**"], "exclude": []}))
        walked += sum(1 for x in doclink.walk({"root_path": drive.resolve(), "include": ["**"], "exclude": []}))
        rows = [ln for ln in cov.splitlines() if ln.startswith("- `")]
        git_rows = [x for x in rows if x.startswith("- `.git/")]
        check("docs: coverage has one row per walked path", len(rows) == walked, f"{len(rows)} vs {walked}")
        check("docs: .git/ not walked (one summary row), symlink not followed",
              (not git_ok or (len(git_rows) == 1 and "folder not walked" in git_rows[0]))
              and any("link-outside` — symlink (not followed)" in x for x in rows), str(git_rows[:3]))
        guide = (brain / "CLAUDE.md").read_text(encoding="utf-8")
        check("docs: in-vault guide carries the Documents rules", "65-documents/Documents.md" in guide
              and "NEVER read, open, grep or list anything OUTSIDE this vault" in guide)
        check("docs: _STRUCTURE.md lists the documents layer", "65-documents/" in
              (brain / "_STRUCTURE.md").read_text(encoding="utf-8"))
        if git_ok:
            check("docs: git authors become people (names only)",
                  (brain / "10-people" / "Grace Hopper.md").exists() and "g@example.com" not in alltext)
            check("docs: git dates + vcs status on notes",
                  "last_commit: 2024-02-01" in lp and "vcs_status: tracked" in lp
                  and "vcs_status: untracked" in note("inbox/untracked-note.md"))
        vault_invariants(brain, "docs brain", ["secret-body-do-not-leak", gdf.PLANTED_EMAIL])
        gj = json.loads((brain / "graph.json").read_text(encoding="utf-8"))
        check("docs: graph has document nodes, no _index/_files nodes",
              any(n.get("type") == "document" for n in gj["nodes"])
              and not any("/_index/" in n["id"] or "/_files/" in n["id"] for n in gj["nodes"]))

        # ---- refresh is a no-op on unchanged stores; originals still untouched ----
        r_ = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(data), "-o", str(out), "--refresh"],
                            capture_output=True, text=True)
        rep = (brain / "_UPDATE_REPORT.md").read_text() if (brain / "_UPDATE_REPORT.md").exists() else ""
        check("docs: --refresh on unchanged stores = 0 conflicts, 0 updated",
              r_.returncode == 0 and "conflicts (kept yours, fresh copy beside as *.new.md): 0" in rep
              and "- updated: 0" in rep, rep[:400] + r_.stderr[-300:])
        check("docs: originals byte-identical after refresh", _tree_snapshot(store) == before)
        # ---- --exclude git_docs leaves the store out entirely ----
        r_ = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(data), "-o", str(d / "v2"),
                             "--exclude", "git_docs"], capture_output=True, text=True)
        cov2 = (d / "v2" / "company" / "initech-brain" / "65-documents" / "_DOCS_COVERAGE.md")
        check("docs: --exclude git_docs skips the linked store",
              r_.returncode == 0 and cov2.exists() and "Initech git_docs" not in cov2.read_text())


def test_company_graph_links():
    """Company brains: deals link their account, the company's own posts link the
    organization root, and the root links its map — no unlinked deal/post clouds."""
    acme = FIXTURES / "company" / "acme"
    if not acme.is_dir():
        return
    with tempfile.TemporaryDirectory() as d:
        data = Path(d) / "data" / "company" / "acme"
        shutil.copytree(acme, data)
        out = Path(d) / "v"
        r_ = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(Path(d) / "data"), "-o", str(out)],
                            capture_output=True, text=True)
        brain = out / "company" / "acme-brain"
        check("company graph: acme builds", r_.returncode == 0, r_.stderr[-300:])
        g = json.loads((brain / "graph.json").read_text(encoding="utf-8"))
        deg = {}
        for e_ in g["edges"]:
            deg[e_["a"]] = deg.get(e_["a"], 0) + 1
            deg[e_["b"]] = deg.get(e_["b"], 0) + 1
        deals = [n["id"] for n in g["nodes"] if n.get("type") == "deal"]
        posts = [n["id"] for n in g["nodes"] if n.get("type") == "post"]
        check("company graph: every deal is linked (account or the company)",
              all(deg.get(i, 0) > 0 for i in deals), str([i for i in deals if not deg.get(i)][:3]))
        check("company graph: every company post is linked to the organization",
              all(deg.get(i, 0) > 0 for i in posts), str([i for i in posts if not deg.get(i)][:3]))
        check("company graph: the organization root is connected",
              deg.get("00-org/organization", 0) > 0)
        vault_invariants(brain, "acme graph brain", [])


def test_team_roster():
    """teamroster.py — a company brain's own team from the user's personal brains
    (exact company match only; the owner's current position) and a team.json roster;
    a person named only in a customer document never becomes a company person."""
    import tempfile
    import teamroster
    import docentities
    from sources.common import Collector
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pb = td / "personal" / "ada-brain"
        (pb / "10-people").mkdir(parents=True)
        (pb / "00-me").mkdir(parents=True)
        def person(n, comp, role):
            (pb / "10-people" / f"{n}.md").write_text(
                f'---\ntype: person\ntitle: {n}\ncompany: "[[{comp}]]"\nrole: "{role}"\nstrength: 3\n---\n')
        person("Grace Hopper", "Globex", "Co-Founder & COO")
        person("Ned Stark", "Globex Inc.", "Board Member")
        person("Ann Other", "Globex Air Lines", "CEO")   # a different company
        (pb / "00-me" / "identity.md").write_text(
            "---\ntitle: Ada Lovelace\n---\n\n- **Co-Founder & CTO** — [[Globex]] (2024 – Present)\n"
            "- **CTO** — [[Globex]] (2019 – 2021)\n")
        root = td / "data" / "company" / "globex"
        root.mkdir(parents=True)
        (root / "team.json").write_text('[{"name": "Kim Roster", "role": "Advisor"}]')
        out = td / "company" / "globex-brain"
        out.mkdir(parents=True)
        brains = teamroster.personal_brains(out)
        check("team: sibling personal brains auto-detected", [b.name for b in brains] == ["ada-brain"])
        col = Collector()
        col.add_person("git_docs", "Grace Hopper", role="COO", company="Globex",
                       tags=["person/executive", "person/mentioned-in-docs"])
        teamroster.apply(col, "Globex", brains=brains, roster_root=root)
        names = {r["name"]: r for r in col.people.values()}
        check("team: exact company match joins, a longer company name does not",
              "Grace Hopper" in names and "Ned Stark" in names and "Ann Other" not in names, sorted(names))
        check("team: the owner's CURRENT position only", names.get("Ada Lovelace", {}).get("role") == "Co-Founder & CTO")
        check("team: own title beats a passing doc mention (kept as also-reported)",
              names["Grace Hopper"]["role"] == "Co-Founder & COO"
              and any(a[0] == "COO" for a in names["Grace Hopper"]["alt"].get("role", [])))
        check("team: board member tagged board", "person/board" in names["Ned Stark"]["tags"])
        check("team: roster file adds people no source names", "Kim Roster" in names
              and "person/advisor" in names["Kim Roster"]["tags"])
        check("team: no relationship fields cross over", not any(
            "strength" in r or r.get("connected_on") for r in names.values()))
    check("docs: role tail loses a dangling joiner",
          docentities._clean_role("Product Manager, Digital Product and") == "Product Manager, Digital Product")


def test_docs_connector():
    """plugins/docs-connector — the networked half of the document stores, tested
    OFFLINE: the git path clones a local temp repository; the Drive path runs
    against an injected fake HTTP layer. The mirror lives outside the data folder,
    the link is mode 'connector', the Drive sidecar carries no e-mail addresses,
    syncs are incremental, and a reseed brings the mirror into the brain."""
    import importlib.util
    import os as _os
    p = REPO / "plugins" / "docs-connector" / "skills" / "docs-connect" / "scripts" / "connector.py"
    if not p.is_file():
        return
    spec = importlib.util.spec_from_file_location("sbl_connector", p)
    con = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(con)
    try:
        con.check_git_url("https://user:pw@example.com/org/repo.git")
        refused = False
    except SystemExit:
        refused = True
    check("connector: refuses a URL with embedded credentials", refused)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        data = d / "data"
        _os.environ["SBL_CONNECTOR_HOME"] = str(d / "home")
        _os.environ["SBL_DRIVE_TOKEN_FILE"] = str(d / "home" / "token.json")
        try:
            # ---- git (local temp repository; no network) ----
            if shutil.which("git"):
                src = d / "remote"
                src.mkdir()
                (src / "Plan.md").write_text("# Plan\n\nShip it.\n", encoding="utf-8")
                env = dict(_os.environ, GIT_AUTHOR_NAME="Ada Lovelace", GIT_AUTHOR_EMAIL="a" + "@example.com",
                           GIT_COMMITTER_NAME="Ada Lovelace", GIT_COMMITTER_EMAIL="a" + "@example.com")
                for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "one"]):
                    subprocess.run(["git", "-C", str(src), *args], env=env, capture_output=True)
                r_ = subprocess.run([sys.executable, str(p), "add-git", "--data", str(data), "--entity", "initech",
                                     "--url", str(src)], capture_output=True, text=True, env=env)
                check("connector: add-git clones into the mirror", r_.returncode == 0, r_.stdout + r_.stderr)
                link = json.loads((data / "company/initech/git_docs/_SOURCE_LINK.json").read_text())
                mirror = Path(link["root"])
                check("connector: link is mode connector, mirror outside data/",
                      link["mode"] == "connector" and data.resolve() not in mirror.parents
                      and (mirror / "Plan.md").is_file())
                (src / "Roadmap.md").write_text("# Roadmap\n\nQ3.\n", encoding="utf-8")
                for args in (["add", "-A"], ["commit", "-q", "-m", "two"]):
                    subprocess.run(["git", "-C", str(src), *args], env=env, capture_output=True)
                r_ = subprocess.run([sys.executable, str(p), "sync", "--data", str(data)],
                                    capture_output=True, text=True, env=env)
                link = json.loads((data / "company/initech/git_docs/_SOURCE_LINK.json").read_text())
                check("connector: sync fast-forwards the mirror",
                      r_.returncode == 0 and (mirror / "Roadmap.md").is_file()
                      and link["connector"].get("last_sync"), r_.stdout + r_.stderr)
                out = d / "vault"
                r_ = subprocess.run([sys.executable, str(SCRIPTS / "build_vault.py"), str(data), "-o", str(out)],
                                    capture_output=True, text=True)
                brain = out / "company" / "initech-brain"
                check("connector: reseed brings the mirror into the brain",
                      r_.returncode == 0 and any(brain.rglob("roadmap.md")), r_.stderr[-300:])

            # ---- Google Drive (fake HTTP layer; no network) ----
            Path(_os.environ["SBL_DRIVE_TOKEN_FILE"]).parent.mkdir(parents=True, exist_ok=True)
            Path(_os.environ["SBL_DRIVE_TOKEN_FILE"]).write_text(json.dumps(
                {"refresh_token": "r", "client_id": "c", "client_secret": "s"}))
            state = {"files": {
                "root": [{"id": "f1", "name": "Strategy", "mimeType": "application/vnd.google-apps.folder"},
                         {"id": "d1", "name": "Notes.md", "mimeType": "text/markdown", "size": "12",
                          "md5Checksum": "m1", "modifiedTime": "2025-01-02T00:00:00Z",
                          "owners": [{"displayName": "Grace Hopper", "emailAddress": "g" + "@example.com"}]}],
                "f1": [{"id": "g1", "name": "Vision", "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2025-02-01T00:00:00Z", "webViewLink": "https://docs.google.com/document/d/g1"}]},
                "downloads": 0}

            def fake_http(method, url, body, headers):
                if url.startswith(con.TOKEN_URL):
                    return {"access_token": "t", "expires_in": 3600}
                if "/export" in url or "alt=media" in url:
                    state["downloads"] += 1
                    return b"# exported\n" if "/export" in url else b"# Notes\nhello\n"
                q = urllib_parse.parse_qs(urllib_parse.urlsplit(url).query)["q"][0]
                fid = q.split("'")[1]
                return {"files": state["files"].get(fid, [])}

            import urllib.parse as urllib_parse
            con.write_link(str(data), "initech", "google_drive", con.mirror_dir("initech", "google_drive"),
                           "Initech Drive", {"kind": "drive", "folder": "root"})
            mir = con.mirror_dir("initech", "google_drive")
            st = con.sync_drive(mir, "root", str(data), "initech", http=fake_http)
            side = (data / "company/initech/google_drive/_SOURCE_MANIFEST.json").read_text()
            check("connector: drive files + exported native doc land in the mirror",
                  (mir / "Notes.md").is_file() and (mir / "Strategy" / "Vision.docx").is_file()
                  and st["downloaded"] == 2, str(st))
            check("connector: drive sidecar keeps owner names, never e-mail addresses",
                  "Grace Hopper" in side and "@example.com" not in side)
            st2 = con.sync_drive(mir, "root", str(data), "initech", http=fake_http)
            check("connector: unchanged drive files are not downloaded again",
                  st2["downloaded"] == 0 and st2["unchanged"] == 2, str(st2))
            state["files"]["root"] = state["files"]["root"][:1]
            st3 = con.sync_drive(mir, "root", str(data), "initech", http=fake_http)
            check("connector: files deleted in Drive leave the mirror",
                  st3["removed"] == 1 and not (mir / "Notes.md").exists(), str(st3))
        finally:
            _os.environ.pop("SBL_CONNECTOR_HOME", None)
            _os.environ.pop("SBL_DRIVE_TOKEN_FILE", None)


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
    test_plugins()
    test_travel_plugin()
    test_harness()
    test_dev_tools()
    test_docs_sources()
    test_docs_connector()
    test_team_roster()
    test_company_graph_links()
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
