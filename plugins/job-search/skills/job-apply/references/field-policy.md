# Field Policy — what may be typed, what must be shown, what stops the run

This file governs the auto-filler. It is not advisory. When policy and speed conflict, policy wins.

---

## 1. NEVER type these — stop and hand the field to the user

Claude is prohibited from entering these anywhere, on any site, no matter who asks or how the
field is labelled. If a required field matches, **halt the application and tell the user which field**.

- Passwords, password confirmations, PINs, 2FA/OTP codes, security answers
- **Passport number, any national identity number, tax or social-security number,
  driving-licence number**
  (Gulf and some EU employers ask for these at application stage — this is the most likely trigger)
- Bank account, IBAN, card number, CVV, any payment detail
- Date of birth — the master profile says omit by default (§1); only the user may supply it
- Digital-signature fields that constitute a legal signature
- Anything requiring a document upload other than the tailored CV/cover letter Claude just built

**Never create an account.** If a form requires registration before applying, that job is
**skipped** per the user's standing choice. Do not attempt to work around it.

## 2. ALWAYS recorded verbatim — never summarised, never buried

These carry legal or negotiating weight, so the **exact question and the exact answer** must reach
the user in full — never a paraphrase:

- at **`supervised`**, quoted back before the submit gate;
- at **`autonomous`**, written verbatim into `answers.json` and `ANSWERS.md` **before** the click,
  and listed in the post-submit report. Nobody is reading them in advance, which makes the written
  record the only place they exist.

The fields:

- Work authorization / visa sponsorship ("Do you now or will you in future require sponsorship?")
- Right-to-work-in-country questions, and anything about nationality or residency
- Salary expectation, current salary, notice period, earliest start date
- Any "I certify that the information is true", "I agree to the terms", consent or GDPR checkbox
- Every free-text answer Claude composed (cover letter, "why this company", "why you")
- Willingness to relocate, travel percentage, on-site days
- References, and permission to contact a current employer

## 3. Answer-source rule — two kinds of field, two different rules

The two kinds are not the same problem, and treating them the same is what left a required
"Why <company>?" box empty and handed the form back to the user.

### 3a. FACTUAL fields — looked up, never invented

Anything checkable against reality: name, contact, work authorisation, notice period, salary
expectation, dates, titles held, languages, education, references, every consent and
certification.

Every one of these comes from **`<brain>/45-jobs/profile/profile.md`** or
**`profile/application-answers.md`**. Nothing else. If a factual question cannot be answered
truthfully from those two files, **ask the user** — and in an autonomous run, where there is
nobody to ask, **skip that job with a one-line reason**. Do not infer, do not approximate, do
not "reasonably assume". An invented fact here goes out under their name to a real employer
and may be relied on.

Where a truthful answer would hurt (e.g. "years of Portuguese: 0" on a role requiring fluent
Portuguese), answer truthfully and flag it — or skip the job. Never soften it into something
untrue.

### 3b. COMPOSED fields — written, every time, never bounced back

Why this company · why this role · cover letter · biggest achievement · management scope ·
"tell us about yourself" · anything asking for prose rather than a fact.

These are **written**, not looked up, so the answer-source rule above does not apply and must
not be used to refuse them. Compose from the profile, `application-answers.md` §4, the
tailored CV and the job description's own vocabulary. Match the length the form asks for —
if it says 200–400 words, write 200–400 words.

**A composed field is never left blank and never returned to the user as a question.** A
required input still empty when the form is verified is a bug in the run, not something to
ask about. In `supervised` mode the user reads every composed answer at the submit gate; in
`autonomous` mode they read it afterwards in `answers.json` — either way they see it, so the
job is to write the best version, not to avoid writing one.

Two things stay true regardless: never state a fact inside composed prose that §3a could not
have supplied, and where the employer expresses a preference about AI-assisted answers, still
write it and **record in `ANSWERS.md` that it was composed**, so the record is honest about
how the words were produced.

## 4. EEO / demographic / diversity questions

These are voluntary in almost every jurisdiction. **Default: select "prefer not to say" / decline
to answer**, and note it in the review. Do not guess ethnicity, gender, veteran or disability
status. If a form makes one mandatory, surface it to the user rather than choosing.

## 5. Contact set

One phone, one location, chosen by playbook §2 in `cv-tailor/references/tailoring-playbook.md`
and stated in the review. Never both phone numbers. Never both cities except for a global
programme, per that playbook.

## 6. Account-wall detection

`detect_portal.py` catches the known ones by URL (Workday, Taleo, SuccessFactors, iCIMS, BrassRing,
Oracle HCM, Avature, Eightfold, Phenom, Cornerstone). For an unknown site, treat these page strings
as a wall: *create an account, sign up to apply, register to apply, log in to apply, set a password,
confirm password, create a candidate account*.

On a wall: log the job as `skipped_walled`, tell the user the company, the role and the URL in one line,
and move to the next. Do not spend further tokens on it.

## 6b. HOW to fill a field so it actually registers — learned the hard way

Most modern ATS forms (**Ashby, Greenhouse, Lever, Workable**) are React-controlled. A value written
straight into the DOM — which is what `form_input` does — **displays correctly but is never
registered**. The form then fails validation with *"Missing entry for required field"* on fields
that visibly contain the right text. This has wasted a submit more than once.

**Rules:**
1. **Text inputs: click the field, then type real keystrokes** (`computer` → `left_click`, then
   `type`). Do not rely on `form_input` for a React form.
