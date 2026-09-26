#!/usr/bin/env python3
"""
detect_form.py - classify an application form before touching it.

    python3 detect_form.py URL [--html saved-page.html]

Prints {platform, one_question_per_screen, needs_login, fee_signal, upload_fields,
video_signal, multi_page, notes}. With --html (a page the agent saved or read), the
signals come from the page itself; without it, from the URL alone.

A login wall, a fee, or a required video is not something to fight: raise-apply stops
that one application and says which it was.
"""
import argparse, json, re, sys

PLATFORMS = [
    ("typeform", r"typeform\.com|\.typeform\.com"),
    ("tally", r"tally\.so"),
    ("fillout", r"fillout\.com|forms\.fillout"),
    ("google-forms", r"docs\.google\.com/forms|forms\.gle"),
    ("airtable-form", r"airtable\.com/(app|shr)"),
    ("hubspot", r"hsforms|share\.hsforms\.com|hubspot"),
    ("jotform", r"jotform\.com"),
    ("yc-portal", r"ycombinator\.com/apply|apply\.ycombinator\.com"),
    ("aplica", r"aplica\.|\.aplica\."),
    ("f6s", r"f6s\.com"),
    ("notion-form", r"notion\.(so|site)"),
]
LOGIN = r"type=[\"']password|sign in to (continue|apply)|log in to (continue|apply)|create (an )?account|sign up to apply"
FEE = r"application fee|program fee|processing fee|pay(ment)? (of|required)|stripe\.com|checkout|\$\s?\d+ fee"
VIDEO = r"(1|one|2|two|60|90)[- ](minute|min|second)s? video|video (link|url|introduction)|loom\.com|record a video"


def classify(url, html=""):
    u = (url or "").lower()
    platform = next((name for name, pat in PLATFORMS if re.search(pat, u)), "custom")
    h = (html or "").lower()
    res = {
        "platform": platform,
        "one_question_per_screen": platform == "typeform",
        "needs_login": platform in ("yc-portal", "f6s", "aplica") or bool(re.search(LOGIN, h)),
        "fee_signal": bool(re.search(FEE, h)),
        "upload_fields": len(re.findall(r"type=[\"']file", h)),
        "video_signal": bool(re.search(VIDEO, h)),
        "multi_page": platform in ("typeform", "google-forms", "fillout", "yc-portal")
                      or bool(re.search(r"next page|step \d+ of \d+|continue to next", h)),
        "notes": [],
    }
    if platform == "airtable-form" and "/shr" in u:
        res["notes"].append("a shared Airtable VIEW is not a form — it cannot be fetched; ask for a CSV export")
    if res["needs_login"]:
        res["notes"].append("login or account wall — stop this application, the founder signs in")
    if res["fee_signal"]:
        res["notes"].append("fee signal — stop; a fee also reduces the net cheque against the floor")
    if res["video_signal"]:
        res["notes"].append("video requested — write talking points, the founder records it")
    if not html:
        res["notes"].append("URL-only classification — read the page before filling")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--html")
    a = ap.parse_args()
    html = ""
    if a.html:
        try:
            html = open(a.html, encoding="utf-8", errors="replace").read()
        except OSError as e:
            sys.exit(str(e))
    print(json.dumps(classify(a.url, html), indent=1))


if __name__ == "__main__":
    main()
