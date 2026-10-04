#!/usr/bin/env python3
"""seed_demo_agents.py — populate the demo brains' AGENT layers and the Harness, realistically.

`gen_demo_fixtures.py` makes the exports and `build_vault.py` + `analyze.py` make the two demo
brains. This third step gives those brains the work the agents would have left behind after a
fortnight of use, so Second Brain Studio's Agents · Inbox · Goals · Routines · Activity sections
(and the Map's trip overlay) are populated in the shipped demo instead of empty:

  personal/john-brain          Jobs Agent onboarded (profile, two shortlists, three applications
                               at different stages, one interview), Travel Agent onboarded (profile,
                               trip ideas, a Lisbon trip on the map), Fundraising left UN-onboarded
                               on purpose (its "Set me up" state is part of the demo), goals,
                               routines, reports, activity, review-first memory with one pending
                               inference, suggestions from the health check.
  company/acme-brain           Fundraising Agent onboarded for Acme's seed round (profile, eight
                               screened targets, one meeting counted toward the goal, a Funding
                               Plan), company goals + routines, reports, activity.

EVERY file is written by the real writer that owns it — learn.py / render_brain.py (jobs),
itinerary.py / scout.py / taste.py / render_brain.py (travel), ledger.py / render_brain.py
(fundraising), harness.py (goals, routines, reports, activity, suggestions), memory.py — never
by hand, so the shapes are exactly what Studio reads. The only hand-written files are the ones
the agents themselves write as prose: the profile notes, the shortlist reports and the Funding
Plan, in the format each SKILL.md prescribes. Dates are driven through each writer's own clock
(`--now`, patched module TODAYs) and are relative to --today, so the story stays coherent.

Honesty rules the content keeps: nothing was sent or booked; agents draft, people decide; every
"Done" item carries evidence that exists; the Travel trip is a draft (planned 0 of 1).

    python3 tools/seed_demo_agents.py --vault <dir with personal/john-brain + company/acme-brain>
                                      [--today 2026-10-03]

Stdlib only. Runs offline. Idempotent enough for a staging dir: run it ONCE per fresh build.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap

REPO = pathlib.Path(__file__).resolve().parent.parent
ENGINE = REPO / "engine" / "scripts"
PLUG = REPO / "plugins"
JOBS = PLUG / "job-search" / "skills" / "job-scout" / "scripts"
CV = PLUG / "job-search" / "skills" / "cv-tailor" / "scripts"
TRAVEL = PLUG / "travel-planner" / "skills" / "trip-planner" / "scripts"
FUND = PLUG / "fundraising" / "skills" / "raise-research" / "scripts"
PY = sys.executable

TODAY = dt.date(2026, 10, 3)
BACKDATE = dt.datetime(2026, 9, 1, 12, 0, 0)       # mtime of every built note before the runs


def D(days_ago, hhmm="07:00"):
    """ISO datetime `days_ago` before TODAY at hh:mm."""
    d = TODAY - dt.timedelta(days=days_ago)
    return f"{d.isoformat()}T{hhmm}:00"


def day(days_ago):
    return (TODAY - dt.timedelta(days=days_ago)).isoformat()


# ------------------------------------------------------------------------ plumbing
def sh(args, cwd, env=None, ok=(0,), quiet=False):
    e = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    e.pop("SBL_NOW", None)
    if env:
        e.update(env)
    r = subprocess.run([str(a) for a in args], cwd=str(cwd), env=e, capture_output=True, text=True)
    if r.returncode not in ok:
        print(f"\n✗ {' '.join(str(a) for a in args[:4])} … exited {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}",
              file=sys.stderr)
        raise SystemExit(1)
    if not quiet and r.stderr.strip():
        pass
    return r.stdout


def pyc(code, cwd, extra_path=()):
    """Run a snippet with the plugin's scripts dir on sys.path and the brain as cwd — the way
    the plugin itself resolves its state root — so a patched TODAY drives the real writer."""
    pre = "import sys\n" + "".join(f"sys.path.insert(0, {str(p)!r})\n" for p in extra_path)
    return sh([PY, "-c", pre + textwrap.dedent(code)], cwd)


def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def harness(brain, now, *args, as_json=False):
    cmd = [PY, ENGINE / "harness.py", "--brain", brain]
    if now:
        cmd += ["--now", now]
    if as_json:
        cmd.append("--json")
    out = sh(cmd + list(args), brain)
    return json.loads(out) if as_json else out


def run(brain, agent, when, status, steps, handoff=None, routine="", trigger="manual", title="",
        asks=None, wrote=None, stop_reason="", minutes=9):
    """One complete Activity record: open → steps → close, all at a chosen time."""
    args = ["run-open", "--agent", agent, "--trigger", trigger]
    if routine:
        args += ["--routine", routine]
    if title:
        args += ["--title", title]
    r = harness(brain, when, *args, as_json=True)
    path = r["run"]
    t0 = dt.datetime.fromisoformat(when)
    for i, line in enumerate(steps):
        t = t0 + dt.timedelta(seconds=20 + i * 50)
        harness(brain, t.isoformat(), "run-append", path, "--line", line)
    tend = (t0 + dt.timedelta(minutes=minutes)).isoformat()
    close = ["run-close", path, "--status", status]
    tmp = []
    if handoff is not None:
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        f.write("Report follows.\n\n```report\n" + json.dumps(handoff, ensure_ascii=False) + "\n```\n")
        f.close()
        tmp.append(f.name)
        close += ["--final-file", f.name]
    if asks:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(asks, f)
        f.close()
        tmp.append(f.name)
        close += ["--asks-file", f.name]
    if wrote:
        close += ["--wrote", "\n".join(wrote)]
    if stop_reason:
        close += ["--stop-reason", stop_reason]
    out = harness(brain, tend, *close, as_json=True)
    for f in tmp:
        os.unlink(f)
    return out


def backdate(brain):
    """Every built note gets a past mtime so the Harness's stray-write check (mtime-based,
    harness.changed_since) sees the runs seeded below as clean. Staging only."""
    ts = BACKDATE.timestamp()
    n = 0
    for p in pathlib.Path(brain).rglob("*"):
        if p.is_file():
            os.utime(p, (ts, ts))
            n += 1
    return n


# ======================================================================== JOHN — Jobs Agent
def john_jobs_profile(brain):
    pd = brain / "45-jobs" / "profile"
    write(pd / "profile.md", f"""
    ---
    type: profile
    title: Career profile — John Carter
    tags: [jobsearch, profile]
    owner: John Carter
    updated: {day(12)}
    ---

    > The only source of facts for a CV or an application answer. If it is not here, it is asked —
    > never inferred, never rounded up.

    # Career profile — John Carter

    ## 1. Contact sets

    | Set | Location | Phone | Email | Status line |
    |---|---|---|---|---|
    | `us` | San Francisco, US | +00 000 000 000 | john@example.com | `US citizen · hybrid SF · remote OK` |
    | `eu` | London, GB | +00 000 000 000 | john@example.com | `US citizen · UK settled status · remote` |

    Links in a CV header: linkedin.com/in/johncarter

    ## 2. Positioning

    Product leader who has shipped industrial robots end to end — hardware, autonomy software and
    the fleet service around them — and founded a company that sells them to small manufacturers.
    Strongest when a product has to work on a factory floor, not in a demo.

    ## 3. Domains

    Collaborative robotics × small-manufacturer go-to-market (the rare intersection) · fleet
    operations software · functional safety · warehouse automation.

    ## 4. Roles (reverse chronological)

    ### Acme Robotics — Founder & CEO
    - **Dates:** 01/2020 – present
    - **Where:** San Francisco, US
    - **Allowed title variants:** Founder & CEO · Founder · CEO
    - **What it was:** collaborative robots and fleet software for small manufacturers.
    - **Scale:** 200 people · 12 customers · 110 opportunities in the pipeline
    - **Why it ended:** —
    - **Employment type:** founder (full-time)
    - **Facts:**
      - Took Cobot V2 from prototype to 12 paying customers across 3 countries.
      - Fleet software runs 240 robots; install time cut from 3 weeks to 4 days.
      - Raised nothing yet — bootstrapped on revenue; a seed round is in preparation.

    ### Meridian Labs — Director of Product
    - **Dates:** 02/2017 – 12/2019
    - **Where:** London, GB
    - **Allowed title variants:** Director of Product · Product Director
    - **What it was:** autonomy platform for industrial vehicles.
    - **Scale:** 3 product managers · 40 engineers across 4 squads
    - **Why it ended:** left to found Acme Robotics.
    - **Employment type:** full-time employee
    - **Facts:**
      - Owned the autonomy roadmap for 4 squads; shipped 2 platform releases a year.
      - Brought the first safety-certified release through TUV functional-safety review.

    ### Loopr Logistics — Head of Product
    - **Dates:** 03/2014 – 01/2017
    - **Where:** London, GB
    - **Allowed title variants:** Head of Product
    - **What it was:** warehouse automation line.
    - **Scale:** 2 product managers · 18 engineers
    - **Why it ended:** moved to Meridian Labs for the autonomy platform role.
    - **Employment type:** full-time employee
    - **Facts:**
      - Launched the picking line that handled 12,000 orders a day at the largest site.

    ## 5. Education, certifications, languages

    Bletchley Institute — MSc Robotics (2010–2012) · Functional Safety (TUV) · ROS 2 Developer ·
    English (native), Portuguese (conversational).

    ## 6. Numbers

    200 people (Acme headcount) · 12 customers · 240 robots in the field · 3 weeks → 4 days install ·
    40 engineers / 4 squads (Meridian) · 18 engineers (Loopr) · 12,000 orders a day (Loopr).

    ## 7. What this person has NOT done

    Never run a consumer product · no public-company experience · has not managed more than 200 people.

    ## 8. Contact-set decision rule

    `us` for US and remote-US roles; `eu` for UK/EU roles (no sponsorship needed in the UK).

    ## 9. Framing policy

    | Archetype | Current own venture shown as | Overlapping roles shown as |
    |---|---|---|
    | `advisor` | current role (the venture is the credential) | separate entries |
    | `product-leadership` | a "Founder" line alongside the employed roles | separate entries |
    """)
    write(pd / "search-criteria.md", f"""
    ---
    type: criteria
    title: Job search criteria
    tags: [jobsearch, profile, criteria]
    owner: John Carter
    updated: {day(12)}
    ---

    # Job search criteria

    ## 1. Lanes and titles
    - **advisor** — Board Advisor · Product Advisor · Fractional CPO · Fractional Head of Product
    - **product-leadership** — VP Product · Head of Product (robotics / industrial automation only)

    ## 2. Compensation
    Floor: USD 4,000 per month for a fractional engagement (≤ 2 days a week); USD 240,000 a year
    for a full-time role. A published figure below the floor: drop. No published figure: shortlist
    and flag.

    ## 3. Geography and work authorization
    Can work without sponsorship in the US and the UK · remote first · will not relocate · hybrid
    in San Francisco or London only.

    ## 4. Domains
    Robotics, industrial automation, logistics tech, hardware-enabled B2B. Adjacent but acceptable:
    developer tools for hardware teams.

    ## 5. Hard exclusions
    Crypto / digital assets · equity-only or co-founder roles · competitors of Acme Robotics ·
    anything requiring his own money · portals that need a new account to view the posting.

    ## 6. Freshness and volume
    14 days back · deliver 6 to 8 roles a sweep.
    """)
    write(pd / "scoring.md", f"""
    ---
    type: scoring
    title: Scoring weights
    tags: [jobsearch, profile, scoring]
    owner: John Carter
    updated: {day(12)}
    ---

    # Scoring weights

    | Component | Max |
    |---|---|
    | Shortlist likelihood | 30 |
    | Compensation | 15 |
    | Role fit | 15 |
    | Domain fit | 15 |
    | Geography and work mode | 10 |
    | Company quality and stage | 10 |

    - Apply floor: **70**. Shortlist-likelihood floor: **18 of 30**.
    - Disqualifiers: a required language he does not speak · must-be-based-in outside SF/London ·
      a title that is really a hands-on IC role.
    """)
    write(pd / "application-answers.md", f"""
    ---
    type: answers
    title: Settled application answers
    tags: [jobsearch, profile, answers]
    owner: John Carter
    updated: {day(12)}
    ---

    # Settled application answers

    ## 0. Autonomy

    ```
    level: supervised          # supervised | autonomous
    max-submits-per-run: 3
    daily-target: 2            # fractional roles are few; two valid applications a day is the pace
    ```

    ## 1. Work authorization
    US citizen; UK settled status. No sponsorship needed in either.

    ## 2. Notice and availability
    Available for a fractional engagement immediately, up to 2 days a week. Full-time: 3 months.

    ## 3. Compensation
    Fractional: from USD 4,000 a month. Full-time: from USD 240,000 base.

    ## 4. Framing
    Acme Robotics stays on the CV as the current role; a fractional engagement is additional to it,
    and the form answer says so plainly.

    ## Knock-outs
    - must be based in: anywhere except San Francisco, London, or remote
    - language required: any language other than English or Portuguese
    - security clearance required
    - equity-only compensation
    """)
    write(pd / "sources.md", f"""
    ---
    type: sources
    title: Where to look
    tags: [jobsearch, profile, sources]
    owner: John Carter
    updated: {day(12)}
    ---

    # Where to look

    - Tier 0 — open ATS boards of robotics and industrial-automation companies (Greenhouse, Lever, Ashby).
    - Tier 1 — advisory networks that publish roles publicly.
    - Queries: "fractional chief product officer robotics" · "product advisor automation" ·
      "VP product robotics" · "head of product industrial".
    - Never: boards that need an account to read the posting.
    """)
    write(pd / "archetypes.md", f"""
    ---
    type: archetypes
    title: Target archetypes
    tags: [jobsearch, profile, archetypes]
    owner: John Carter
    updated: {day(12)}
    ---

    # Target archetypes

    ## advisor · Advisory and fractional product leadership

    - **Target titles:** Fractional Chief Product Officer · Fractional Head of Product · Product Advisor · Board Advisor
    - **Trigger keywords:** fractional, advisor, advisory, part-time, interim
    - **Not this lane:** full-time VP roles wearing an "advisor" label in the first line.
    - **Evidence strength:** strong — he does this today for client companies.
    - **Headline pattern:** `Fractional CPO · robots on real factory floors`
    - **Summary skeleton:** founder running a 200-person robotics company → shipped 2 platforms before →
      knows small-manufacturer buyers → available 2 days a week.
    - **Lead proof points:** 12 customers in 3 countries · install 3 weeks → 4 days · TUV release.
    - **Bullet priority:** Acme deep · Meridian two bullets · Loopr one line.
    - **Why-angles:** he has sold to the same buyers; he has seen the same floor problems; a founder's
      time is cheapest spent where he already knows the answers.
    - **Stories:** S1, S2, S4
    - **Framing policy:** Acme is the current role, the engagement is additional.

    ## product-leadership · VP / Head of Product in robotics

    - **Target titles:** VP Product · Head of Product
    - **Trigger keywords:** vp product, head of product, robotics, automation, autonomy
    - **Not this lane:** platform PM roles; roles outside hardware-enabled products.
    - **Evidence strength:** moderate — his last employed product role ended in 2019.
    - **Headline pattern:** `VP Product · autonomy and fleet software that ships`
    - **Summary skeleton:** two product organisations led → a company founded on the lessons →
      what the posting's product needs next.
    - **Lead proof points:** 40 engineers / 4 squads · 2 releases a year · 240 robots in the field.
    - **Bullet priority:** Meridian deep · Acme as founder line · Loopr two bullets.
    - **Why-angles:** a product at the stage where he has been most useful; a team he could grow.
    - **Stories:** S1, S3, S4
    - **Framing policy:** founder venture as a line alongside the employed roles.
    """)
    write(pd / "stories.md", f"""
    ---
    type: stories
    title: Story bank
    tags: [jobsearch, profile, stories]
    owner: John Carter
    updated: {day(12)}
    ---

    # Story bank

    ## S1 · The install that took three weeks
    - **Tags:** ownership · delivery
    - **Situation:** Acme's first customer install took 3 weeks and the customer nearly walked.
    - **Task:** make the next one take days, not weeks, without a bigger field team.
    - **Action:** moved cell calibration into the fleet software and wrote the site checklist myself.
    - **Result:** the next install took 4 days; the checklist is still the one the team uses.
    - **Reflection:** the fix was a product decision, not a staffing one.
    - **Source:** Acme Robotics.

    ## S2 · Saying no to the biggest prospect
    - **Tags:** hard decision · scale
    - **Situation:** a 4,000-employee prospect asked for a custom gripper line.
    - **Task:** decide whether to take the revenue or protect the roadmap.
    - **Action:** declined the custom line, offered the standard kit with a retrofit option.
    - **Result:** lost the deal that quarter; won two smaller ones on the standard kit.
    - **Reflection:** the roadmap survived; the numbers in §6 are the roadmap's.
    - **Source:** Acme Robotics.

    ## S3 · Two releases a year, every year
    - **Tags:** leadership · delivery
    - **Situation:** Meridian's autonomy platform had shipped once in two years.
    - **Task:** make releases boring.
    - **Action:** one release train, 4 squads, a safety case written before the code.
    - **Result:** 2 platform releases a year; the first TUV-reviewed release.
    - **Reflection:** cadence is a safety feature.
    - **Source:** Meridian Labs.

    ## S4 · The picking line
    - **Tags:** scale · ambiguity
    - **Situation:** Loopr's largest site needed 12,000 orders a day from a line designed for 5,000.
    - **Task:** find the throughput without new hardware.
    - **Action:** re-sequenced the picks by zone; changed the operator UI first.
    - **Result:** 12,000 orders a day on the same hardware.
    - **Reflection:** the software was the cheaper machine.
    - **Source:** Loopr Logistics.
    """)
    print("  jobs: profile (7 files)")


def _cv(company, role, headline, summary, bullets):
    body = f"""---