2. **To clear a field, NEVER press `cmd+a`** — it selects the entire document, not the field.
   Use `triple_click` on the field alone, or press `Backspace` repeatedly.
3. **Dropdowns / comboboxes: click, type a few characters, wait, then click the real option**
   from the listbox. Setting the text alone does not select anything.
4. **Yes/No toggles and radios: click them, then screenshot and confirm the selected state.**
   A subagent reported two toggles set that were not set — verify, never trust the report.
5. **Prove it before handing over: attempt validation.** After filling, take a screenshot and check
   for an error banner. A form that looks complete can still be empty underneath.

## 6c. ATS-specific traps — check before filling

| ATS | Trap | What to do |
|---|---|---|
| **Ashby** | React-controlled inputs. `form_input` DOM writes display but never register; submit fails "missing required field". | Click the field, type real keystrokes. Verify toggles by screenshot. |
| **SmartRecruiters** | The CV upload `<input type=file>` lives inside a **`SPL-DROPZONE` shadow root**, so `read_page`/`find`/`file_upload` cannot see it. Clicking "Choose a file" opens a native OS dialog you cannot use. | Locate it with `javascript_tool`, walk shadow roots for `SPL-DROPZONE`, **move the actual input element into the light DOM** (`document.body.appendChild(inp)` — listeners travel with it), give it an `aria-label` + id, `file_upload` to its ref, then **put it back** in the shadow root and clear the styles. Also: City is a typeahead needing a dropdown pick, and the phone country code defaults to the company's country. |
| **Own-site forms** (a company's own careers page, not an ATS) | Hidden **honeypot** field — often "Website" with no placeholder, before Name, beside a hidden input. Filling it bins the application. | Leave any unlabelled/oddly-placed extra field blank. The real portfolio field is clearly labelled. |
| **join.com** | Public posting, but "Apply now" → `/apply/authentication`. | Account wall — skip. |
| **Greenhouse (embedded)** | The form is an iframe on the company domain; the extension may lack `greenhouse.io` permission. | Ask the user to allow the domain — never drop the job for this. |


## 6d. React dropdowns need PAUSES, and display text is not a value

**The failure:** on a Greenhouse form a subagent reported all seven questions answered. Every
one displayed the right text. **None of them was registered** — `form.checkValidity()` was false and
six required inputs were empty. `form_input` sets `.value` on the visible search input; the real
answer lives in a separate hidden input that only React's own change handler writes.

**The fix, for Greenhouse react-select and Ashby alike:**
1. `left_click` the combobox.
2. **wait ~1 second** — without the pause the menu has not opened and the keystrokes go nowhere.
3. `type` the option text with real keystrokes.
4. **wait ~1 second** — the option list has to filter.
5. `key Enter`.
6. **wait ~1 second**, then verify.

Batching click+type+Enter with no waits silently does nothing. This was reproduced: the identical
batch failed without waits and worked with them.

**Verify the REGISTERED value, never the displayed one:**
```js
// what is actually selected
[...document.querySelectorAll('.select__single-value,[class*=singleValue]')].map(e=>e.innerText.trim())
// how many required inputs are still empty - must be 0 before submitting
[...document.querySelectorAll('input[required]')].filter(e=>!e.value && /requiredInput/i.test(e.className)).length
```

**Typing a short answer can select the wrong option.** Typing "Yes" into a sponsorship dropdown
selected a specific named visa the applicant does not hold — a false statement about them, on a
question with legal weight.
**Always list the filtered options and confirm which one is focused before pressing Enter:**
```js
[...document.querySelectorAll('.select__option')].map(e=>({t:e.innerText.trim(), focused:/focused/i.test(e.className)}))
```

**Read the question, not the job's country.** Sponsorship questions come in two shapes and they
have different answers for the same person:

- *"Will you require sponsorship to remain in **your current location**?"* — asks about the country
  they already live and work in.
- *"Do you have the right to work in **[the job's country]**?"* — asks about somewhere they may
  never have lived.

Answer each from `profile/application-answers.md` §2, which records the position **per region** for
exactly this reason. Never carry one answer across to the other question, and never infer either
from where the job is posted.


## 6e. Chrome extension domain permissions — surface them, do not sit on them

The extension refuses to read pages on a domain until the user allows it, and **Claude cannot grant that
itself**. Left unsurfaced it stalls finished applications silently — the run looks busy and nothing
is moving.

**What to do:**
1. **Ask for the domain the moment a call returns "Permission denied for reading pages on this
   domain."** Trigger the extension's own prompt by retrying the action — do not quietly move on.
2. **Tell them which domain, on which job, and what is waiting on it.** Otherwise they cannot
   know what to approve, where, or when — a bare "blocked" is useless to them.
3. **Front-load it.** At the start of a multi-job run, ask for every domain it will need so every
   permission prompt appears at the start of the run, not scattered through it.

**The ATS domains this system uses** — worth allowing once, permanently:
`job-boards.greenhouse.io` · `job-boards.eu.greenhouse.io` · `boards.greenhouse.io` ·
`jobs.ashbyhq.com` · `jobs.lever.co` · `jobs.smartrecruiters.com` · plus employer career domains
that host their own form (`jobs.elastic.co`, `databricks.com`, `fivetran.com`).

**A permission block never removes a job from the list.** It is a pause, not a disqualification.

## 7. Rate and conduct

One application at a time. Never submit the same application twice — check `outcomes.jsonl` for the
job key first. Never message a recruiter, never send email, never accept terms beyond the
application form itself. Never touch a LinkedIn form (the user's standing choice — prepare and hand off).
