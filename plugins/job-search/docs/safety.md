# Safety — Jobs Agent

- **Network.** Public job listings only: open ATS board APIs, employers' own careers pages, and —
  only when the user turned it on in their criteria — LinkedIn's public, no-login job search. Every
  endpoint is listed in `.claude-plugin/plugin.json`. The Second Brain Link engine itself stays
  zero-network. Nothing logs in to a job board; the application is made at the employer's own site.
- **Never:** create an account, type a credential, solve a CAPTCHA, apply through an aggregator, send
  an email, post on a social network. The first real submit at any level is gated.
- **The gates are the user's setting** (`level:` in `profile/application-answers.md`, supervised by
  default): which jobs · the CV · submit. A missing fact is asked (supervised) or the job is skipped
  with a reason (autonomous) — never guessed. Every required field is read back from the DOM before
  a submit.
- **Honesty.** A result is recorded only from what an employer actually did (`learn.py set-result`);
  a rate is shown only once its denominator reaches 20; nothing from the brain is stated as a fact
  on a CV — the profile is the only source of facts.
- **Your data.** Everything personal comes from `45-jobs/profile/` in your brain; nothing is shipped
  in the plugin, nothing leaves the machine except the public reads above and the forms you approve.