type: cv
title: John Carter — {role}
tags: [jobsearch, cv]
name: John Carter
headline: "{headline}"
output_basename: John_Carter_CV_{company.replace(' ', '_')}
company: {company}
role: {role}
contact_set: us
email: john@example.com
phone: "+00 000 000 000"
location: San Francisco, US
status: US citizen
links:
  - text: linkedin.com/in/johncarter
    url: https://www.linkedin.com/in/johncarter/
---

## Professional Summary
<!-- blocks: prose -->

{summary}

## Experience
<!-- blocks: roles -->

### Founder & CEO | Acme Robotics · Collaborative Robotics for Small Manufacturers
*01/2020 – Present*
San Francisco, US · 200 people · 12 customers

{bullets}

### Director of Product | Meridian Labs · Autonomy Platform for Industrial Vehicles
*02/2017 – 12/2019*
London, GB

- Owned the robotics autonomy roadmap for 4 squads of 40 engineers and shipped 2 platform releases a year.
- Brought the first functional safety release through TUV review.

### Head of Product | Loopr Logistics · Warehouse Automation
*03/2014 – 01/2017*
London, GB

- Launched the picking line that handled 12,000 orders a day at the largest site.

## Education
<!-- blocks: entries -->

- **MSc Robotics** · Bletchley Institute — 2012
- Functional Safety (TUV) · ROS 2 Developer

## Skills
<!-- blocks: prose -->

