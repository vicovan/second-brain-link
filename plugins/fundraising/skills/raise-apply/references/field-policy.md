# Field policy — what may be typed into an application form

Not advisory. Read before touching a form, every run.

## 1. Never typed, at any autonomy level
- Passwords, one-time codes, security answers.
- Payment details of any kind — and **any fee field means stop**, whatever the amount.
- Passport, national ID, tax ID, social-security or equivalent numbers.
- Date of birth.
- Anything the founder's profile does not contain (§3).

## 2. Stops this application (reported in one line, then the next program)
- A login, a sign-up, or an account to create.
- A CAPTCHA or bot check.
- A required video or audio recording — write the talking points into the folder; the founder records.
- A required reference contact the profile does not list.
- A legal attestation beyond "the information is accurate" (e.g. accepting investment terms).

## 3. Facts vs composed answers
**a. Factual fields** (incorporation, location, team size, amount raised, revenue, users, dates):
answered only from the profile. Missing → ask (supervised) or stop this application (autonomous).
Never estimate, never round up, never "approximately".

**b. Composed fields** (why us, why now, the problem, the insight): always written, from
`stories.md` and `company.md`, tailored to the program's verified thesis. Never left blank, never
handed back as "please fill".

## 4. Demographic and diversity questions
Answered only from an explicit answer in `answers.md`; otherwise "prefer not to say" where offered,
or the field is skipped if optional. Never inferred from a name, a photo or a location.

## 5. Limits
Every field's limit is recorded with its **tested** unit. A counter that says only "100 left" is
ambiguous — type one character: dropping to 99 means characters. Answers are cut to fit, never
truncated mid-sentence by the form.

## 6. Verification
a. Every required field is non-empty in the DOM before submit.
b. Every dropdown, radio and checkbox reads back as the value intended — auto-selection is the most
   dangerous failure (it states something the founder never said).
c. Uploaded files show as attached with the right filename.
d. Multi-page forms: re-verify each page before advancing; a navigation that loses a page's values
   is caught here.
e. A Chrome per-domain permission block is a setup detail: name the domain, continue with other work.
