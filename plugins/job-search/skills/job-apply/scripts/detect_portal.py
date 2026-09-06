#!/usr/bin/env python3
"""
detect_portal.py - classify a job URL before spending any tokens on it.

    python3 detect_portal.py <url> [--fetch] [--json]
    python3 detect_portal.py --batch urls.txt --json

Verdicts:
  fillable  - public application form, no account needed. Claude may auto-fill.
  walled    - requires creating an account first. Claude is NOT permitted to create
              accounts, and the user chose to SKIP these. Report and move on.
  linkedin  - the user applies themselves. Claude prepares CV + answers only, never drives it.
  aggregator- a listing mirror, not the real form. Resolve to the employer's own URL first.
  unknown   - fetch the page and decide; treat as custom until proven walled.

Exit code: 0 fillable, 1 walled, 2 linkedin, 3 aggregator, 4 unknown.
"""
import argparse, json, os, re, ssl, sys, urllib.request

UA = "SecondBrainLink-JobSearch/1.0 (+https://secondbrainlink.com; public job-board APIs only)"

# host/path patterns -> (verdict, ats name)
RULES = [
    # --- public forms: no account required ---
    # job-boards.EU.greenhouse.io is the EU-hosted board (JetBrains and other EU employers
    # use it). Missing it classified a top-ranked role "unknown" in one run.
    (r"(job-)?boards(\.eu)?\.greenhouse\.io|greenhouse\.io/embed|gh_jid=", "fillable", "greenhouse"),
    (r"jobs\.lever\.co",                                   "fillable", "lever"),
    (r"jobs\.ashbyhq\.com|ashbyhq\.com/[^/]+/[0-9a-f-]{36}", "fillable", "ashby"),
    (r"apply\.workable\.com|\.workable\.com/j/",           "fillable", "workable"),
    (r"jobs\.smartrecruiters\.com|careers\.smartrecruiters\.com", "fillable", "smartrecruiters"),
    (r"\.recruitee\.com",                                  "fillable", "recruitee"),
    (r"jobs\.personio\.(com|de)|\.jobs\.personio",         "fillable", "personio"),
    (r"\.teamtailor\.com",                                 "fillable", "teamtailor"),
    (r"breezy\.hr|\.breezy\.hr",                           "fillable", "breezy"),
    (r"jobvite\.com/[^/]+/job",                            "fillable", "jobvite"),
    (r"pinpointhq\.com",                                   "fillable", "pinpoint"),

    # --- account walls: Claude cannot create accounts; the user chose to skip ---
    (r"myworkdayjobs\.com|workday\.com|wd\d+\.myworkday",  "walled", "workday"),
    (r"taleo\.net|tbe\.taleo|\.taleo\.",                   "walled", "taleo"),
    (r"successfactors\.(com|eu)|jobs\.sap\.com|sfsf",      "walled", "successfactors"),
    (r"icims\.com",                                        "walled", "icims"),
    (r"brassring\.com|kenexa",                             "walled", "brassring"),
    (r"oraclecloud\.com/hcmUI|fa-[a-z]+\.oraclecloud",     "walled", "oracle-hcm"),
    (r"avature\.net",                                      "walled", "avature"),
    (r"eightfold\.ai/careers",                             "walled", "eightfold"),
    # join.com shows a public posting but "Apply now" goes to /apply/authentication
    (r"join\.com/companies",                               "walled", "join.com"),
    (r"phenompeople\.com|\.phenom\.",                      "walled", "phenom"),
    (r"csod\.com|cornerstoneondemand",                     "walled", "cornerstone"),
    (r"bamboohr\.com/careers/\d+.*login",                  "walled", "bamboo-login"),

    # --- the user applies themselves ---
    (r"linkedin\.com/jobs",                                "linkedin", "linkedin"),

    # --- mirrors, not the real form ---
    (r"indeed\.com|glassdoor\.|ziprecruiter\.|totaljobs\.|jobleads\.|"
     r"remotive\.com|wellfound\.com|startup\.jobs|builtin\.com|"
     r"web3\.career|jobbird\.com|jobster|remoterocketship\.com|"
     r"welcometothejungle\.com|otta\.com|jobs\.workable\.com/search",                 "aggregator", "aggregator"),
]

# Text that appears on a page when an account is required, even on an unknown ATS.
WALL_TEXT = re.compile(
    r"create an account|sign up to apply|register to apply|create your profile to|"
    r"you must be signed in|log in to apply|create a candidate account|"
    r"set a password|confirm password", re.I)

FORM_TEXT = re.compile(
    r"<input[^>]+type=[\"']file|apply for this job|submit application|"
    r"first name|resume|cv upload|attach your", re.I)


def ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:                                            # noqa: BLE001
        pass
    for ca in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if os.path.exists(ca):
            try:
                return ssl.create_default_context(cafile=ca)
            except Exception:                                    # noqa: BLE001
                pass
    return ssl.create_default_context()


def classify(url):
    for pat, verdict, ats in RULES:
        if re.search(pat, url, re.I):
            return verdict, ats, "url pattern"
    return "unknown", "unknown", "no pattern matched"


def probe(url):
    """Fetch the page and look for account-wall or form markers."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25, context=ssl_ctx()) as r:
            body = r.read(400_000).decode("utf-8", "replace")
    except Exception as e:                                       # noqa: BLE001
        return None, f"fetch failed: {e}"
    if WALL_TEXT.search(body):
        return "walled", "account-wall text found in page"
    if FORM_TEXT.search(body):
        return "fillable", "application form markers found in page"
    return None, "page fetched, inconclusive"


ACTION = {
    "fillable":   "Auto-fill with the cheap subagent, then pre-submit review.",
    "walled":     "SKIP (the user's choice). Claude cannot create accounts. Log as skipped.",
    "linkedin":   "Do NOT automate. Build CV + answers, hand the user the ready tab.",
    "aggregator": "Resolve to the employer's own posting first, then re-run this.",
    "unknown":    "Fetch the real page; treat as custom-fillable unless a wall appears.",
}
CODE = {"fillable": 0, "walled": 1, "linkedin": 2, "aggregator": 3, "unknown": 4}


def one(url, do_fetch):
    verdict, ats, why = classify(url)
    if do_fetch and verdict in ("unknown", "fillable"):
        p_verdict, p_why = probe(url)
        if p_verdict == "walled":                 # a wall always overrides
            verdict, ats, why = "walled", ats, p_why
        elif p_verdict and verdict == "unknown":
            verdict, why = p_verdict, p_why
    return {"url": url, "verdict": verdict, "ats": ats,
            "reason": why, "action": ACTION[verdict]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--batch", help="file with one URL per line")
    ap.add_argument("--fetch", action="store_true", help="also fetch the page to confirm")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    urls = []
    if a.batch:
        urls += [l.strip() for l in open(a.batch, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
    if a.url:
        urls.append(a.url)
    if not urls:
        sys.exit("need a url or --batch")

    out = [one(u, a.fetch) for u in urls]
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out:
            print(f"{r['verdict']:<11} {r['ats']:<16} {r['url'][:74]}")
            print(f"            -> {r['action']}  ({r['reason']})")
    sys.exit(CODE[out[-1]["verdict"]] if len(out) == 1 else 0)


if __name__ == "__main__":
    main()
