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


def main():
    print("Second Brain Link — test harness\n")
    test_read_csv_preamble()
    test_urls()
    test_selfheal()
    test_doctor_and_autoheal()
    test_full_mode()
    test_company_and_gbrain()
    test_sibling_split_and_providers()
    test_multi_entity_and_correlation()
    test_mapping_engine()
    test_places_and_mappings_build()
    test_google_takeout_subsources()
    test_harvester_rescues_unmapped()
    test_analyze_org_trim_identity()
    test_template_folder_autoname()
    test_facebook_mapping()
    test_data_catalog()
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
                if src.is_dir() and any(p.suffix.lower() in (".csv", ".json", ".ics")
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
