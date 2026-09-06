# Tailoring Playbook — how to turn a job description into a first-pick CV

Goal per application: be in the top handful out of 1,000+ applicants at BOTH
gates — (1) the ATS / AI screener that ranks by keyword and title match, and
(2) the human who reads the top 20 for six seconds each. Everything below
serves one of those two gates.

## 0. The truth boundary (read first)

You may freely change: emphasis, ordering, wording, which bullets appear,
which of the ALLOWED titles is used, how a role is framed, which contact set
is used, headline, summary, keyword density.
You may never change: employers, dates, degrees, numbers, or claim outcomes,
customers, revenue, certifications or titles not in profile/profile.md.
"Adjust job titles" means choosing the truthful label that mirrors the target
(e.g. Co-Founder & CTO → "CTO & Co-Founder"; Technical Product Director ↔ "Staff
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
   "IAM" and "Identity and Access Management").
6. Nice-to-have keywords: from "bonus", "preferred", "nice to have".
7. Domain signals: industry (fintech, travel, identity, commerce, defense…),
   stack (Python, TS, K8s…), scale words (multi-tenant, enterprise, global).
8. Culture / narrative signals: what they brag about (open source, speed,
   customer obsession, security, regulated, founder-led).
9. The three questions this employer is silently asking (e.g. "has they done
   this exact thing before?", "will they stay?", "can they hire in our region?").

Keep this as a short table at the top of your reasoning; every section of the
CV must answer something in it.

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
Line 1 of the CV is the target title exactly as the JD writes it, plus one differentiator. This is
the strongest single lever and it costs nothing in accuracy, because a headline states what they are
applying *as*, not a role they held.

| JD title | Headline |
|---|---|
| Chief Technology Officer | `Chief Technology Officer (CTO) · 8× founder · AI, FinTech, Identity` |
| VP of Engineering | `VP Engineering / CTO · scaled teams to 30+ across four countries` |
| Principal AI Architect | `Principal AI Architect · agents, MCP, knowledge graphs, IAM` |
| Chief Architect | `Chief Architect · cloud-native platforms, AI integration, data at scale` |
| Head of ML | `Head of ML · production LLM systems, evaluation, agentic orchestration` |
| Engineering Director | `Engineering Director · leading multi-team AI product organisations` |

Also mirror the title **verbatim in the first sentence of the Professional Summary** — ATS parsers
weight the summary heavily, and a human reads it in the same glance.

### Rung 2 — Use an ALLOWED title variant for the role itself
Each role in `profile/profile.md` §4 carries a list of **allowed titles** — labels that are genuinely
accurate for that role, including ones the user actually used at the time. Pick the variant closest to
the target. Examples already sanctioned there:

- **Northwind Data** (the current role) → `Staff Software Architect` for architect/IC targets ·
  `Technical Product Director` for product-leadership targets, when the profile lists both as
  genuinely held. Never both on one CV.
- **Jane's own venture** → `Founder & CEO` · `Founder, CEO & CTO` · `Founder & CTO` — pick the one
  whose emphasis matches the target.
- **Meridian Labs** (an earlier scale-up) → `CTO` or `Chief Technology Officer` (spelled out reads
  more senior to some ATS).

If the target is "Head of Engineering" and the allowed list has "CTO", **use CTO** — do not
downgrade or invent. Seniority above the target is fine; a fabricated title is not.

### Rung 3 — Keep the real title, add a SCOPE-EQUIVALENCE line
When no allowed variant matches the target vocabulary, leave the title truthful and add one line
directly under the role header that restates the scope **in the JD's own words**. This is where most
of the matching actually happens, and it is completely honest — it describes what they did.

```
Co-Founder & CTO · Northwind Data · Dallas, US                    04/2022 – 12/2024
Scope equivalent to VP Engineering: owned architecture, delivery and hiring for a
multi-tenant B2B platform, leading the engineering team end to end.
```

More patterns:
- Target **Engineering Director**, role was CTO at a scale-up →
  *"Directed four engineering teams and their managers across two sites."*
- Target **Principal Architect**, role was Founder/CTO →
  *"Principal-architect scope: owned every architectural decision on the platform personally,
  end to end."*
- Target **Head of AI**, role was Staff Software Architect →
  *"Head-of-AI scope: set the AI technical direction for the platform and its agent governance."*

Use the target's exact noun. If they say "Director", the line says "Directed". If they say
"Principal Architect", the line says "Principal-architect scope".

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
| **Northwind Data** | *agent-first B2B SaaS infrastructure* | *B2B SaaS with multi-gateway payment orchestration* | *multi-tenant enterprise SaaS platform* |
| **Meridian Labs** | *real-time AI rules engine* | *B2B fintech — instant digital payouts* | *regulated real-time transaction platform* |
| **Acme Robotics** | *ML-driven fleet platform, API-first* | *orchestration and payments platform* | *enterprise integration platform* |
| **Globex** | *enterprise AI-agent governance platform* | *platform for regulated industries* | *enterprise governance & administration vendor* |
| **Jane's own venture** | *open-source AI context engine, MIT* | *privacy-first data platform* | *data-sovereign knowledge platform, zero-network core* |

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

### The boundary
Rewriting means **restating a real fact in different words**, never adding scope, scale, numbers or
responsibility that did not exist. Every number stays exactly as `profile/profile.md` §7 has it. If a
target needs a fact that is not in the bank, it goes in as a question to the user — not as a bullet.

## 3c. The Professional Summary — the 90 words that decide the six-second read

More attention lands here than anywhere else on the CV. It is rewritten from scratch for every
target. **Never reuse a summary between applications.**

### The formula — four sentences, in this order

1. **Target title verbatim + the single strongest proof.** Open with the exact title they wrote,
   bolded, then the one credential that most makes it believable.
2. **Their #1 requirement, answered with a specific fact.** Not a claim — evidence, with a number
   or a named thing from `profile/profile.md`.
3. **Their #2 and #3 requirements, compressed.** Usually a domain proof and a delivery proof.
4. **Scale / leadership credential**, or the honest calibration line where one is needed.

### Worked openings — same person, four targets

| Target | Opening sentence |
|---|---|
| Chief Architect | *"**Chief Architect** profile: 15 years of hands-on software architecture in product companies, including **CTO of a B2B SaaS platform**…"* |
| Principal AI/ML Engineer | *"A **pragmatic builder** who leads AI/ML work by shipping it…"* |
| CPTO | *"**Chief Product & Technology Officer** who owns the roadmap and still writes the code…"* |
| Director of PM, Security | *"**Technical Product Director** who owns security product strategy and can argue the details with engineering rather than approve what they propose."* |

The last one lifts the JD's own phrasing — they wrote *"argue the details with engineering, not just
approve what they propose"*. Quoting a JD's distinctive line back is the strongest signal available
that the CV was written for them, and it costs nothing in truth.

### Rules
- **Target title verbatim in sentence 1**, and bolded. Both ATS and humans look here.
- **Every claim carries evidence.** "Deep AI experience" is noise; a version, a count and a
  timing — "v0 to v1.4, one maintainer, 12 connectors" — is a fact. Take every number from
  `profile/profile.md` §6; never invent one to make the sentence land.
- **90–120 words.** Longer and the six-second read is lost.
- Use **their** vocabulary throughout — this is where §3b Move 3 matters most.
- **Include the honest calibration when there is a real gap** (see below).

### The honest calibration line
Where the JD asks for something the user does not have, say it plainly in one clause rather than
hoping it is not noticed. The shape, on three kinds of gap:

- **Wrong flavour of the same discipline** — *"**Engineer and architect rather than research
  scientist** — measured by what ships."*
- **Wrong scale** — *"my CTO experience is at startups and scale-ups, **not as CIO inside a
  Fortune 500**."*
- **Adjacent but not the named specialism** — *"**High-performance training on TPUs is not my
  depth** — my optimisation experience is in serving, retrieval and inference economics."*

This is not modesty for its own sake. A recruiter who finds the gap themselves discounts the whole
CV; one who is told plainly reads the rest as credible. Put it last, after the strengths.

## 3d. The closing section — "Why This Role"

Every tailored CV ends with a 3-bullet section named for the target (*"Why This Role"*, *"Why
<Company>, Why <City>"*, *"Why This Founder, This Venture"*). Structure:

1. **The strongest match**, stated as *their* problem meeting *their* specific experience.
2. **The second match**, usually leadership, commercial range, or domain.
3. **A logistics or calibration line** — work authorization, relocation, language, or the honest gap.

Keep it to three. Four reads as pleading.

## 3e. Writing so it does not read as machine-written

A CV that looks generated gets read as *effort not spent*, and at CTO/architect level that is
disqualifying on its own. The tells are not exotic — they are **uniformity**. Real writing is
uneven. Break the pattern deliberately:

### The eight tells, and the rule for each

| # | Tell | Rule |
|---|---|---|
| 1 | **Every bullet opening with `**Bold lead-in:** …`** — the loudest one | **At most half** the bullets in any role may use a bold lead-in, and never more than three in a row anywhere on the page. The others open with a plain verb (*Rebuilt…*, *Took the platform from…*) or with the number itself (*12 source integrations, one minute per build…*). |
| 2 | **A wall of `·`-separated keywords** under Core Competencies | Use the `kv` block: four or five labelled groups, ≤ 7 terms each. Same ATS coverage, a fraction of the noise. |
| 3 | **Em-dashes everywhere** | **Two per page, maximum.** Everywhere else use a comma, a full stop, or a colon. Count them before building. |
| 4 | **Every sentence the same length** (18–24 words) | Vary it. Put at least one sentence under nine words in the summary. Short sentences carry weight; a page of even ones reads as filler. |
| 5 | **The abstract tricolon** — "scalability, resilience and observability" | Once per CV at most. Prefer two concrete things to three abstract ones. |
| 6 | **Round marketing numbers** (100%, 3x, 50+) | Use the real, uneven number from the profile — *v0 → v1.4*, *12 source integrations*, *~1 minute per build*. Specificity is the credibility; a rounded number reads as an estimate. |
| 7 | **Bold used as emphasis-by-default** | One bold span per bullet, and not on every bullet. Bold is for the thing a skimmer must not miss, not for decoration. |
| 8 | **The rhetorical contrast frame** — "not just X, but Y", "it's not about X — it's about Y" | Never. It is the single most recognisable LLM cadence in prose. |

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
4. Is Core Competencies a `kv` block with labelled groups? If it is one paragraph, convert it.
5. Any phrase from the banned list? Any round number? Any "not just X but Y"?
6. Read the summary aloud. If every sentence lands the same way, cut one in half.

**Rewrite, do not just unbold.** A lead-in ends in a colon and the text continues it; delete the
bold and you get *"Designed the data layer for volume and for trust high-volume data pipelines…"*.
Same for em-dashes: swapping one for a comma silently manufactures comma splices
(*"…personally, not delegating it, I took an engine from v0…"*). Every removal is a rewrite of that
sentence. Read each one back after changing it.

**What this does not license.** Varying the writing never varies the facts. Everything in §0 still
holds: no invented title, no invented metric, no claim not in `profile/profile.md`.

## 4. Keyword strategy (the ATS gate)

ATS and AI screeners rank by (a) title match, (b) required-keyword coverage,
(c) recency of those keywords, (d) years of experience. So:

1. Build the keyword list from §1.5–1.7. Aim to place EVERY must-have keyword
   at least twice: once in Core Competencies, once inside a role bullet where
   it is true. Nice-to-haves once.
2. Use both forms on first use: spell the term out and put the acronym in
   brackets ("Service Level Objective (SLO)"). Screeners tokenise differently;
   humans skim differently.
3. Put the most important keywords in the top third of page 1 (headline,
   summary, competencies, first role). Recency-weighted parsers reward this.
4. Mirror the JD's exact phrasing where truthful ("built and scaled", "owned
   the roadmap", "hands-on", "0→1", "enterprise customers"). Do not paraphrase
   a must-have into a synonym the parser won't match.
5. Years of experience: state the profile's own figure in the summary; if the JD says
   "10+ years in X", make sure X is visibly ≥10 years in the timeline.
6. No keyword stuffing in white text, no hidden blocks — modern parsers flag
   it and humans hate it. Density comes from truthful bullets.
7. Core Competencies section: 40–60 terms, "·"-separated, grouped loosely
   (leadership → AI → domain → stack). Order matters: JD must-haves first.
8. **Seed must-have keywords into the BULLETS, not only the competencies list.** Many screeners
   weight body text above a keyword block, and a human discounts a list of terms that never appear
   in the evidence. Every must-have should be visible **once in Core Competencies and once inside a
   bullet where it is genuinely true** — that is what "at least twice" in rule 1 means.
9. **Check keyword recency.** A parser that weights recent experience wants the must-haves in the
   top two roles, not only in a job from 2010. If a key term only appears in an old role, find the
   true recent instance of it and lead with that instead.
10. **Run `check_pdf.py` with the JD's must-haves and fix every "missing" and every "weak".** A weak
    (1×) keyword usually means it is in Core Competencies but nowhere in the evidence — put it in a
    bullet. This catches a missing must-have keyword before the CV goes out.

## 5. Human gate — the six-second read

The recruiter sees: name, headline, first two lines of summary, the first
role's title+company+dates, and maybe the first bullet. Make each of those
answer "is this person exactly what we asked for?"

- Summary = 3–5 lines, dense, no adjectives without numbers. Pattern:
  [target title] with [years] across [their domain words]. [Two or three
  proof points with numbers]. [Current role framed as relevant to them].
  [One line on why this company/role — only if it is specific and true].
- Bullets = outcome-first, "Verb + what + scale/number + why it mattered".
  Lead phrase in bold when a bullet maps to a JD requirement (the reader
  can scan bold lead-ins as a checklist).
- Most recent 2–3 roles get 3–5 bullets; older roles 1–2; studios (2003–2017)
  get one merged entry unless the JD is about agencies/services.
- Never more than 2 pages. Page 1 must stand alone.
- Remove anything that raises a question you can't answer in the CV (e.g.
  concurrent ventures for a full-time employer target — collapse or frame as
  "advisory / board" only if true; if not true, ask the user how to present it).

## 6. Concurrency & "will they stay?" handling

For full-time employee targets the silent question is "they's a serial founder —
will they leave?" Handle it deliberately:
- Order: employee roles show the user has operated inside
  other people's companies with investors and founders.
- Frame founder roles as building companies for others' capital (venture-
  backed, board-managed).