Collaborative robotics, fleet software, functional safety, motion planning, ROS 2, field installation,
pricing for small manufacturers, autonomy roadmaps
"""
    return body


JOHN_APPS = [
    # (key, company, role, url, score, portal, archetype, likelihood, applied_on (days ago), stage)
    dict(key="analytical-engines-vp-product", company="Analytical Engines", role="VP Product",
         url="https://jobs.example.com/analytical-engines/vp-product", score=84, portal="greenhouse",
         archetype="product-leadership", likelihood=24, filled=15, applied=15, result=("interview", 4),
         headline="VP Product · autonomy and fleet software that ships",
         summary=("Product leader in robotics who has shipped two industrial platforms and then founded a company "
                  "on what they taught. At Meridian Labs the autonomy platform went from one release in two years "
                  "to two a year, the first of them through TUV functional-safety review. At Acme Robotics the fleet "
                  "software runs 240 robots on 12 customer floors today. Hardware teams trust the roadmap. The next "
                  "product should be one where the floor, not the demo, decides what ships."),
         bullets=("- Took the Cobot V2 robotics line from prototype to 12 paying customers in 3 countries.\n"
                  "- Cut install time from 3 weeks to 4 days by moving cell calibration into the fleet software.\n"
                  "- Fleet software runs 240 robots across 12 customer sites.")),
    dict(key="kiln-ceramics-fractional-head-of-product", company="Kiln Ceramics", role="Fractional Head of Product",
         url="https://jobs.example.com/kiln-ceramics/fractional-head-of-product", score=78, portal="lever",
         archetype="advisor", likelihood=22, filled=8, applied=8, result=None,
         headline="Fractional Head of Product · robots on real factory floors",
         summary=("Founder running a 200-person robotics company, available 2 days a week to a manufacturer putting "
                  "its first automation line in. Sold Cobot V2 to 12 small manufacturers and wrote the site checklist "
                  "that cut installs from 3 weeks to 4 days. The fleet software and the functional safety case were "
                  "product decisions before they were engineering ones. Ceramics is a new floor. The questions are not."),
         bullets=("- Took the Cobot V2 robotics line from prototype to 12 paying customers in 3 countries.\n"
                  "- Cut install time from 3 weeks to 4 days with a site checklist and fleet software calibration.")),
    dict(key="tidewater-marine-product-advisor-robotics", company="Tidewater Marine", role="Product Advisor (Robotics)",
         url="https://jobs.example.com/tidewater-marine/product-advisor", score=76, portal="ashby",
         archetype="advisor", likelihood=21, filled=1, applied=None, result=None,
         headline="Product Advisor (Robotics) · automation for a shipyard floor",
         summary=("Founder of a collaborative-robotics company, advising a marine manufacturer on its first automation "
                  "cell. Has sold and installed Cobot V2 at 12 small manufacturers in 3 countries and built the "
                  "fleet software that runs 240 of them. Brought a functional safety release through TUV review. "
                  "Marine is a new domain. Installing a first cell on a working floor is not."),
         bullets=("- Took the Cobot V2 robotics line from prototype to 12 paying customers in 3 countries.\n"
                  "- Brought the first Acme functional safety release through TUV review.")),
]


def john_jobs_ledger(brain):
    state = brain / ".plugins" / "job-search"
    for a in JOHN_APPS:
        # 1) the folder + ANSWERS.md, dated the day the application was started (status filled)
        pyc(f"""
            import argparse, learn
            learn.TODAY = {day(a['filled'])!r}
            ns = argparse.Namespace(job_key={a['key']!r}, company={a['company']!r}, role={a['role']!r},
                url={a['url']!r}, source="ats", score={a['score']!r}, portal={a['portal']!r}, status="filled",
                cv_variant={a['archetype']!r}, contact_set="us", keywords="robotics;fleet software;functional safety",
                note="", archetype={a['archetype']!r}, likelihood={a['likelihood']!r}, market="US", force_gates="")
            learn.cmd_log(ns)
        """, brain, [JOBS, CV])
        appdir = state / "applications" / day(a["filled"]) / a["key"]
        cvmd = appdir / f"John_Carter_CV_{a['company'].replace(' ', '_')}.md"
        cvmd.write_text(_cv(a["company"], a["role"], a["headline"], a["summary"], a["bullets"]), encoding="utf-8")
        write(appdir / "posting.md", f"""
        # {a['company']} — {a['role']}

        Source: <{a['url']}> · portal: {a['portal']} · seen {day(a['filled'])}

        {a['company']} is putting its first automation line in and wants a product leader who has
        shipped robots to a factory floor. Remote or San Francisco. Compensation not posted.
        """)
        write(appdir / "fit.md", f"""
        # Fit — {a['company']} / {a['role']}

        - Archetype: `{a['archetype']}` · score {a['score']}/100 · shortlist likelihood {a['likelihood']}/30
        - Why it fits: the same buyers Acme sells to; the posting asks for floor experience, not slides.
        - Gaps to prepare for: no marine / ceramics domain experience (profile §7).
        - Keywords led with: robotics · fleet software · functional safety

        ## Bullet plan
        | Requirement in the posting | Proof (profile §4/§6) |
        |---|---|
        | has put robots on a factory floor | 12 customers in 3 countries; 240 robots |
        | shortens installation | 3 weeks → 4 days (site checklist + in-software calibration) |
        | safety-minded | TUV functional-safety review |
        """)
        answers = {"Work authorization": "US citizen — no sponsorship needed",
                   "Availability": "Immediately, up to 2 days a week" if a["archetype"] == "advisor" else "3 months",
                   "Compensation expectation": "From USD 4,000 a month" if a["archetype"] == "advisor" else "From USD 240,000 base",
                   "Why this role": f"I have sold and installed robots to manufacturers like {a['company']} and know where the first line goes wrong.",
                   "Current role": "Founder & CEO, Acme Robotics — this engagement is additional to it"}
        (appdir / "answers.json").write_text(json.dumps(answers, indent=1), encoding="utf-8")
        # 2) the real gates: lint the CV, the answers and the reviewer's verdict
        prof = brain / "45-jobs" / "profile" / "profile.md"
        sh([PY, CV / "lint_cv.py", "cv", cvmd, "--profile", prof, "--fit", appdir / "fit.md",
            "--posting", appdir / "posting.md", "--keywords", "robotics;fleet software;functional safety"], brain, ok=(0, 1))
        sh([PY, CV / "lint_cv.py", "answers", appdir / "answers.json", "--profile", prof], brain, ok=(0, 1))
        sh([PY, CV / "lint_cv.py", "review", appdir, "--verdict", "shortlist",
            "--reason", "Reads as one person's real history; numbers all in the profile."], brain, ok=(0, 1))
        gates = json.loads((appdir / "gates.json").read_text(encoding="utf-8"))
        bad = [k for k in ("cv", "answers", "review") if not gates.get(k, {}).get("pass")]
        # 3) submitted (status applied) — only for the two that went out
        if a["applied"] is not None:
            force = f'force_gates={"gate " + ", ".join(bad) + " overruled for the demo fixture"!r}' if bad else 'force_gates=""'
            pyc(f"""
                import argparse, learn
                learn.TODAY = {day(a['applied'])!r}
                ns = argparse.Namespace(job_key={a['key']!r}, company={a['company']!r}, role={a['role']!r},
                    url={a['url']!r}, source="ats", score={a['score']!r}, portal={a['portal']!r}, status="applied",
                    cv_variant={a['archetype']!r}, contact_set="us", keywords="robotics;fleet software;functional safety",
                    note="Submitted through the employer's own form; confirmation page reached.",
                    archetype={a['archetype']!r}, likelihood={a['likelihood']!r}, market="US", {force})
                learn.cmd_log(ns)
            """, brain, [JOBS, CV])
        if a.get("result"):
            res, ago = a["result"]
            pyc(f"""
                import argparse, learn
                learn.TODAY = {day(ago)!r}
                learn.cmd_set_result(argparse.Namespace(job_key={a['key']!r}, keys="", all_open=False, result={res!r},
                    note="", feedback="We would like to meet you — a 45-minute conversation with the CTO next week."))
            """, brain, [JOBS, CV])
        print(f"  jobs: {a['key']} → {'applied' if a['applied'] is not None else 'filled'}"
              + (f" → {a['result'][0]}" if a.get('result') else "") + (f"  (gates failed: {bad})" if bad else ""))

    # the two shortlist reports the scout wrote (current list only, Status column second)
    rep = state / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    kiln_cv = f"../applications/{day(8)}/kiln-ceramics-fractional-head-of-product/John_Carter_CV_Kiln_Ceramics.pdf"
    tide_cv = f"../applications/{day(1)}/tidewater-marine-product-advisor-robotics/John_Carter_CV_Tidewater_Marine.pdf"
    write(rep / f"{day(8)}.md", f"""
    # Shortlist — {day(8)}

    Swept 14 days back across 31 open boards (Greenhouse 18, Lever 9, Ashby 4) + 2 advisory networks.
    61 postings seen · 9 new · 6 shortlisted · 2 left out (already applied).
    Target: 1/2 · shortlist 6 of 4

    | # | Status | Role | Company | Comp | Score | Apply | Status detail | CV |
    |---|---|---|---|---|---|---|---|---|
    | 1 | ✅ applied | [Fractional Head of Product](https://jobs.example.com/kiln-ceramics/fractional-head-of-product) | Kiln Ceramics | not posted | 78 | ✅ direct form (lever) | ✅ **Submitted** — confirmation page reached; the form had 11 fields and no account wall. | [CV]({kiln_cv}) |
    | 2 | ⬜ not started | [Product Advisor, Automation](https://jobs.example.com/foundry-metals/product-advisor) | Foundry Metals | USD 3,500/mo | 71 | ✅ direct form (greenhouse) | ⬜ Below the fractional floor by 500 — flagged, not dropped. | — |
    | 3 | ⬜ not started | [Head of Product](https://jobs.example.com/beacon-rail/head-of-product) | Beacon Rail | USD 230k | 70 | ✅ direct form (ashby) | ⬜ Full-time; base under the floor; hybrid London. | — |
    | 4 | ⛔ skipped | [Chief Product Officer](https://jobs.example.com/lantern-chain/cpo) | Lantern Chain | equity only | — | ⛔ excluded | 🚫 **Excluded by criteria** — equity-only compensation. | — |
    | 5 | ⬜ not started | [Fractional CPO](https://jobs.example.com/pallas-insurance/fractional-cpo) | Pallas Insurance | USD 6,000/mo | 68 | ✅ direct form (greenhouse) | ⬜ Insurance — outside the domains; below the apply floor. | — |
    | 6 | ⬜ not started | [VP Product, Fleet](https://jobs.example.com/verge-freight/vp-product-fleet) | Verge Freight | USD 250k | 74 | ⛔ account wall | ⛔ Needs a Workday account to see the form — handed back as a link. | — |

    > **Legend:** ✅ applied · 🟡 filled, awaiting submit · ⬜ not started · ⛔ skipped ·
    > ❌ disqualified · 🚫 excluded by criteria · 🔵 replied · 🎯 interview

    ## Also seen / near misses
    - [Product Manager, Robotics](https://jobs.example.com/gasworks-energy/pm-robotics) — Gasworks Energy — IC role wearing a senior title.

    ## Application log
    | When | Company | Role | Outcome |
    |---|---|---|---|
    | {day(8)} | Kiln Ceramics | Fractional Head of Product | ✅ applied |
    """)
    write(rep / f"{day(1)}.md", f"""
    # Shortlist — {day(1)}

    Swept 14 days back across 31 open boards + 2 advisory networks.
    48 postings seen · 5 new · 4 shortlisted · 1 left out (Kiln Ceramics — applied {day(8)}).
    Target: 0/2 · shortlist 4 of 4

    | # | Status | Role | Company | Comp | Score | Apply | Status detail | CV |
    |---|---|---|---|---|---|---|---|---|
    | 1 | 🟡 filled, awaiting submit | [Product Advisor (Robotics)](https://jobs.example.com/tidewater-marine/product-advisor) | Tidewater Marine | USD 4,500/mo | 76 | ✅ direct form (ashby) | 🟡 **Filled, awaiting your approval** — 9 fields verified in the form; the submit is the irreversible step and your level is supervised. | [CV]({tide_cv}) |
    | 2 | ⬜ not started | [Fractional Head of Product](https://jobs.example.com/saltbox-foods/fractional-head-of-product) | Saltbox Foods | USD 5,000/mo | 73 | ✅ direct form (greenhouse) | ⬜ Food manufacturing; a known buyer — next in line. | — |
    | 3 | ⬜ not started | [VP Product](https://jobs.example.com/alder-health/vp-product) | Alder Health | USD 260k | 69 | ✅ direct form (lever) | ⬜ Medical devices — adjacent; below the apply floor. | — |
    | 4 | ❌ disqualified | [Head of Product, Autonomy](https://jobs.example.com/meridian-labs/head-of-product) | Meridian Labs | USD 240k | — | ✅ direct form (greenhouse) | ❌ Former employer; must be based in London full-time. | — |

    > **Legend:** ✅ applied · 🟡 filled, awaiting submit · ⬜ not started · ⛔ skipped ·
    > ❌ disqualified · 🚫 excluded by criteria · 🔵 replied · 🎯 interview

    ## Application log
    | When | Company | Role | Outcome |
    |---|---|---|---|
    | {day(1)} | Tidewater Marine | Product Advisor (Robotics) | 🟡 filled — awaiting your approval to submit |
    """)
    # the scout's own state: what it has seen, and when it last ran
    seen = [{"title": "Fractional Head of Product", "company": "Kiln Ceramics", "url": JOHN_APPS[1]["url"], "score": 78},
            {"title": "Product Advisor, Automation", "company": "Foundry Metals", "url": "https://jobs.example.com/foundry-metals/product-advisor", "score": 71},
            {"title": "Head of Product", "company": "Beacon Rail", "url": "https://jobs.example.com/beacon-rail/head-of-product", "score": 70},
            {"title": "Fractional CPO", "company": "Pallas Insurance", "url": "https://jobs.example.com/pallas-insurance/fractional-cpo", "score": 68},
            {"title": "VP Product, Fleet", "company": "Verge Freight", "url": "https://jobs.example.com/verge-freight/vp-product-fleet", "score": 74},
            {"title": "Product Advisor (Robotics)", "company": "Tidewater Marine", "url": JOHN_APPS[2]["url"], "score": 76},
            {"title": "Fractional Head of Product", "company": "Saltbox Foods", "url": "https://jobs.example.com/saltbox-foods/fractional-head-of-product", "score": 73},
            {"title": "VP Product", "company": "Alder Health", "url": "https://jobs.example.com/alder-health/vp-product", "score": 69}]
    r = subprocess.run([PY, str(JOBS / "scout_state.py"), "add-seen"], cwd=str(brain), input=json.dumps(seen),
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("scout_state add-seen failed: " + r.stderr[-500:])
    (state / "last-run.txt").write_text(day(1), encoding="utf-8")
    sh([PY, JOBS / "render_brain.py", "--quiet"], brain)
    print("  jobs: 2 shortlists · ledger · 45-jobs rendered")


# ======================================================================== JOHN — Travel Agent
def john_travel(brain):
    pd = brain / "47-travel" / "profile"
    write(pd / "traveler.md", f"""
    ---
    type: travel-profile
    title: Traveller
    tags: [travel, profile]
    owner: John Carter
    updated: {day(6)}
    home_airports: [SFO, OAK]
    citizenships: [US]
    visa_ok: [GB, PT, JP, KR]
    ---

    # Traveller

    ## Home
    - Home city: San Francisco
    - Home airports (first = preferred): see `home_airports` above
    - Will also fly from: SJC (an hour away, only when much cheaper)

    ## Citizenships and entry
    - Citizenships: see `citizenships` above
    - `visa_ok`: confirmed visa-free entry on a US passport for short stays.

    ## Who travels
    - Usually: alone, sometimes with a partner
    - Companions: partner (no children)

    ## Flying
    - Cabin: economy on anything under 6 hours, premium economy beyond
    - Seat: window
    - Red-eyes: avoid
    - Loyalty programmes: one airline programme (number in `booking-answers.md` only if ever needed)

    ## Needs
    - Mobility / access needs: none
    - Dietary needs: none — but coffee matters more than dinner
    """)
    write(pd / "travel-criteria.md", f"""
    ---
    type: travel-profile
    title: Travel criteria
    tags: [travel, profile]
    owner: John Carter
    updated: {day(6)}
    ---

    # Travel criteria

    ## Trips
    - Typical length (nights): 4 to 6
    - Seasons / months: spring and autumn; avoid August
    - Climate: mild
    - Pace: balanced (4 things a day), one slow morning per trip

    ## Flights
    - Longest flight you will take: 12 hours
    - Longest total journey: 18 hours
    - Layover tolerance: one stop
    - **Stopover nights:** yes, gladly — a night in a connecting city beats a six-hour wait

    ## Avoid
    - Resorts, buffets, anything that needs a rental car in a city centre

    ## Budget bands
    - Per trip (total, USD): 3,500
    - Per night of stay: 180
    - Per day for food and activities: 90
    """)
    write(pd / "booking-answers.md", f"""
    ---
    type: travel-profile
    title: Booking answers
    tags: [travel, profile, answers]
    owner: John Carter
    updated: {day(6)}
    ---

    # Booking answers

    ## 0. Autonomy

    ```
    level: research            # research | supervised | autonomous
    max-bookings-per-run: 3
    max-spend-per-run: 0
    ```

    - **`research`** — plans, prices and pre-filled links. It never opens a checkout. **This is the
      only level with any effect in this version: booking is not built yet.**

    ## 1. Names
    - Full name exactly as on the passport: John Carter

    ## 2. Opt-in only
    - Date of birth: (not provided)
    - Passport expiry: (not provided)

    ## 3. Programmes and preferences
    - Travel insurance: I buy my own
    - Billing country: US
    """)
    write(pd / "providers.md", f"""
    ---
    type: travel-profile
    title: Providers
    tags: [travel, profile]
    owner: John Carter
    updated: {day(6)}
    ---

    # Providers

    - Currency: USD
    - Flights — market shape first, then carriers directly: Google Flights, then the airline's own site
    - Stays: Booking.com, then the hotel's own site
    - Ground: national rail operators first; a hire car only outside cities
    - Food: Google Maps — his own ratings first
    - Never use: sites that need an account to show a price
    """)
    sh([PY, TRAVEL / "taste.py", "--owner", "John Carter", "--out", pd / "taste.md"], brain)
    # confirm the taste file (the user did, in the story)
    t = (pd / "taste.md").read_text(encoding="utf-8").replace("status: candidate", "status: confirmed", 1)
    (pd / "taste.md").write_text(t, encoding="utf-8")
    sh([PY, TRAVEL / "scout.py", "--top", "6"], brain)
    # the trip: Lisbon in November — the pins he saved in 2024 and never used
    env = {"TRAVEL_HOME": str(brain / ".plugins" / "travel-planner")}
    tid = "lisbon-2026-11"
    sh([PY, TRAVEL / "itinerary.py", "new", "--id", tid, "--title", "Lisbon — November", "--earliest", "2026-11-12",
        "--latest", "2026-11-17", "--nights", "5", "--currency", "USD"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "add-stop", tid, "--place", "Lisbon", "--country", "PT", "--arrive", "2026-11-12",
        "--nights", "4", "--why", "8 saved places never visited; Web Summit week was the last time"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "add-stop", tid, "--place", "Sintra", "--country", "PT", "--role", "daytrip",
        "--arrive", "2026-11-15", "--nights", "0", "--lat", "38.7876", "--lng", "-9.3906",
        "--why", "the ridge trail he saved"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "brain-pois", tid, "--stop", "s1", "--radius-km", "12"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "add-poi", tid, "--stop", "s2", "--name", "Sintra Ridge Trail"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "plan-days", tid], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "set-stay", tid, "--stop", "s1", "--name", "Alfama guesthouse (candidate)",
        "--url", "https://stays.example.com/alfama-guesthouse", "--price", "164", "--quoted-at", D(2, "09:14"),
        "--status", "candidate", "--source", "stays.example.com", "--lat", "38.7119", "--lng", "-9.1302"], brain, env)
    sh([PY, TRAVEL / "itinerary.py", "activate", tid], brain, env)
    out = sh([PY, TRAVEL / "itinerary.py", "validate", tid], brain, env)
    sh([PY, TRAVEL / "render_brain.py", "--quiet"], brain)
    print(f"  travel: profile (5 files) · trip ideas · {tid} ({out.strip()}) · 47-travel rendered")


# ======================================================================== JOHN — Harness + memory
def john_harness(brain):
    b = str(brain)
    harness(brain, D(12, "18:00"), "seed", "--from", PLUG / "job-search" / "harness", "--agent", "job-search")
    harness(brain, D(6, "18:30"), "seed", "--from", PLUG / "travel-planner" / "harness", "--agent", "travel-planner")
    harness(brain, D(12, "18:01"), "set", "Get hired", "by", "2026-11-30")
    harness(brain, D(12, "18:02"), "set", "Daily job scout", "enabled", "true")
    harness(brain, D(6, "18:31"), "set", "Trip ideas from my places", "enabled", "true")
    harness(brain, D(6, "18:32"), "set", "Plan my next trip", "by", "2026-11-10")
    harness(brain, D(11, "09:00"), "routine-new", "--agent", "brain", "--title", "Monday reconnect",
            "--schedule", "MON 09:00", "--max-minutes", "10", "--notify", "news", "--enabled",
            "--body", "Every Monday, read the people layer and the dormant-strong-ties list in "
                      "90-synthesis/graph-insights.md, and suggest three people worth a message this week — "
                      "someone whose relationship has gone quiet, someone who changed company, someone close to "
                      "a goal I am working on. Cite the note behind each name. Suggest, never send.")
    harness(brain, D(11, "09:01"), "set", "Monday reconnect", "status", "validated")

    # ---- the runs, oldest first ------------------------------------------------------------
    # 1  first scout run, scheduled: six roles, one application sent (verified by its note)
    run(brain, "job-search", D(8, "07:00"), "done", [
        "Read the last report — none yet; first run",
        "Read profile/search-criteria.md and profile/scoring.md",
        "Swept 31 open ATS boards (14 days back): 61 postings, 9 new",
        "Screened knock-outs: 1 excluded (equity only), 1 account wall",
        "Scored 7 candidates against the rubric; 6 clear the floor",
        "Tailored the CV for Kiln Ceramics (lint: cv ✓ answers ✓ review ✓)",
        "Asked: Submit the Kiln Ceramics application? → approved",
        "Submitted through the employer's form; confirmation page reached",
        "Rendered the shortlist and the dashboard into 45-jobs",
    ], routine="Daily job scout", trigger="schedule", wrote=[
        f"45-jobs/reports/Shortlist {day(8)}.md", "45-jobs/Job Dashboard.md",
        f"45-jobs/applications/{day(8)}/kiln-ceramics-fractional-head-of-product/Kiln Ceramics — Fractional Head of Product.md"],
        handoff={"done": [
            {"text": "Applied to Kiln Ceramics — Fractional Head of Product (score 78)",
             "evidence": f"`45-jobs/applications/{day(8)}/kiln-ceramics-fractional-head-of-product/Kiln Ceramics — Fractional Head of Product.md`"},
            {"text": f"Shortlist of 6 written", "evidence": f"`45-jobs/reports/Shortlist {day(8)}.md`"}],
            "not_done": ["Verge Freight — VP Product, Fleet: the form sits behind a Workday account; link handed back"],
            "next": ["Follow up Kiln Ceramics after 7 days if no reply", "Foundry Metals is 500 under the floor — your call"],
            "needs_you": [], "news": True},
        asks=[{"question": "Submit the Kiln Ceramics application? This sends it in your name and cannot be undone.",
               "answered": True, "answer": "Submit it"}], minutes=14)
    # 2  a chat: he recorded the Analytical Engines interview (the goal moves to 1 of 3)
    run(brain, "job-search", D(4, "17:40"), "done", [
        "Recalled memory for job-search (3 items)",
        "Read the pasted reply from Analytical Engines",
        "learn.py set-result analytical-engines-vp-product → interview",
        "Prepared interview notes from fit.md and stories S1, S3, S4",
        "Saved an outcome memory: Analytical Engines led to an interview",
    ], trigger="chat", title="Jobs Agent chat",
        wrote=[f"45-jobs/applications/{day(15)}/analytical-engines-vp-product/Analytical Engines — VP Product.md"],
        handoff={"done": [{"text": "Recorded the interview invitation from Analytical Engines",
                           "evidence": f"`45-jobs/applications/{day(15)}/analytical-engines-vp-product/Analytical Engines — VP Product.md`"}],
                 "not_done": [], "next": ["Interview prep the evening before — ask for it"], "needs_you": [], "news": True},
        minutes=6)
    # 3  Monday reconnect (brain routine): three names, quiet work, news
    run(brain, "brain", D(5, "09:00"), "done", [
        "Read 90-synthesis/graph-insights.md (dormant strong ties)",
        "Read 10-people for last_contact older than 400 days with strength ≥ 3",
        "Chose three: Priya Nair, Alan Turing, Ada Lovelace — reasons in the report",
    ], routine="Monday reconnect", trigger="schedule",
        handoff={"done": [{"text": "Three people worth a message this week: Priya Nair (dormant, the only investor), "
                                   "Alan Turing (warm, Meridian Labs), Ada Lovelace (founder peer)",
                           "evidence": "`10-people/Priya Nair.md` `10-people/Alan Turing.md` `10-people/Ada Lovelace.md`"}],
                 "not_done": [], "next": ["Ask Grace Hopper for the Northwind introduction — she bridges both"],
                 "needs_you": [], "news": True}, minutes=4)
    # 4  a quiet scheduled run: nothing new — Activity only, no Inbox item
    run(brain, "job-search", D(3, "07:00"), "skipped", [
        "Read the last report", "Swept 31 boards: 0 new postings since the last run",
    ], routine="Daily job scout", trigger="schedule",
        handoff={"done": [], "not_done": [], "next": ["Sweep again tomorrow"], "needs_you": [], "news": False}, minutes=3)
    # 5  Trip ideas (monthly, 1st): three ideas from his own places
    run(brain, "travel-planner", D(2, "09:00"), "done", [
        "Read 85-places: 138 places, 25 named pins in 6 cities",
        "scout.py: Lisbon (8 saved, never visited), Tokyo (6 saved + a ★5 pour-over bar), Seoul (2 saved)",
        "Rendered Trip Ideas.md and the Suggestions layer on the Map",
    ], routine="Trip ideas from my places", trigger="schedule", wrote=["47-travel/Trip Ideas.md", "47-travel/Suggestions.geojson"],
        handoff={"done": [{"text": "Three trip ideas, each citing the notes behind it", "evidence": "`47-travel/Trip Ideas.md`"}],
                 "not_done": [], "next": ["Say 'plan Lisbon' to turn the strongest idea into an itinerary on the map"],
                 "needs_you": [], "news": True}, minutes=2)
    # 6  a scheduled run that FAILED mid-way (the board timed out; nothing was sent)
    run(brain, "job-search", D(2, "07:00"), "failed", [
        "Read the last report", "Swept 31 boards: 3 new postings",
        "Fetching the Saltbox Foods posting… timed out three times (the board returned 503)",
    ], routine="Daily job scout", trigger="schedule", stop_reason="The Saltbox Foods board returned 503 three times; stopped before scoring so nothing half-done was written.",
        handoff={"done": [], "not_done": ["Score and tailor for the 3 new postings"],
                 "next": ["Re-run the sweep; the board was down, not the pipeline"], "needs_you": [], "news": True}, minutes=5)
    # 7  yesterday's run is PARKED on the irreversible step — the Inbox's "needs you"
    run(brain, "job-search", D(1, "07:00"), "awaiting", [
        "Read the last report (failed run — re-sweeping)",
        "Swept 31 boards: 5 new postings, 4 shortlisted, 1 already applied (Kiln Ceramics)",
        "Tailored the CV for Tidewater Marine (lint: cv ✓ answers ✓ review ✓)",
        "Filled 9 fields in the Ashby form and verified each in the page",
        "Asked: Submit the Tidewater Marine application? — waiting for you",
    ], routine="Daily job scout", trigger="schedule",
        wrote=[f"45-jobs/reports/Shortlist {day(1)}.md",
               f"45-jobs/applications/{day(1)}/tidewater-marine-product-advisor-robotics/Tidewater Marine — Product Advisor (Robotics).md"],
        handoff={"done": [{"text": "Shortlist of 4 written", "evidence": f"`45-jobs/reports/Shortlist {day(1)}.md`"},
                          {"text": "Tidewater Marine application filled and verified, not submitted",
                           "evidence": f"`45-jobs/applications/{day(1)}/tidewater-marine-product-advisor-robotics/Tidewater Marine — Product Advisor (Robotics).md`"}],
                 "not_done": ["Saltbox Foods — Fractional Head of Product (next in line)"],
                 "next": ["Approve or deny the Tidewater Marine submit; then Saltbox Foods"],
                 "needs_you": [], "news": True},
        asks=[{"question": "Submit the Tidewater Marine application? USD 4,500 a month, 2 days a week, remote. "
                           "This sends it in your name and cannot be undone.", "answered": False}], minutes=16)
    # 8  an interrupted chat (the app quit mid-plan) — Activity + Inbox "interrupted"
    run(brain, "travel-planner", D(1, "21:10"), "interrupted", [
        "Recalled memory for travel-planner (2 items)",
        "Read Trip Ideas.md and the Lisbon pins",
        "itinerary.py new lisbon-2026-11 — 2 stops, 9 places from your brain",
        "Shopping stays around Alfama…",
    ], trigger="chat", title="Travel Agent chat", wrote=["47-travel/trips/lisbon-2026-11/itinerary.json"],
        handoff={"done": [{"text": "Lisbon — November drafted on the map (2 stops, 9 of your places)",
                           "evidence": "`47-travel/trips/lisbon-2026-11/itinerary.json`"}],
                 "not_done": ["Stays: one candidate priced, two more to compare", "Flights not shopped yet"],
                 "next": ["Resume the stay search — nothing is booked"], "needs_you": [], "news": True}, minutes=7)
    # the scheduler's bookkeeping: the slots that fired
    for slot, status in ((D(8), "done"), (D(3), "skipped"), (D(2), "failed"), (D(1), "awaiting")):
        harness(brain, slot, "fired", "Daily job scout", "--slot", slot, "--status", status)
    harness(brain, D(5, "09:00"), "fired", "Monday reconnect", "--slot", D(5, "09:00"), "--status", "done")
    harness(brain, D(2, "09:00"), "fired", "Trip ideas from my places", "--slot", D(2, "09:00"), "--status", "done")
    # inbox: he has read the first report
    inbox = harness(brain, None, "inbox", as_json=True)
    for it in inbox:
        if it["kind"] == "report" and day(8) in str(it.get("title", "")):
            harness(brain, None, "inbox", "--read", it["id"])
    print("  harness: 2 goals · 7 routines (2 agent + 1 brain on; 4 drafts from analyze) · 8 runs")

    # ---- memory: review-first, with one inference waiting -----------------------------------
    mem = [PY, ENGINE / "memory.py", "--brain", b]
    sh(mem + ["policy", "review"], brain)
    sh(mem + ["observe", "--scope", "job-search", "--kind", "preference", "--source", "user",
              "--text", "Fractional roles only up to 2 days a week; Acme stays the day job.", "--tags", "criteria,scoring"], brain)
    sh(mem + ["observe", "--scope", "job-search", "--kind", "rule", "--source", "user",
              "--text", "Never apply to a former employer (Meridian Labs, Loopr Logistics).", "--tags", "criteria"], brain)
    sh(mem + ["observe", "--scope", "job-search", "--kind", "lesson", "--source", "outcome",
              "--text", "Analytical Engines (VP Product) led to an interview — product-leadership lane, score 84, greenhouse.",
              "--tags", "scoring,sourcing", "--evidence", "set-result analytical-engines-vp-product|interview"], brain)
    sh(mem + ["observe", "--scope", "job-search", "--kind", "lesson", "--source", "agent",
              "--text", "Postings that name the factory floor in the first paragraph score 10+ higher on fit than ones that lead with the stack.",
              "--tags", "scoring"], brain)
    sh(mem + ["observe", "--scope", "travel-planner", "--kind", "preference", "--source", "user",
              "--text", "Window seat, no red-eyes, and a stopover night beats a long layover.", "--tags", "flights"], brain)
    sh(mem + ["observe", "--scope", "travel-planner", "--kind", "preference", "--source", "user",
              "--text", "Coffee first: plan the morning around a third-wave café he has saved.", "--tags", "taste,dining"], brain)
    sh(mem + ["observe", "--scope", "brain", "--kind", "fact", "--source", "user",
              "--text", "Grace Hopper is the bridge to Northwind Capital — ask her before contacting Priya Nair directly.", "--tags", "network"], brain)
    sh(mem + ["render"], brain)
    print("  memory: review-first · 6 active · 1 inferred item pending review")


# ======================================================================== ACME — Fundraising Agent
ACME_TARGETS = [
    dict(key="northwind-capital", name="Northwind Capital", kind="fund", url="https://northwind-capital.example",
         tier=4, fit=86, why="Priya Nair sits on Acme's board; the warm path is already open.",
         people=["Priya Nair"], claims={"thesis": ("Industrial automation and robotics, Series Seed to A", "✅"),
                                        "cheque": ("USD 500K to 2M", "✅"), "geography": ("US and Europe", "✅")}),
    dict(key="ironwood-ventures", name="Ironwood Ventures", kind="fund", url="https://ironwood-ventures.example",
         tier=2, fit=78, why="Exact thesis — hardware-enabled B2B; cold path through the published form.",
         people=["a partner (robotics)"], claims={"thesis": ("Hardware-enabled B2B, seed", "✅"), "cheque": ("USD 1M to 3M", "✅"),
                                                  "geography": ("US", "✅")}),
    dict(key="foundry-robotics-accelerator", name="Foundry Robotics Accelerator", kind="program",
         url="https://foundry-accelerator.example", tier=1, fit=74,
         why="Dated cohort door; USD 250K for 7% is a net cheque above the floor.",
         claims={"deadline": ("2026-10-20", "✅"), "cheque": ("USD 250K", "✅"), "cohort": ("Winter 2027", "✅"),
                 "geography": ("Global, remote-friendly", "✅")}),
    dict(key="beacon-industrial-fund", name="Beacon Industrial Fund", kind="fund", url="https://beacon-industrial.example",
         tier=2, fit=70, why="Manufacturing-tech thesis; no partner named yet.",
         claims={"thesis": ("Manufacturing technology", "3P"), "cheque": ("USD 750K to 2M", "3P"), "geography": ("US", "3P")}),
    dict(key="harbour-angels", name="Harbour Angels", kind="syndicate", url="https://harbour-angels.example",
         tier=3, fit=64, why="Home turf — the SF hardware angel syndicate; small cheques, fast decisions.",
         claims={"cheque": ("USD 150K to 400K", "✅"), "geography": ("San Francisco Bay Area", "✅")}),
    dict(key="pallas-manufacturing-grants", name="Pallas Manufacturing Grants", kind="grant",
         url="https://pallas-grants.example", tier=1, fit=61, why="Non-dilutive; a dated window in November.",
         claims={"deadline": ("2026-11-05", "✅"), "cheque": ("USD 200K", "✅"), "geography": ("US", "✅")}),
    # the two the filter chain removes
    dict(key="quarry-growth-partners", name="Quarry Growth Partners", kind="fund", url="https://quarry-growth.example",
         tier=None, fit=None, why="Growth stage — minimum cheque USD 10M; wrong round.",
         claims={"cheque": ("USD 10M and up, Series B+", "✅"), "thesis": ("Growth-stage industrials", "✅")}),
    dict(key="lantern-chain-fund", name="Lantern Chain Fund", kind="fund", url="https://lantern-chain.example",
         tier=None, fit=None, why="Crypto / web3 thesis — a hard exclusion.",
         claims={"thesis": ("Web3 infrastructure and tokenised supply chains", "📋")}),
]


def acme_fundraising(brain):
    pd = brain / "46-fundraising" / "profile"
    write(pd / "round.md", f"""
    ---
    type: fundraising-profile
    title: Round
    ask: 1500000
    currency: USD
    instrument: SAFE
    min_net_cash: 150000
    geography_ok: [us, europe, global]
    relocation: no
    entity_now: us-delaware
    entities_ok: [us-delaware]
    cofounder: closed
    exclusions: [crypto]
    thesis_keywords: [robotics, industrial automation, manufacturing, hardware, b2b, fleet software]
    off_thesis: [consumer, crypto, biotech, web3]
    filter_order: [floor, geo, thesis, access, entity, exclusions]
    max_research_agents: 3
    followup_days: 7
    ---

    # The round

    - Acme Robotics is raising a USD 1.5M seed on a SAFE; the lead writes at least the minimum above.
    - Delaware C-corp already; no relocation — the team and the customers are in San Francisco.
    - Decisions still open: the valuation cap (the plan lists it as a founder decision).
    """)
    write(pd / "company.md", f"""
    ---
    type: fundraising-profile
    title: Company
    ---

    # Acme Robotics

    ## One line
    Collaborative robots and the fleet software around them, for small manufacturers who could never
    afford an integration project.

    ## Product truth (shipped, checkable)
    - Cobot V2 shipping since 2025; 240 robots in the field.
    - Install time cut from 3 weeks to 4 days (the site checklist + in-software calibration).
    - First safety-certified release reviewed by TUV.

    ## Traction
    - 12 paying customers in 3 countries; 2 renewals; 110 opportunities in the pipeline.
    - Bootstrapped on revenue. 0 raised.

    ## Market (with sources)
    - Figures only with a link; the plan will not repeat an unsourced market size.

    ## Do not claim
    - recurring revenue figures — not in the data room yet
    - partnership — Ironwood Cloud is a vendor, not a partner
    - profitability — bootstrapped is not profitable
    """)
    write(pd / "founder.md", f"""
    ---
    type: fundraising-profile
    title: Founder
    ---

    # Founder

    - Name: John Carter · role: Founder & CEO · full-time
    - Previously: Director of Product at Meridian Labs (autonomy platform); Head of Product at Loopr Logistics
    - Education: MSc Robotics, Bletchley Institute
    - Links: https://www.linkedin.com/in/johncarter
    - References (ask before listing): Grace Hopper (VP Engineering); a customer plant manager
    """)
    write(pd / "answers.md", f"""
    ---
    type: fundraising-profile
    title: Settled answers
    level: supervised
    max_submits_per_run: 3
    ---

    # §0 Autonomy

    - `supervised` — three gates: pick the targets, approve the answers, submit.

    # §1 Settled answers (reused on every form)

    | Question | Answer |
    |---|---|
    | Company name | Acme Robotics |
    | Website | https://acme-robotics.example |
    | Location (company) | San Francisco, US |
    | Founders full-time? | Yes |
    | Incorporated? | Yes — Delaware C-corp |
    | Raised so far | None |
    | Founder video | (record per program — never reuse across different briefs) |
    | Demo / product link | https://acme-robotics.example/demo |
    """)
    write(pd / "stories.md", f"""
    ---
    type: fundraising-profile
    title: Stories
    ---

    ## Origin — why this company
    Running product at Meridian Labs, every small manufacturer we met wanted the robot and could not
    afford the integration project around it. Acme is the robot with the integration built in.

    ## Why now
    Cobot V2 cut install from weeks to days; the small-manufacturer segment is finally serviceable.

    ## Why you
    Shipped two industrial platforms before; sold and installed the first twelve Acme lines personally.

    ## The hardest thing so far
    Turning down the largest prospect's custom gripper line to protect the standard kit.

    ## Unfair advantage
    The install checklist and in-software calibration — twelve floors of lessons nobody else has yet.
    """)
    env = {"FUNDRAISE_HOME": str(brain / ".plugins" / "fundraising")}
    L = [PY, FUND / "ledger.py"]
    for t in ACME_TARGETS:
        claims = {f: {"v": v, "stamp": st, "src": t["url"], "at": day(10)} for f, (v, st) in t["claims"].items()}
        data = {"key": t["key"], "name": t["name"], "kind": t["kind"], "url": t["url"], "why": t["why"],
                "claims": claims, "people": t.get("people", []), "origin": ["founder list"]}
        sh(L + ["upsert", "--json", json.dumps(data)], brain, env)
        if t["tier"]:
            sh(L + ["set-tier", t["key"], "--tier", str(t["tier"]), "--fit", str(t["fit"]), "--why", t["why"]], brain, env)
    # the filter chain removes two (floor / exclusions), as the plan says
    sh(L + ["rescreen"], brain, env)
    # dates: the ledger stamps TODAY — drive it through the module so the story is a fortnight old
    def led(code, when):
        pyc(f"""
            import datetime, argparse, ledger as L
            L.TODAY = datetime.date.fromisoformat({when!r})
            {code}
        """, brain, [FUND])
    led('L.cmd_set_status(argparse.Namespace(key="foundry-robotics-accelerator", status="queued", by="agent", note="Tier 1 door", different=""))', day(9))
    led('L.cmd_log_app(argparse.Namespace(key="foundry-robotics-accelerator", day=' + repr(day(9)) + '))', day(9))
    led('L.cmd_set_status(argparse.Namespace(key="ironwood-ventures", status="queued", by="agent", note="Tier 2 cold path", different=""))', day(9))
    led('L.cmd_log_draft(argparse.Namespace(key="ironwood-ventures", path="46-fundraising/outreach/Ironwood Ventures — cold email.md", gmail_id=None, channel="email"))', day(7))
    led('L.cmd_set_status(argparse.Namespace(key="northwind-capital", status="queued", by="agent", note="warm intro via Grace Hopper", different=""))', day(12))
    led('L.cmd_log_draft(argparse.Namespace(key="northwind-capital", path="46-fundraising/outreach/Northwind Capital — intro request via Grace Hopper.md", gmail_id=None, channel="email"))', day(12))
    led('L.cmd_sent(argparse.Namespace(key="northwind-capital", days=7, note="John sent the intro request himself"))', day(11))
    led('L.cmd_log_outcome(argparse.Namespace(key="northwind-capital", result="replied", note="Priya replied the same day and proposed a call."))', day(8))
    led('L.cmd_log_outcome(argparse.Namespace(key="northwind-capital", result="meeting", note="45 minutes with Priya Nair; she asked for the data room and the cap."))', day(3))
    led('L.cmd_next(argparse.Namespace(key="northwind-capital", action="send the data-room link and the cap once decided", due=' + repr(day(-4)) + '))', day(3))
    led('L.cmd_set_status(argparse.Namespace(key="harbour-angels", status="queued", by="agent", note="Tier 3", different=""))', day(5))
    led('L.cmd_next(argparse.Namespace(key="foundry-robotics-accelerator", action="submit the application before the window closes", due="2026-10-20"))', day(9))
    # the two drafts (never sent by the agent) and the application folder's draft answers
    out = brain / "46-fundraising" / "outreach"
    write(out / "Northwind Capital — intro request via Grace Hopper.md", f"""
    ---
    type: outreach-draft
    title: Northwind Capital — intro request via Grace Hopper
    tags: [fundraising, outreach, draft]
    target: "[[Northwind Capital (target)]]"
    channel: email
    status: sent-by-founder
    drafted: {day(12)}
    ---

    # Intro request — to Grace Hopper, for Priya Nair

    > Draft written by the Fundraising Agent on {day(12)}. **Never sent by the agent** — John sent it
    > himself on {day(11)} and recorded it with `ledger.py sent`.

    Grace — Acme is opening a USD 1.5M seed. Priya Nair at Northwind Capital sits on our board but we have
    not spoken in two years, and you know her better than I do. Would you introduce us? Two lines on what
    changed since she last looked: Cobot V2 is live at 12 customers, and installs went from three weeks
    to four days. Happy to send the one-pager first if that is easier.
    """)
    write(out / "Ironwood Ventures — cold email.md", f"""
    ---
    type: outreach-draft
    title: Ironwood Ventures — cold email
    tags: [fundraising, outreach, draft]
    target: "[[Ironwood Ventures (target)]]"
    channel: email
    status: draft
    drafted: {day(7)}
    ---

    # Cold email — Ironwood Ventures

    > Draft only. The agent never sends; mark it `sent` when you do.

    Subject: Robots small manufacturers can actually install — Acme Robotics seed

    Your note on hardware-enabled B2B said the install is the product. That is the whole of Acme: 12
    small manufacturers run 240 of our robots, and the install takes four days because the calibration
    moved into the fleet software. We are raising USD 1.5M on a SAFE. Would a 20-minute call fit next week?
    """)
    app = brain / "46-fundraising" / "applications" / day(9) / "foundry-robotics-accelerator"
    write(app / "answers.md", f"""
    # Foundry Robotics Accelerator — drafted answers ({day(9)})

    | Field | Answer | Source |
    |---|---|---|
    | What does the company do? | Collaborative robots and fleet software for small manufacturers. | company.md |
    | Traction | 12 paying customers in 3 countries; 240 robots; 2 renewals. | company.md |
    | Raised so far | None — bootstrapped on revenue. | company.md |
    | Why now | Cobot V2 cut install from 3 weeks to 4 days. | stories.md |
    | Founder video | (to record — never reused) | answers.md |

    Status: **drafted, not filed** — the submit is yours (level: supervised). Window closes 2026-10-20.
    """)
    # the Funding Plan — raise-plan's prose, in its fixed sections
    write(brain / "46-fundraising" / "Funding Plan.md", f"""
    ---
    type: fundraising-plan
    title: Funding Plan
    updated: {day(3)}
    targets: 8
    level: supervised
    tags: [fundraising, plan]
    ---

    # Funding Plan — Acme Robotics seed (USD 1.5M, SAFE)

    ## Stamps legend
    ✅ read on the target's own site, dated · 3P third-party only · 📋 desk-screened from a list · ⚠ unverified · ⏳ stale.
    This plan reads public pages and the founder's own lists; where those are silent it says ⚠ rather than guessing.

    ## The filter
    `floor → geo → thesis → access → entity → exclusions` (from `profile/round.md`). This run it removed 2 of 8:
    1 at **floor** (Quarry Growth Partners — USD 10M minimum), 1 at **exclusions** (Lantern Chain Fund — web3).

    ## §0 Ledger
    | Target | Filed / sent | Outcome | Next window |
    |---|---|---|---|
    | [[Northwind Capital (target)]] | intro request sent by John {day(11)} | **meeting {day(3)}** — asked for the data room and the cap | send both once the cap is decided |
    | [[Ironwood Ventures (target)]] | draft ready {day(7)} | not sent yet | your call |
    | [[Foundry Robotics Accelerator (target)]] | answers drafted {day(9)} | not filed | closes 2026-10-20 ✅ |

    ## §1 Timeline
    | Date | Days left | Action | Net cash | Stamp |
    |---|---|---|---|---|
    | 2026-10-20 | 17 | Foundry Robotics Accelerator — submit | USD 250K | ✅ |
    | 2026-11-05 | 33 | Pallas Manufacturing Grants — window | USD 200K | ✅ |
    | rolling | — | Ironwood Ventures · Beacon Industrial Fund · Harbour Angels | USD 150K–3M | ✅ / 3P |

    **Branches.** If Foundry accepts → the cohort starts in January and the round closes around it. If not
    by 2026-10-27 → Pallas and the Tier 2 cold path carry the timeline.

    ## §2 Tiers
    - **Tier 1 — dated cohort doors:** [[Foundry Robotics Accelerator (target)]] · [[Pallas Manufacturing Grants (target)]]
    - **Tier 2 — cold path, exact thesis:**

      | Target | Partner | Why this one | Cold path | Cheque | Stamp |
      |---|---|---|---|---|---|
      | [[Ironwood Ventures (target)]] | a partner (robotics) | hardware-enabled B2B is the thesis verbatim | published form | USD 1–3M | ✅ |
      | [[Beacon Industrial Fund (target)]] | — | manufacturing technology | website form | USD 750K–2M | 3P |
    - **Tier 3 — home turf:** [[Harbour Angels (target)]]
    - **Tier 4 — warm-intro builds:** [[Northwind Capital (target)]] (via Grace Hopper → Priya Nair — done)
    - **Don't bother:** Quarry Growth Partners (floor) · Lantern Chain Fund (exclusions)

    ## §3 Founder decisions
    1. **Valuation cap** — undecided in `round.md`. Recommendation: name a cap before the Northwind data-room
       send; a SAFE without a cap reads as not having thought about it. You decide.
    2. **Ironwood cold email** — draft ready since {day(7)}. Recommendation: send it after Northwind's
       second meeting is booked, so the first conversation sets the pace.

    ## §4 Screening tables
    **founder list (8):** survived 6 · conditional 0 · out 2 — floor: Quarry Growth Partners · exclusions: Lantern Chain Fund.

    ## §5 Partner track
    Design partners before corporate development: Verge Freight (third line in negotiation) and Saltbox Foods
    (retrofit kits) are the references a lead will call. No acquisition conversations before the round closes.

    ## §6 Corrections
    - `fundraising/Seed-Round-Narrative.md` in the docs store says "two renewals" — matches `company.md`. No contradictions found.

    ## This week, in order
    1. Decide the valuation cap — you (§3).
    2. Send Northwind the data-room link and the cap — you; record it with `ledger.py sent` — raise-outreach.
    3. Draft the Foundry Robotics Accelerator application for your approval — raise-apply.
    4. Re-verify Beacon Industrial Fund's cheque on its own site (3P → ✅) — raise-research.
    5. Decide whether the Ironwood email goes now — you.
    """)
    sh([PY, FUND / "render_brain.py", "--quiet"], brain, env)
    print("  fundraising: profile (5 files) · 8 targets (2 out) · 1 meeting · plan · 46-fundraising rendered")


def acme_harness(brain):
    b = str(brain)
    harness(brain, D(12, "10:00"), "seed", "--from", PLUG / "fundraising" / "harness", "--agent", "fundraising")
    harness(brain, D(12, "10:01"), "set", "Raise my round", "by", "2026-12-15")
    harness(brain, D(12, "10:02"), "set", "What's due in my raise", "enabled", "true")
    harness(brain, D(10, "10:00"), "routine-new", "--agent", "brain", "--title", "Who knows what — weekly digest",
            "--schedule", "FRI 16:00", "--max-minutes", "10", "--notify", "news", "--enabled",
            "--body", "Every Friday, read 95-goals/whoknows.md and the people layer's dept/ and channel/ tags, and "
                      "write a short digest: which teams gained or lost an owner this week, which channels have a "
                      "single active member, and who new joiners should ask about what. Cite the notes. Draft only.")
    harness(brain, D(10, "10:01"), "set", "Who knows what — weekly digest", "status", "validated")
    harness(brain, D(10, "10:02"), "set", "Draft handovers for single points of failure", "schedule", "MONTHLY 1 09:00")
    harness(brain, D(10, "10:03"), "set", "Draft handovers for single points of failure", "enabled", "true")
    harness(brain, D(10, "10:04"), "set", "Draft handovers for single points of failure", "status", "validated")

    run(brain, "fundraising", D(11, "11:20"), "done", [
        "Recalled memory for fundraising (0 items — first run)",
        "Read profile/round.md: 6 filters, floor USD 150K net",
        "Imported the founder's list: 8 targets",
        "Screened against the chain: 6 survived, 2 out (floor, exclusions)",
        "Verified the 6 survivors on their own sites: 5 ✅, 1 3P",
        "Drafted the intro request to Grace Hopper for Northwind Capital — handed over, not sent",
    ], trigger="chat", title="Fundraising Agent chat", wrote=["46-fundraising/Fundraising Dashboard.md",
                                                               "46-fundraising/outreach/Northwind Capital — intro request via Grace Hopper.md"],
        handoff={"done": [{"text": "8 targets screened, 6 survive the filter chain", "evidence": "`46-fundraising/Fundraising Dashboard.md`"},
                          {"text": "Intro request to Grace Hopper drafted (not sent)",
                           "evidence": "`46-fundraising/outreach/Northwind Capital — intro request via Grace Hopper.md`"}],
                 "not_done": ["Funding Plan — after the first replies"], "next": ["You send the intro request; mark it sent"],
                 "needs_you": [], "news": True}, minutes=18)
    run(brain, "fundraising", D(4, "08:00"), "done", [
        "Read the last report",
        "ledger.py due --days 14: 2 items — Foundry window (2026-10-20), Northwind follow-up",
        "Drafted the Foundry Robotics Accelerator answers from company.md and stories.md",
        "Linted the answers against the do-not-claim list: 0 red lints",
        "Wrote the Funding Plan (8 targets, 2 branches, 2 founder decisions)",
    ], routine="What's due in my raise", trigger="schedule",
        wrote=["46-fundraising/Funding Plan.md", f"46-fundraising/applications/{day(9)}/foundry-robotics-accelerator/answers.md"],
        handoff={"done": [{"text": "Funding Plan written", "evidence": "`46-fundraising/Funding Plan.md`"},
                          {"text": "Foundry Robotics Accelerator answers drafted, not filed",
                           "evidence": f"`46-fundraising/applications/{day(9)}/foundry-robotics-accelerator/answers.md`"}],
                 "not_done": ["Beacon Industrial Fund cheque is third-party only — re-verify on their site"],
                 "next": ["Approve the Foundry answers so the form can be filled", "Decide the valuation cap"],
                 "needs_you": ["Decide the valuation cap — Northwind asked for it after the meeting and the plan branches on it."],
                 "news": True}, minutes=12)
    run(brain, "fundraising", D(3, "15:05"), "done", [
        "Recalled memory for fundraising (2 items)",
        "ledger.py log-outcome northwind-capital meeting — 45 minutes with Priya Nair",
        "Goal check: Raise my round 1 of 5 investor meetings",
        "Saved an outcome memory: Northwind Capital answered meeting (fund, tier 4)",
    ], trigger="chat", title="Fundraising Agent chat",
        handoff={"done": [{"text": "Recorded the Northwind Capital meeting", "evidence": "`46-fundraising/targets/Northwind Capital (target).md`"}],
                 "not_done": [], "next": ["Send the data-room link once the cap is decided"], "needs_you": [], "news": True}, minutes=4)
    run(brain, "fundraising", D(2, "08:00"), "skipped", [
        "Read the last report", "ledger.py due --days 14: nothing newly due since yesterday",
    ], routine="What's due in my raise", trigger="schedule",
        handoff={"done": [], "not_done": [], "next": ["Check again tomorrow"], "needs_you": [], "news": False}, minutes=1)
    run(brain, "brain", D(1, "16:00"), "done", [
        "Read 95-goals/whoknows.md and the people layer's dept/ and channel/ tags",
        "Found 2 channels with a single active member (design-crit, ops-room)",
        "Drafted the digest",
    ], routine="Who knows what — weekly digest", trigger="schedule",
        handoff={"done": [{"text": "Weekly who-knows digest: 5 departments, 8 channels, 2 single-owner channels",
                           "evidence": "`95-goals/whoknows.md`"}],
                 "not_done": [], "next": ["Draft handovers for the two single-owner channels (the monthly routine does this)"],
                 "needs_you": [], "news": True}, minutes=3)
    run(brain, "brain", D(2, "09:00"), "preflight-failed", [], routine="Draft handovers for single points of failure",
        trigger="schedule", stop_reason="The AI sign-in had expired on this Mac, so the run never started and no usage was spent.",
        handoff={"done": [], "not_done": ["Draft handovers for the 2 single-owner channels"],
                 "next": ["Sign in again, then Run now"], "needs_you": ["Can't run — the AI is not signed in on this Mac."],
                 "news": True}, minutes=0)
    run(brain, "fundraising", D(1, "08:00"), "skipped", [
        "Read the last report", "ledger.py due --days 14: nothing newly due since yesterday",
    ], routine="What's due in my raise", trigger="schedule",
        handoff={"done": [], "not_done": [], "next": ["Check again Monday"], "needs_you": [], "news": False}, minutes=1)
    for slot, status in ((D(4, "08:00"), "done"), (D(2, "08:00"), "skipped"), (D(1, "08:00"), "skipped")):
        harness(brain, slot, "fired", "What's due in my raise", "--slot", slot, "--status", status)
    harness(brain, D(1, "16:00"), "fired", "Who knows what — weekly digest", "--slot", D(1, "16:00"), "--status", "done")
    harness(brain, D(2, "09:00"), "fired", "Draft handovers for single points of failure", "--slot", D(2, "09:00"), "--status", "preflight-failed")
    print("  harness: 1 goal · 7 routines (1 agent + 2 brain on; 2 drafts from analyze) · 7 runs")

    mem = [PY, ENGINE / "memory.py", "--brain", b]
    sh(mem + ["observe", "--scope", "fundraising", "--kind", "rule", "--source", "user",
              "--text", "Never quote a revenue figure; Acme is bootstrapped and pre-round.", "--tags", "outreach,claims"], brain)
    sh(mem + ["observe", "--scope", "fundraising", "--kind", "lesson", "--source", "outcome",
              "--text", "Northwind Capital answered meeting (fund, tier 4) — the warm path through Grace Hopper worked in one day.",
              "--tags", "targeting,outreach", "--evidence", "log-outcome northwind-capital|meeting"], brain)
    sh(mem + ["observe", "--scope", "brain", "--kind", "fact", "--source", "user",
              "--text", "Design-crit and ops-room each have a single active owner; handovers come first.", "--tags", "continuity"], brain)
    sh(mem + ["render"], brain)
    print("  memory: 3 active items (policy: auto)")


# ======================================================================== main
def main():
    global TODAY
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", required=True, help="dir holding personal/john-brain and company/acme-brain")
    ap.add_argument("--today", default=TODAY.isoformat())
    a = ap.parse_args()
    TODAY = dt.date.fromisoformat(a.today)
    root = pathlib.Path(a.vault).resolve()
    john = root / "personal" / "john-brain"
    acme = root / "company" / "acme-brain"
    for b in (john, acme):
        if not (b / "_STRUCTURE.md").is_file():
            raise SystemExit(f"not a built brain: {b}")
        if (b / "96-agents" / "Activity").is_dir():
            raise SystemExit(f"{b} already has Activity — seed a FRESH build, not twice")
    print(f"seeding agents into {root} (today = {TODAY})")
    print("john-brain")
    john_jobs_profile(john)
    john_jobs_ledger(john)
    john_travel(john)
    print("acme-brain")
    acme_fundraising(acme)
    # every note written so far predates the runs below, so the write-block check stays clean
    n = backdate(john) + backdate(acme)
    print(f"  backdated {n} files to {BACKDATE.date()} (staging only)")
    print("john-brain harness")
    john_harness(john)
    print("acme-brain harness")
    acme_harness(acme)
    for b in (john, acme):
        inbox = harness(b, None, "inbox", as_json=True)
        kinds = {}
        for it in inbox:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        goals = harness(b, None, "goal-progress", as_json=True)
        print(f"  {b.name}: inbox {kinds} · goals " + ", ".join(f"{g['goal']} {g['value']} of {g['target']} ({g['pace']})" for g in goals))
    n = scrub_build_paths(root)
    print(f"  scrubbed the build location from {n} files (the demo ships on a public site)")
    return 0


def scrub_build_paths(root):
    """The renderers stamp ABSOLUTE paths (their state root, the doc store's original folder)
    into reports, manifests and .claude/settings.json. The demo is served publicly, so rewrite
    this build's location to the neutral default workspace paths, then re-hash every manifest
    entry for a rewritten file (plain SHA-256 of the bytes) so --refresh doesn't read it as a
    user edit. Returns the number of files rewritten."""
    import hashlib
    vault = str(root).rstrip("/") + "/"
    data = str(root.parent / "data").rstrip("/") + "/"
    swaps = [(vault, "~/Documents/SecondBrainLink/vault/"), (data, "~/Documents/SecondBrainLink/data/")]
    changed = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in (".md", ".json", ".geojson", ".jsonl", ".canvas", ".txt", ".yml", ".yaml"):
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        u = t
        for a, b in swaps:
            u = u.replace(a, b)
        if u != t:
            p.write_text(u, encoding="utf-8")
            changed.append(p)
    if not changed:
        return 0
    digest = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
    for mp in root.rglob("*GENERATED*.json"):
        t = mp.read_text(encoding="utf-8")
        u = t
        for p, h in digest.items():
            for base in (mp.parent, mp.parent.parent, mp.parent.parent.parent, p.parent):
                try:
                    rel = str(p.relative_to(base))
                except ValueError:
                    continue
                key = '"' + rel + '": "'
                i = u.find(key)
                if i >= 0:
                    u = u[: i + len(key)] + h + u[i + len(key) + 64 :]
                    break
        if u != t:
            mp.write_text(u, encoding="utf-8")
    return len(changed)


if __name__ == "__main__":
    sys.exit(main())
