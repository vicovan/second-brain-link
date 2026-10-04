# Tailoring Playbook — how to turn a job description into a first-pick CV

Goal per application: be in the top handful out of 1,000+ applicants at BOTH
gates — (1) the ATS / AI screener that ranks by keyword and title match, and
(2) the human who reads the top 20 for six seconds each. Everything below
serves one of those two gates.

**Three things decide more than any wording, and they are settled before this playbook runs:**
the knock-out answers (`job-apply/scripts/knockout.py` — right to work, location, language, pay),
whether the job is winnable at all (`job-scout/references/scoring-rubric.md`, shortlist
likelihood), and the requirement table in `<app dir>/fit.md` (§1b). A perfect CV for a job the
screener auto-rejects on location is wasted work.

**The rules below are enforced, not advisory.** `scripts/lint_cv.py cv` fails the build on the
things a screener rejects fastest: roles out of date order, a "Why …" section, a sentence that
names the candidate's own gap, first person, banned phrases, negative-parallel cadence, too many
em-dashes or bold lead-ins, and — with `--profile` — any number, employer or title not in the
profile. The phrase lists live in that script, so this file and the gate cannot drift.

## 0. The truth boundary (read first)

You may freely change: emphasis, ordering, wording, which bullets appear,
which of the ALLOWED titles is used, how a role is framed, which contact set
is used, headline, summary, keyword density.
You may never change: employers, dates, degrees, numbers, or claim outcomes,
customers, revenue, certifications or titles not in profile/profile.md.
"Adjust job titles" means choosing the truthful label that mirrors the target
(e.g. Co-Founder & CTO → "CTO & Co-Founder"; Director of Product ↔ "Staff
Software Architect", where the profile lists both for that role; Founder & CEO →
"Founder, CEO & CTO"). It
never means inventing a title the company would not confirm.
If the JD needs a fact the master profile does not have, ask the user in one line
and continue with what is available; do not block the whole CV on it.

## 1. Intake — extract the target from the JD

Read the JD (and the company site if reachable) and write down, before
touching the CV:

1. Exact target title as written (e.g. "VP of Engineering, AI Platform").
2. Seniority band: IC-architect / Head-Director / VP / C-level / Founder-program.
3. Company type: startup (seed–B) / scale-up / enterprise / consultancy /
   VC-accelerator / public sector / defense.
4. Location & work mode: on-site city, hybrid, remote-EU, remote-global,
   remote-US-hours, GCC/MENA.
5. Must-have keywords: every noun phrase in "requirements" / "must have" /
   "you have" — copy them verbatim into a list (both acronym and long form:
   "CI/CD" and "Continuous Integration / Continuous Delivery").
6. Nice-to-have keywords: from "bonus", "preferred", "nice to have".
7. Domain signals: industry (fintech, health, retail, logistics, public sector…),
   stack (Python, TS, K8s…), scale words (multi-tenant, enterprise, global).
8. Culture / narrative signals: what they brag about (open source, speed,
   customer obsession, security, regulated, founder-led).