- An own venture or open-source project: for employee targets, present as
  "Founder (open-source side project)" ONLY if the user says so for that
  application; default is to keep it as the current role. Ask them once per application if the target is a
  full-time employed role: "Keep the venture as the current full-time role, or frame it as
  open-source project alongside?"
- Never hide a current venture entirely — it is on the user's LinkedIn; inconsistency
  costs more than concurrency.

## 7. Company-type variants (what to emphasise)

| Target | Emphasise | De-emphasise |
|---|---|---|
| Seed–Series B startup | 0→1 speed, hands-on coding, fundraising, scrappy team-building, accelerator wins | enterprise process, defense PoCs |
| Scale-up / Series C+ | org growth, process, architecture standards, multi-tenant SaaS, hiring across countries | studio years, personal-finance app |
| Enterprise / vendor | governance and standards work, enterprise architecture, platform depth | consumer apps |
| Defense / regulated | DDIL, air-gapped, local inference, PII stripping, provenance/audit, GDPR | growth-hacking language |
| FinTech / payments | scheme integrations, tokenisation, payment orchestration | travel matching |
| Travel tech | GDS and distribution work, passenger-rights automation, airline retailing | identity depth |
| AI-native / agents | shipped AI systems, MCP/A2A, agent governance, retrieval, local inference | unrelated platform rebuilds |
| VC / accelerator / investor | thesis, market, moat, business model, stage honesty, founder track record, "focus" | technical stack lists |
| Consultancy / fractional CTO | breadth across sectors and companies, executive education, languages | single-company depth |

### Open-source and open-core employers (GitLab, Grafana, Elastic, HashiCorp, Supabase…)

Put the open source **on the employer line, not buried in the descriptor**:
`Founder & CTO | <Your Project> · open-source AI context layer (MIT)`. These companies read the
licence as a credential. Reinforce it with a Core Competencies group of its own, and where it is
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