9. The three questions this employer is silently asking (e.g. "have they done
   this exact thing before?", "will they stay?", "can they hire in our region?").

Keep this as a short table at the top of your reasoning; every section of the
CV must answer something in it.

## 1b. The fit file — two passes, written before the CV (`<app dir>/fit.md`)

Rating requirements *after* reading the profile inflates the ones the candidate happens to meet.
So rate them first, blind:

**Pass 1 — from the JD alone.** One row per requirement: the requirement, the JD's own words
quoted verbatim, and an importance — `critical` (named as required, or the role's headline
purpose), `high`, `medium`, `low`. An importance that is inferred rather than stated is never
`critical`. Do not revise importance in pass 2.

**Pass 2 — against `profile/profile.md` only.** For each row: the evidence (role + fact), and a
status — `existing` (the profile names it), `supported` (the profile shows it in other words — may
be restated in the JD's words), or `gap` (no trace).

Then, in the same file:
- `## Keywords` — the 15–20 ATS terms, most important first, `;`-separated on one bullet line.
  `lint_cv.py --fit fit.md` checks them.
- `## Reviewer doubts` — the three things a hiring manager would question, each with the one fact
  that answers it (or `none — interview prep`).
- `## Gaps` — every `gap` row, for interview prep. **Gaps never go on the CV and never go into a
  free-text answer.**

The CV is built only from `existing` and `supported` rows. If a `critical` row is a `gap`, the job
should not have cleared the scout's shortlist-likelihood bar — say so rather than paper over it.

**Writing "used X" as "built X" is fabrication.** It is the most common one, because the tool name
really is in the profile. The verb must be the profile's verb.

## 2. Contact-set decision — pick exactly one

A CV shows **one** phone and **one** primary location. Two of either reads as indecision, and an
ATS will often index only the first.

Pick one set from `profile/profile.md` §1 by matching the employer's location and its
work-authorization need, in this order:

| Signal in the JD or the company | Choose |
|---|---|
| The role is in a country where the user already has the right to work | that country's set — say so explicitly ("citizen · no sponsorship required"), because it is the single strongest logistical signal on the page |
| The role is remote within a region the user can work in | the set inside that region |
| The role is remote-global with no region stated | the set with the widest work authorization, unless the company's customers are concentrated somewhere the user's other set serves better |
| The role is on-site in a country the user cannot work in without sponsorship | the user's home set, plus one line offering relocation and naming the sponsorship need — only if the profile says they want that. Otherwise skip the role |
| Accelerator, VC programme or investor audience | the set closest to the programme's home; if the programme is global, the profile may allow showing two cities on the location line — still one phone |

If the profile records a seasonal pattern (where the user physically is at different times of year),
match the phone to where they will be at the start date, and add a presence sentence for on-site and
hybrid roles.

**Never list two phone numbers. Never include a date of birth** unless the target market expects it
and the profile says so.

## 3. Title & headline mirroring — the three-rung ladder

**The problem this solves:** a recruiter scanning for "VP Engineering" will not pattern-match
"Co-Founder & CTO" in two seconds, and an ATS scoring on title similarity scores it lower. The CV
has to *look* like the role they are hiring for — without ever stating a title the user did not hold.

Work down this ladder and stop at the first rung that fits. **Never skip to inventing.**

### Rung 1 — Headline mirrors the target title verbatim (always do this)
Line 1 of the CV is the target title exactly as the JD writes it, plus **one** short
differentiator — a fact, not a list. This is the strongest single lever and it costs nothing in
accuracy, because a headline states what they are applying *as*, not a role they held.

| JD title | Headline |
|---|---|
| Chief Technology Officer | `Chief Technology Officer · three platforms taken from seed to Series B` |
| VP of Engineering | `VP of Engineering · grew teams from 9 to 23 across three time zones` |
| Principal AI Architect | `Principal AI Architect · LLM systems in regulated production` |
| Head of ML | `Head of ML · recommendation models serving 40M users` |
| Engineering Director | `Engineering Director · multi-team product organisations` |

**Rules the gate enforces:** the title comes first, nothing in front of it; ≤ 80 characters; no
second title (`VP Engineering / CTO`), no "-level" phrasing, no keyword list after the dot.

Also mirror the title **verbatim in the first sentence of the Professional Summary** — ATS parsers
weight the summary heavily, and a human reads it in the same glance.

### Rung 2 — Use an ALLOWED title variant for the role itself
Each role in `profile/profile.md` §4 carries a list of **allowed titles** — labels that are genuinely
accurate for that role, including ones the user actually used at the time. Pick the variant closest to
the target. Examples already sanctioned there:

- **Northwind Data** (the current role) → `Staff Software Architect` for architect/IC targets ·
  `Director of Product` for product-leadership targets, when the profile lists both as
  genuinely held. Never both on one CV.
- **Jane's own venture** → `Founder & CEO` · `Founder, CEO & CTO` · `Founder & CTO` — pick the one
  whose emphasis matches the target.
- **Meridian Labs** (an earlier scale-up) → `CTO` or `Chief Technology Officer` (spelled out reads
  more senior to some ATS).

If the target is "Head of Engineering" and the allowed list has "CTO", **use CTO** — do not
downgrade or invent. Seniority above the target is fine; a fabricated title is not.

### Rung 3 — Keep the real title, add a plain CONTEXT line
When no allowed variant matches the target vocabulary, leave the title truthful and add one italic
line directly under the role header that states the **reach in facts**: team size, managers,
reporting line, sites, what the role covered. The facts do the matching; the reader draws the
equivalence themselves.

```
Co-Founder & CTO · Northwind Data · Lisbon, Portugal              04/2022 – 12/2024
Led 14 engineers in two teams, reporting to the board; owned architecture, delivery and hiring.
```

More patterns:
- Target **Engineering Director**, role was CTO at a scale-up →
  *"Directed four engineering teams and their managers across two sites."*
- Target **Principal Architect**, role was Founder/CTO →
  *"Made every architecture decision on the platform, from data model to deployment."*
- Target **Head of AI**, role was Staff Software Architect →
  *"Set the AI technical direction and model roadmap for a platform team of eleven."*

**Never write the target's title or a level into this line** — not "scope equivalent to VP
Engineering", not "Principal-architect scope", not "VP-level ownership". A candidate describing the
level they want reads to a recruiter as tailoring, and to an AI screener as keyword stuffing.
`lint_cv.py` fails it.

### THE LINE — what must never happen
**Never write a title the user did not hold.** Not "VP Engineering" when the profile says CTO, not
"Head of ML" when the profile says Architect, not a seniority the profile does not record. Titles are the single most verifiable
thing on a CV — they are checked in references, on LinkedIn, and in background checks, and a
mismatch discovered later is far more damaging than a lower ATS score today.

The dividing line is simple:
- **Allowed:** a different accurate *label* for the same job (§4 allowed titles), a headline stating
  what they are applying as, and a truthful description of scope in the target's vocabulary.
- **Not allowed:** a title they never held, a company they did not hold it at, or a scope claim the
  bullets do not support.

If a target title genuinely cannot be reached from any rung, say so to the user in one line rather than
stretching. That is a signal the role may be a poor fit, which is useful information.

### Everything else stays as before
- For IC/architect targets, lead every bullet with what the user personally designed or coded, and put
  Technical Skills higher.
- For C-level targets, lead with scale, P&L-adjacent decisions, fundraising, board/investor work
  and hiring.
- For founder programmes / investors, use the programme structure (see `assets/example-cv.md`):
  problem, hard-to-replace, workflow owned, traction→growth, market & stage, then "why this founder".

## 3b. Rewriting the past roles for the target — descriptions, not just titles

A title gets past the first filter; the **bullets** decide whether a human keeps reading. Every role
on the CV must be rewritten for this specific target. Four moves, in order:

### Move 1 — Reframe the company descriptor
The `where` line under each role header describes what the company *was*. Point it at the target's
world. Same company, same truth, different emphasis:

| Company | For an AI/agents target | For a fintech target | For an enterprise/security target |
|---|---|---|---|
| **Northwind Data** | *ML-powered analytics platform* | *B2B SaaS with usage-based billing* | *multi-tenant enterprise SaaS platform* |
| **Meridian Labs** | *recommendation engine for retail* | *checkout and loyalty platform* | *high-availability retail platform* |
| **Acme Robotics** | *ML-driven fleet platform, API-first* | *orchestration and payments platform* | *enterprise integration platform* |
| **Globex** | *document-AI platform for logistics* | *invoice-automation platform* | *enterprise document-management vendor* |
| **Jane's own venture** | *open-source developer tooling* | *subscription analytics for small businesses* | *self-hosted analytics, SOC 2-ready* |

The point is the *shape*, not these companies: one row per employer on the CV, one column per kind
of target, and the same truthful descriptor pointed in a different direction each time. Build the
table from the user's own `profile.md` §4 before tailoring anything.

### Move 2 — Select which bullets appear at all
The bullet bank in §4 is a **superset**. A tailored CV picks 2–5 per recent role, 1–2 per older one,
and **drops the rest entirely**. A bullet that does not serve this target is costing space that a
relevant one needs. Ruthless selection beats comprehensive listing every time.

### Move 3 — Restate the SAME fact in the target's vocabulary
This is the highest-leverage move and it is entirely honest: identical fact, their words.

**Worked example — one fact from the profile, rewritten for five targets:**

| Target | How the bullet reads |
|---|---|
| VP Engineering | *"**Doubled the engineering organisation** across two sites while implementing scalable agile process."* |
| Engineering Director | *"**Directed** engineering across two sites, growing the org 2× and building the management layer beneath me."* |
| Chief Architect | *"**Established enterprise architecture standards** and a modern data stack, and managed a complete platform and API rebuild."* |
| CTO | *"Owned technology for the platform: full product rebuild, architecture standards, and an org doubled across two sites."* |
| Head of AI | *"Set technical direction and standards for a platform team, then grew it 2× — the org-building half of taking AI from pilot to product."* |

(One fact from Jane's profile — *"grew the team from 12 to 25 across two sites, 2022–2024"* —
pointed five different ways. Nothing was added; only the emphasis moved.)

**A second worked example — one fact about Jane's own open-source project:**

| Target | How the bullet reads |
|---|---|
| Principal Architect | *"Owned every architectural domain personally and drove them to production."* |
| Head of ML | *"Set the **ML architecture and evaluation standard** for the platform end to end."* |
| Staff/Principal IC | *"**Shipped v0 → v1.4 end to end** — 12 connectors, ~1 min per build."* |
| CPTO / Product | *"Owned **roadmap, architecture, pricing and positioning** together, and shipped it."* |
| Data/Platform | *"Built **high-volume ingestion and normalisation pipelines** over 12 heterogeneous sources."* |

**Rule:** lift the JD's nouns and verbs and use *those*. If they say "ship", do not write "deliver".
If they say "own", do not write "was responsible for". A parser matching on their exact string will
not match your synonym, and a human reading their own words feels recognised.

### Move 4 — Order the bullets to answer their #1 requirement first
Re-read the JD's must-haves. The **first bullet of the most recent relevant role** must answer
requirement #1 directly. Then #2, and so on. Six seconds of human attention lands on the top-left of
page 1 — the ordering *is* the argument.

### Move 5 — Business before mechanism
A hiring manager asks *what changed, for whom*; an engineer's instinct is to say *how it was
built*. Lead with the first:

| Mechanism-first (cut) | Business-first (write) |
|---|---|
| *"Built a streaming pipeline on Kafka with exactly-once semantics and schema contracts."* | *"Moved 400 customers from nightly batches to data under 4 minutes old, on Kafka."* |
| *"Designed a rules engine with real-time event detection and eligibility checks."* | *"Cut claim handling from days to seconds for travellers on delayed flights."* |

Internal algorithm names, protocol names and vendor plumbing appear only when the posting asks
for them. Three or more acronyms in one bullet is a bullet nobody outside the team can read.

### Move 6 — Every bullet answers a row of the bullet plan
`fit.md`'s `## Bullet plan` maps each `critical`/`high` requirement to one role and one fact.
Write those bullets first. A bullet that answers no row — however true and impressive — is not
written; the space goes to depth on a row that matters. `lint_cv.py --fit` fails a role in the
three most recent with more than one bullet that shares nothing with the fit keywords.

### The boundary
Rewriting means **restating a real fact in different words**, never adding scope, scale, numbers or
responsibility that did not exist. Every number stays exactly as `profile/profile.md` §7 has it. If a
target needs a fact that is not in the bank, it goes in as a question to the user — not as a bullet.

## 3c. The Professional Summary — the 70 words that decide the six-second read

More attention lands here than anywhere else on the CV. It is rewritten from scratch for every
target. **Never reuse a summary between applications.**

### The formula — three or four sentences, in this order

1. **Who this person is, in one sentence, with the single strongest proof.** The career as a
   person would say it, aimed at this role — not a title label, not a bolded opener.
2. **Their #1 requirement, answered with a specific fact.** Not a claim — evidence, with a number
   or a named thing from `profile/profile.md`.
3. **Scale / leadership credential** — team size, org size or users, from the profile. Short.
4. *(Optional)* their #2 requirement, compressed — only if it fits under 90 words.

### Worked openings — same person, four targets

| Target | Opening sentence |
|---|---|
| Chief Architect | *"Fifteen years designing software in product companies, the last four as CTO of a B2B SaaS platform with 400 enterprise customers."* |
| Principal AI/ML Engineer | *"Builds AI features that reach production, and has done so on three products since 2021."* |
| CPTO | *"Has owned the roadmap and the engineering behind it at two companies, and still writes code."* |
| Director of PM, Security | *"Product leader in security software who can argue the details with engineering rather than approve what they propose."* |

Each one says who the person is in a sentence a human would say aloud. The last lifts the JD's
own phrasing — they wrote *"argue the details with engineering, not just approve what they
propose"*. Quoting a JD's distinctive line back is the strongest signal available that the CV was
written for them, and it costs nothing in truth.

### Rules
- **The headline carries the target title.** The summary may use it once, naturally, but never
  as a bolded opener or a "<Title> profile:" label — that is a template tell. The summary says who
  this person is and why they fit this role, in sentences a person would say.
- **Not credentials glued together.** Semicolon chains ("At X, …; at Y, …") and verbless
  fragments ("Ships AI inside products.") read as generated. Full sentences, uneven lengths.
- **Every claim carries evidence.** "Deep AI experience" is noise; a version, a count and a
  timing — "v0 to v1.4, one maintainer, 12 connectors" — is a fact. Take every number from
  `profile/profile.md` §6; never invent one to make the sentence land.
- **55–90 words; no sentence over 28 words; at least one under 12.** Longer and the six-second
  read is lost. A summary sentence carrying a colon and a list of five things is two sentences.
- **Plain words.** A recruiter who is not an engineer must understand every sentence; system
  internals belong in an interview.
- Use **their** vocabulary throughout — this is where §3b Move 3 matters most.
- **No first person.** CVs use the implied subject: *"Ran engineering across two countries…"*,
  never *"I ran…"*. First person reads as a cover letter pasted into the wrong box.
- **The top five keywords from `fit.md` appear in the summary**, and the proof for the JD's
  riskiest requirement (the `critical` row most likely to be doubted) comes before anything else.

### Gaps never go on the CV
An earlier version of this playbook asked for an "honest calibration" clause naming the gap
(*"…has not run engineering at your headcount"*). In practice a screener reading 300 CVs does not
reward candour; it takes the sentence as the reason to reject, and the rejection arrives the same
day. **The CV states what is true and relevant, and is silent on what is not.** Silence is not a
lie — nothing false is claimed.

Where the gap is real, handle it where it can be argued: in `fit.md` → interview prep, and, if the
form asks directly, with a truthful factual answer (field-policy §3a). `lint_cv.py` fails any CV or
free-text answer that volunteers one ("I have not…", "not my depth", "limited experience").

## 3d. No "Why This Role" section on an employment CV

Recruiters do not expect a CV to argue for the job, and a closing "Why <Company>" block is one of
the clearest signs a CV was generated per application. `lint_cv.py` fails it. The same material
belongs in:
- the **cover letter**, when the form takes one (job-apply step 4), and
- the **"why this company / why this role"** form answers, grounded in `company.md`.

The single exception is an accelerator, fellowship or investor programme whose application asks
for a statement of motivation *as part of the CV*. There, name the section after their own
question.

## 3e. Writing so it does not read as machine-written

A CV that looks generated gets read as *effort not spent*, and at CTO/architect level that is
disqualifying on its own. The tells are not exotic — they are **uniformity**. Real writing is
uneven. Break the pattern deliberately:

### The tells, and the rule for each

| # | Tell | Rule |
|---|---|---|
| 1 | **Every bullet opening with `**Bold lead-in:** …`** — the loudest one | **At most half** the bullets in any role may use a bold lead-in, and never more than three in a row anywhere on the page. The others open with a plain verb (*Rebuilt…*, *Took the platform from…*) or with the number itself (*12 source integrations, one minute per build…*). |
| 2 | **A skills block at the top** — a `·` wall or a grid of labelled skill groups | Neither. Skills are one plain comma-separated line at the end; the keywords that matter are in the bullets. Same ATS coverage, and the work history moves up the page. |
| 3 | **Em-dashes everywhere** | **Two per page, maximum.** Everywhere else use a comma, a full stop, or a colon. Count them before building. |
| 4 | **Every sentence the same length** (18–24 words) | Vary it. Put at least one sentence under nine words in the summary. Short sentences carry weight; a page of even ones reads as filler. |
| 5 | **The abstract tricolon** — "scalability, resilience and observability" | Once per CV at most. Prefer two concrete things to three abstract ones. |
| 6 | **Round marketing numbers** (100%, 3x, 50+) | Use the real, uneven number from the profile — *v0 → v1.4*, *12 source integrations*, *~1 minute per build*. Specificity is the credibility; a rounded number reads as an estimate. |
| 7 | **Bold used as emphasis-by-default** | One bold span per bullet, and not on every bullet. Bold is for the thing a skimmer must not miss, not for decoration. |
| 8 | **The rhetorical contrast frame** — "not just X, but Y", "it's not about X — it's about Y" | Never. It is the single most recognisable LLM cadence in prose. |
| 9 | **`Label: a, b, c` bullets** — what bold lead-ins turn into when they are banned: a noun phrase, a colon, a list | **One per role, three per CV.** Open with a verb that says what changed. |
| 10 | **Level and title echo** — "VP-level ownership", "director-level scope", the posting's title repeated in the bullets | Never. The title lives in the headline and the summary's first sentence; the bullets carry facts. |
| 11 | **Long, jargon-dense sentences** — 35+ words, four acronyms, an algorithm name | Bullet sentences ≤ 32 words, summary sentences ≤ 28, at most three acronyms or product names per bullet, no system-design vocabulary the posting does not use. |
| 12 | **Stylised one-liners** — "X is the normal case", "ships Y as product substance", "owned in one seat" | Never. Abstract self-description in place of a fact. Replace with the fact. |
| 13 | **Two date formats** (`01/2025 – 2026` next to `2024 – 2025`) | One format, everywhere. `MM/YYYY` when the profile has months, `YYYY` when it does not. |

`lint_cv.py` counts tells 1, 3, 8–13 and fails the build on them; the rest are read by eye and by
the recruiter review.

### Words and phrases that do not appear on the user's CV

*proven track record · results-driven · passionate about · leveraging · spearheaded · seamless ·
cutting-edge · robust and scalable · best-in-class · deep dive · synergy · at the intersection of ·
in today's fast-paced · a journey · unlock value · drive impact · holistic · world-class*

Replace each with the specific thing it is standing in for. "Spearheaded the migration" is
"moved 40 services off the monolith in eight months".

### The de-tell pass — run it before `build_cv.py`, every time

1. Count bold lead-ins per role. More than half? Rewrite the surplus to open with a verb.
2. Count em-dashes on the page. More than two? Replace the rest.
3. Read the first three words of every bullet in a role down the page. Do they rhyme? Break them up.
4. Is there a skills block above the work history? Move it to one plain line at the end.
5. Any phrase from the banned list? Any round number? Any "not just X but Y"?
6. Read the summary aloud. If every sentence lands the same way, cut one in half.

**Rewrite, do not just unbold.** A lead-in ends in a colon and the text continues it; delete the
bold and you get *"Designed the data layer for volume and for trust high-volume data pipelines…"*.
Same for em-dashes: swapping one for a comma silently manufactures comma splices
(*"…personally, not delegating it, I took an engine from v0…"*). Every removal is a rewrite of that
sentence. Read each one back after changing it.

**What this does not license.** Varying the writing never varies the facts. Everything in §0 still
holds: no invented title, no invented metric, no claim not in `profile/profile.md`.

## 3f. The bullet test — every bullet, every time

A recruiter reads a bullet in two seconds and decides whether it is about *this* person. Before a
bullet goes on the page, it passes all five:

1. **Only-you.** Could this exact sentence sit on another candidate's CV? *"Built and led the
   engineering team that delivered booking engines"* could; *"Built the engineering team behind
   one booking API over hundreds of airline and hotel suppliers"* could not. The anchor is a
   number or a name — a product, a market, a standard, a customer type, a system. (`lint_cv.py`
   flags every bullet in the three most recent roles that has neither.)
2. **So what.** It says what changed, and for whom, before how. If the reader would ask "and?",
   the result is missing.
3. **Read aloud.** A senior person would say it this way to another person. No label-colon lists,
   no stacked nouns, no vendor plumbing the posting did not ask about.
4. **Serves the posting.** It answers a row of `fit.md`'s bullet plan. A true, impressive bullet
   that answers nothing is cut.
5. **One idea.** One bullet, one point. Two results joined by "and" are two bullets, or one cut.

If a bullet cannot pass truthfully, **cut it** — a role with two strong bullets beats one with four
where two are filler.

## 3g. Consistency — the page reads as one hand

A recruiter who notices *organise* next to *authorize*, *CTO* next to *Chief Technology Officer*, or
*Leads* in a role that ended in 2022 reads a page assembled from parts. `lint_cv.py` fails each:
- **One spelling system** — British or American, matching the posting (and the market).
- **One form of each title** — `CTO` everywhere or `Chief Technology Officer` everywhere.
- **Tense** — past for ended roles; present or past for current ones, but one per role.
- **Punctuation** — every bullet ends with a full stop (or none does). One dash in date ranges.
- **Date format** — `MM/YYYY` or `YYYY`, one throughout.
- **Capitalisation** — role-line descriptors in Title Case; section headings as the template has them.
- **Numbers** — the same style for the same kind of thing (*30+ developers* and *20+ developers*,
  not *thirty* and *20+*).

## 4. Keyword strategy (the ATS gate)

ATS and AI screeners rank by (a) title match, (b) required-keyword coverage,
(c) recency of those keywords, (d) years of experience. So:

1. Build the keyword list from §1.5–1.7. Aim to place EVERY must-have keyword
   in a role bullet where it is true, and in the Skills line. Nice-to-haves once.
2. Use both forms on first use: spell the term out and put the acronym in
   brackets ("Service Level Objective (SLO)"). Screeners tokenise differently;
   humans skim differently.
3. Put the most important keywords in the top third of page 1 (headline,
   summary, first role). Recency-weighted parsers reward this.
4. Mirror the JD's exact phrasing where truthful ("built and scaled", "owned
   the roadmap", "hands-on", "0→1", "enterprise customers"). Do not paraphrase
   a must-have into a synonym the parser won't match.
5. Years of experience: state the profile's own figure in the summary; if the JD says
   "10+ years in X", make sure X is visibly ≥10 years in the timeline.
6. No keyword stuffing in white text, no hidden blocks — modern parsers flag
   it and humans hate it. Density comes from truthful bullets.
7. Skills: one plain comma-separated line, the last section, 12–18 terms, JD must-haves first
   (§3e tell #2). Never a grid of labelled groups, never at the top.
8. **Seed must-have keywords into the BULLETS.** Many screeners weight body text above a keyword
   list, and a human discounts a term that never appears in the evidence. Every must-have should
   be visible **inside a bullet where it is genuinely true**, and again in the Skills line.
9. **Check keyword recency.** A parser that weights recent experience wants the must-haves in the
   top two roles, not only in a job from 2010. If a key term only appears in an old role, find the
   true recent instance of it and lead with that instead.
10. **Run `check_pdf.py` with the JD's must-haves and fix every "missing" and every "weak".** A weak
    (1×) keyword usually means it is in the Skills line but nowhere in the evidence — put it in a
    bullet. This catches a missing must-have keyword before the CV goes out.

## 5. Human gate — the six-second read

The recruiter sees: name, headline, first two lines of summary, the first
role's title+company+dates, and maybe the first bullet. Make each of those
answer "is this person exactly what we asked for?"

- Summary = 3–4 lines (§3c), no adjectives without numbers. Never a line on why this company —
  that belongs in the cover letter and the form answers.
- **The first role a recruiter sees is the most recent employed role**, framed per §6. An own
  venture or open-source project goes in its own small section below the work history.
- **Company URLs on the meta line** (`<https://…>` under the role; the builder prints the bare
  domain) for small or little-known employers, so the reader can check the company exists in one
  glance instead of searching for it. Only a live site: check it responds before using it — a dead
  or parked domain is worse than none. Leave them off household names and off companies with no
  site; never a URL the profile does not record.
- Role lines fit on one line: title | employer · a descriptor of four to six words, in **Title
  Case** like the rest of the role line (`Meridian Labs · Composable Commerce Platform`); short words
  (a, an, and, for, of, the, to, in, on) stay lower case, acronyms keep their form (`SaaS`, `AI`). A descriptor
  that wraps the role line onto two lines is too long.
- Bullets = outcome-first, "Verb + what + scale/number + why it mattered".
  A bold lead-in on at most half the bullets of a role, used for the ones that answer a
  `critical` row of `fit.md`.
- **The first bullet of every role carries a keyword from `fit.md`.** Parsers weight the top of
  each role; humans read nothing else.
- **Roles appear in strict reverse-chronological order, always.** Relevance is shown by how many
  bullets a role gets, never by moving it up. A timeline that jumps (2021 above 2025) reads as
  something being hidden, and parsers compute tenure from order.
- Most recent 2–3 roles get 3–5 bullets; older roles 1–2; roles more than ten years back get
  one merged entry unless the JD is about that work.
- **The merged entry is `#### Earlier Experience`, written role-first**: the title held and the
  work done (*"CEO of two software companies (2003 – 2017), grown to 30+ developers…"*). For an
  employee-track application never call it "ventures", and never lead with *founded* /
  *co-founded*: a page that says "founder" four times profiles the candidate as an entrepreneur
  who will leave, before the reader reaches the work.
- Never more than 2 pages. Page 1 must stand alone.
- Remove anything that raises a question you can't answer in the CV (e.g.
  concurrent ventures for a full-time employer target — collapse or frame as
  "advisory / board" only if true; if not true, ask the user how to present it).

## 6. Concurrency, tenure & "will they stay?"

For full-time employee targets the silent question is "a serial founder — will they leave?", and
short tenures ask "will this one be short too?". Both are settled by the **framing policy** in
`profile/profile.md` (§ Framing policy, written at onboarding, one line per archetype) — not asked
per application, and not improvised:

- **Current own venture or open-source project.** The policy says, per archetype, whether it is
  shown as the current role, or in its own small `## Open Source` (or `## Projects`) section
  below the work history: one line naming the project and the licence, one or two bullets. For
  employee-track archetypes the default is the second: a founder title as the current full-time
  role, directly above a job application, is the loudest "will leave" signal a CV can send.
- **Compound founder titles on employee-track CVs.** Where the profile allows it, a role held as
  `Co-Founder & CTO` is written as the function alone — `CTO` — on a CV for an employed role, and
  keeps the compound on startup and founder-programme CVs. The function is the true title; the
  co-founder half is ownership, and on an employee CV it repeats the "will leave" signal on every
  role line. Only when the profile's allowed-title list includes the plain form.
- **An employer that was acquired** is one continuous entry, with the start date of the original
  employment: `Title | New Owner (formerly Old Name) · short descriptor`, and the meta line says
  `<Old Name> acquired by <New Owner> in MM/YYYY`. Both names on the role line, because the
  recruiter matches it against LinkedIn, where the old name usually has its own entry; the date
  goes on the meta line so the role line stays on one line. Two CV entries for one job read as a
  job change.
- **The CV agrees with LinkedIn.** Titles, employers and dates must match the user's public
  profile, because the recruiter opens it next. When they differ, the profile is fixed first,
  never the CV improvised.
- **Overlapping roles** (`lint_cv.py` reports them). Never hide one; make the relationship
  visible: an advisory or part-time role says so in its descriptor, and concurrent ventures can be
  grouped under one `### Founder ventures` entry with the individual companies as bullets. The
  chronology rule still holds for the entries that remain.
- **Short tenures.** Give each role's descriptor the reason the profile records (acquisition,
  funding round ended, contract scope, venture wound down). A stated reason costs a clause; an
  unexplained year reads as a firing.
- Frame founder roles as building companies for others' capital (venture-backed, board-managed)
  where the profile says so.
- Never hide a current venture entirely — it is on the user's LinkedIn; inconsistency costs more
  than concurrency.

## 7. Company-type variants (what to emphasise)

| Target | Emphasise | De-emphasise |
|---|---|---|
| Seed–Series B startup | 0→1 speed, hands-on coding, fundraising, scrappy team-building, accelerator wins | enterprise process, long procurement cycles |
| Scale-up / Series C+ | org growth, process, architecture standards, multi-tenant SaaS, hiring across countries | agency years, side projects |
| Enterprise / vendor | governance and standards work, enterprise architecture, platform depth | consumer apps |
| Defense / regulated | on-premise delivery, audit trails, data residency, GDPR | growth-hacking language |
| FinTech / payments | payment integrations, reconciliation, risk controls | unrelated consumer work |
| Travel tech | booking and inventory systems, pricing, partner integrations | deep back-office tooling |
| AI-native / agents | shipped AI features, evaluation, retrieval, model operations | unrelated platform rebuilds |
| VC / accelerator / investor | thesis, market, moat, business model, stage honesty, founder track record, "focus" | technical stack lists |
| Consultancy / fractional CTO | breadth across sectors and companies, executive education, languages | single-company depth |

### Open-source and open-core employers (GitLab, Grafana, Elastic, HashiCorp, Supabase…)

Put the open source **on the employer line, not buried in the descriptor**:
`Founder & CTO | <Your Project> · open-source AI context layer (MIT)`. These companies read the
licence as a credential. Name it in the Skills line too, and where it is
true, name the company's own open-core model as a precedent they already cite — that reads as
someone who has thought about their business, not someone who skimmed the careers page.

## 8. Regional CV conventions

- Gulf states: 2 pages fine; nationality + visa status expected; photo optional
  (default none); an existing right to work in the target country is a strong signal — say it.
- EU (DE/AT/CH): photo sometimes expected, DOB sometimes expected — default
  none; ask if the user wants a German-style CV. Lead with the highest formal
  qualification the profile lists; these markets weight it more than the UK or US do.
- UK / US: no photo, no DOB, no nationality (US); 2 pages; US spelling for US
  targets, UK spelling for UK/EU targets (organise/organize, tokenisation/
  tokenization). Match the JD's spelling.
- Local-language markets: where the JD is written in the local language, a CV in
  that language is usually welcome — mirror the JD, and keep an English version ready.

## 9. Output naming & delivery

- File: `<Firstname>_<Lastname>_CV_<Company>.pdf` — ASCII, underscores, **40 characters
  max, no role**. Example: `Jane_Doe_CV_Glean.pdf`.
  Real upload widgets reject long filenames, and the role is already carried by the
  application folder and by the CV's own headline. `build_cv.py` clamps this, so a longer
  name is corrected rather than sent — but it is corrected by dropping words, which reads
  worse than writing it right.
- Always deliver PDF. Also produce DOCX only if the user asks or the application
  portal demands Word.
- In the chat reply: 4–6 lines max — which contact set and why, which title
  label was used, the 5 keywords you led with, and any fact you need them to
  confirm. No long explanations.
