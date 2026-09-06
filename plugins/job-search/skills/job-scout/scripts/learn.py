#!/usr/bin/env python3
"""
learn.py - the feedback loop shared by job-scout, cv-tailor and job-apply.

This is NOT machine learning. It is a durable, human-readable record of what was tried and
what came back, plus rules distilled from it. Every skill reads `lessons.md` before acting
and appends observations after. `consolidate` turns repeated observations into rules and
recomputes the response statistics from real outcomes.

State (shared root, outside any skill folder):
    <state root>/   (default; override with $JOB_SEARCH_HOME)
        outcomes.jsonl        one line per application / draft / skip
        observations.jsonl    candidate lessons awaiting corroboration
        lessons.md            the distilled rules every skill reads at step 0
        applications/YYYY-MM-DD/<job_key>/   tailored CV + answers, filed by the day it went out

Subcommands:
    kpi           **THE NORTH STAR** — successful applications, shortlist conversion,
                  why shortlisted jobs failed, and which portals actually convert
    log-outcome   record an application, draft or skip
    set-result    record what came back (none|rejected|screen|interview|offer)
    add-lesson    append a candidate observation
    consolidate   promote observations seen >=3x into rules; recompute stats
    show          print lessons.md (what skills read at step 0)
    stats         response rates by source, portal, score band
    pending       applications with no result yet, oldest first
"""
import argparse, collections, datetime, json, os, pathlib, re, sys
try:
    import fcntl
except ImportError:      # Windows — the lock is a hardening, not a requirement
    fcntl = None

def _state_root():
    """Delegates to paths.py — the single resolver. Kept as a function so callers
    that already import `_state_root` keep working."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paths import state_root
    return state_root()


ROOT = _state_root()
OUT = ROOT / "outcomes.jsonl"
OBS = ROOT / "observations.jsonl"
LESSONS = ROOT / "lessons.md"
APPS = ROOT / "applications"
TODAY = datetime.date.today().isoformat()

RESULTS = ["none", "rejected", "screen", "interview", "offer"]
# "prior_external" = the user applied to this themselves, outside the system. It keeps the job out of
# every future sweep without inflating the north-star count, which measures what THIS system sent.
# "filled" and "not_started" are the IN-PROGRESS states. They existed as glyphs in
# render_brain.py (STATUS_GLYPH) but not here, so an application that was built and filled
# but not yet sent could not be logged at all — and render_brain renders from this ledger,
# so the user's own application was invisible in their vault until after they submitted it.
# Every one of these has a glyph in render_brain.py STATUS_GLYPH, and the reverse must hold
# too: a state the vault can DISPLAY but this file cannot RECORD is a state an application
# can get stuck in invisibly. (`replied` and `interview` are results, not statuses — they are
# recorded with `set-result` and live in RESULTS below.)
STATUSES = ["applied", "filled", "not_started", "drafted_linkedin", "skipped_walled",
            "skipped_policy", "disqualified", "excluded", "abandoned", "prior_external"]

HEADER = """# Lessons — what the job search has actually learned

Auto-maintained by `learn.py`. **Every skill reads this file before acting.**
Rules below are earned from real outcomes, not assumptions. A rule may *inform* scoring but
never silently edits `profile/search-criteria.md` — changes to the criteria stay the user's call.

"""


def rows(p):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _locked(f):
    """Exclusive lock for the duration of a write.

    The pipeline fans out one subagent per job, and they are told never to touch the
    ledger — but "told" is not a guarantee, and two interleaved appends produce a line
    that json.loads cannot read, which `rows()` then silently drops. A drop here means an
    application vanishes from the vault. The lock makes the rule structural.
    """
    if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    return f


def append(p, obj):
    ROOT.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        _locked(f)
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def rewrite(p, recs):
    """Replace the whole ledger, atomically, under the same lock as append()."""
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        _locked(f)
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


def norm(t):
    return re.sub(r"\s+", " ", t.strip().lower()).rstrip(".")


def band(score):
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "unscored"
    return "80+" if s >= 80 else "70-79" if s >= 70 else "60-69" if s >= 60 else "<60"


def _app_dir(key, day=TODAY):
    """This job's artifact folder. An existing folder under any day wins over a new one
    under today, so a job worked on across midnight keeps one home."""
    if APPS.is_dir():
        for d in sorted(APPS.iterdir(), reverse=True):
            if (d / key).is_dir():
                return d / key
    return APPS / day / key


def cmd_log(a):
    """Record — or update — one application.

    UPSERT, not append. An application is now logged TWICE: once as `filled` the moment
    its folder is created (so it shows up in the vault while it is being worked on) and
    again as `applied` after it is sent. A plain append would leave two rows for one job,
    which double-counts the KPI and renders the application twice.
    """
    key = a.job_key or re.sub(r"[^a-z0-9]+", "-", f"{a.company}-{a.role}".lower()).strip("-")
    recs = rows(OUT)
    prior = next((r for r in recs if r.get("job_key") == key), None)
    if prior and prior.get("status") == "applied" and a.status == "applied":
        sys.exit(f"REFUSING: already applied to '{key}'. Never apply twice.")
    rec = {"date": TODAY, "job_key": key, "company": a.company, "role": a.role,
           "url": a.url, "source": a.source, "score": a.score, "portal": a.portal,
           "status": a.status, "cv_variant": a.cv_variant, "contact_set": a.contact_set,
           "keywords": [k.strip() for k in (a.keywords or "").split(";") if k.strip()],
           "result": None, "result_date": None, "note": a.note}
    if prior:
        # Keep what the earlier row knew and the caller left blank — a `--status applied`
        # follow-up is usually terser than the `filled` row that preceded it — and never
        # lose a result already recorded against this job.
        for k, v in prior.items():
            if k in ("result", "result_date") or (rec.get(k) in (None, "", []) and v not in (None, "", [])):
                rec[k] = v
        rec["date"] = prior.get("date") or TODAY
        rec["status"] = a.status
        recs[recs.index(prior)] = rec
        rewrite(OUT, recs)
    else:
        append(OUT, rec)
    # Dated folder: applications/YYYY-MM-DD/<job_key>/. On the second log for a job (the
    # `applied` follow-up to a `filled` row) reuse the day it was STARTED — creating a
    # second folder under today would split one application across two days.
    d = _app_dir(key, rec.get("date") or TODAY)
    d.mkdir(parents=True, exist_ok=True)
    # a per-application record of exactly what was sent
    ansf = d / "ANSWERS.md"
    if not ansf.exists():
        placeholder = ("_Record every non-obvious answer here - work authorization, salary, "
                       "notice period, consents, free text - so it can be quoted back at interview._")
        lines = [
            f"# {a.company} - {a.role}", "",
            f"- **Applied:** {TODAY}",
            f"- **Status:** {a.status}",
            f"- **Job key:** `{key}`",
            f"- **URL:** {a.url or '-'}",
            f"- **Portal:** {a.portal or '-'}",
            f"- **Score:** {a.score or '-'}",
            f"- **Contact set:** {a.contact_set or '-'}",
            f"- **CV sent:** {a.cv_variant or '-'}  (PDF in this folder)",
            f"- **Keywords led with:** {a.keywords or '-'}", "",
            "## Answers given on the form", "",
            placeholder, "",
        ]
        # The run notes are NOT the answers. Putting them under the answers heading is
        # how "Submitted, confirmation page reached." ended up filed as if it were what
        # was typed into the form — and then rendered twice in the vault note.
        if a.note:
            lines += ["## Notes", "", a.note, ""]
        lines += [
            "## Result", "",
            f"_Not yet._ Record with: `learn.py set-result --job-key {key} --result screen`", "",
        ]
        ansf.write_text("\n".join(lines), encoding="utf-8")
    print(f"logged {key} [{a.status}]")
    print(f"artifacts dir: {d}")
    print(f"record: {ansf}")


def cmd_set_result(a):
    recs = rows(OUT)
    hit = [r for r in recs if r.get("job_key") == a.job_key]
    if not hit:
        sys.exit(f"no outcome with job_key '{a.job_key}'. Try: learn.py pending")
    for r in recs:
        if r.get("job_key") == a.job_key:
            r["result"] = a.result
            r["result_date"] = TODAY
            if a.note:
                r["note"] = a.note
            try:
                d0 = datetime.date.fromisoformat(r["date"])
                r["days_to_response"] = (datetime.date.today() - d0).days
            except (ValueError, KeyError, TypeError):
                pass
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                   encoding="utf-8")
    print(f"{a.job_key} -> {a.result}")


def cmd_add_lesson(a):
    append(OBS, {"date": TODAY, "tag": a.tag, "text": a.text.strip()})
    n = sum(1 for o in rows(OBS) if norm(o["text"]) == norm(a.text))
    print(f"observation recorded ({n}x). Promoted to a rule at 3x — run: learn.py consolidate")


def compute_stats():
    recs = [r for r in rows(OUT) if r.get("status") == "applied"]
    done = [r for r in recs if r.get("result")]
    lines = []
    if not recs:
        return ["_No applications logged yet — statistics appear here once there are outcomes._"]
    pos = {"screen", "interview", "offer"}
    lines.append(f"- **{len(recs)} applications**, {len(done)} with a result, "
                 f"{len(recs)-len(done)} still open.")
    if done:
        good = sum(1 for r in done if r["result"] in pos)
        lines.append(f"- **Overall response rate: {good}/{len(done)}** "
                     f"({100*good//max(1,len(done))}%).")
        for field, label in (("source", "source"), ("portal", "portal"),
                             ("contact_set", "contact set")):
            agg = collections.defaultdict(lambda: [0, 0])
            for r in done:
                k = r.get(field) or "unknown"
                agg[k][1] += 1
                if r["result"] in pos:
                    agg[k][0] += 1
                    
            parts = [f"{k} {v[0]}/{v[1]}" for k, v in sorted(agg.items())]
            if parts:
                lines.append(f"- By {label}: " + " · ".join(parts))
        agg = collections.defaultdict(lambda: [0, 0])
        for r in done:
            k = band(r.get("score"))
            agg[k][1] += 1
            if r["result"] in pos:
                agg[k][0] += 1
        lines.append("- By score band: " +
                     " · ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(agg.items())))
        days = [r["days_to_response"] for r in done if r.get("days_to_response") is not None]
        if days:
            lines.append(f"- Median days to any response: **{sorted(days)[len(days)//2]}**.")
    return lines


def cmd_consolidate(a):
    ROOT.mkdir(parents=True, exist_ok=True)
    obs = rows(OBS)
    counts = collections.Counter(norm(o["text"]) for o in obs)
    first = {}
    for o in obs:
        first.setdefault(norm(o["text"]), o)

    existing = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""
    promoted = []
    for text, n in counts.items():
        if n >= a.threshold and norm(first[text]["text"]) not in norm(existing):
            promoted.append((first[text], n))

    kept = []
    if existing:
        m = re.search(r"## Rules\n(.*?)(?=\n## |\Z)", existing, re.S)
        if m:
            kept = [l for l in m.group(1).splitlines() if l.strip().startswith("-")]

    for o, n in promoted:
        kept.append(f"- **[{o['tag']}]** {o['text'].rstrip('.')}. "
                    f"_(observed {n}x, first {o['date']})_")

    body = HEADER + "## Rules\n"
    body += ("\n".join(kept) if kept else
             "_No rules yet. Observations become rules after being seen "
             f"{a.threshold} times._") + "\n"
    body += "\n## Statistics (recomputed from outcomes.jsonl)\n"
    body += "\n".join(compute_stats()) + "\n"
    body += f"\n_Last consolidated {TODAY}._\n"
    LESSONS.write_text(body, encoding="utf-8")

    print(f"lessons.md updated — {len(kept)} rule(s), {len(promoted)} newly promoted")
    for o, n in promoted:
        print(f"  + [{o['tag']}] {o['text']} ({n}x)")


def cmd_show(a):
    print(LESSONS.read_text(encoding="utf-8") if LESSONS.exists()
          else "No lessons.md yet — run: learn.py consolidate")


def cmd_stats(a):
    print("\n".join(compute_stats()))


def cmd_pending(a):
    p = [r for r in rows(OUT) if r.get("status") == "applied" and not r.get("result")]
    if not p:
        print("nothing pending")
        return
    for r in sorted(p, key=lambda r: r["date"]):
        age = (datetime.date.today() - datetime.date.fromisoformat(r["date"])).days
        print(f"{r['date']}  ({age:3}d)  {r['company'][:28]:30} {r['role'][:34]:36} {r['job_key']}")


def cmd_kpi(a):
    """THE NORTH STAR: successful applications, and what stops there being more."""
    recs = rows(OUT)
    # prior_external = the user applied themselves, outside the system. It belongs in neither the
    # numerator nor the denominator: this KPI measures what THIS system sent.
    recs = [r for r in recs if r.get("status") != "prior_external"]
    applied = [r for r in recs if r.get("status") == "applied"]
    blocked = [r for r in recs if str(r.get("status","")).startswith("skipped")]
    drafted = [r for r in recs if r.get("status") == "drafted_linkedin"]
    total = len(recs)
    print("# KPI — north star: successful applications\n")
    print(f"## ✅ SUCCESSFUL APPLICATIONS: {len(applied)}\n")
    if total:
        print(f"- Shortlisted and attempted : {total}")
        print(f"- **Submitted**             : {len(applied)}   ({100*len(applied)//total}% conversion)")
        print(f"- Blocked before submitting : {len(blocked)}   ({100*len(blocked)//total}% wasted shortlist)")
        if drafted:
            print(f"- Handed to the user to submit   : {len(drafted)}")
    by = collections.Counter(r.get("status","?") for r in recs)
    print("\n## Outcome breakdown")
    for k,v in by.most_common(): print(f"- {k}: {v}")
    if blocked:
        print("\n## Why shortlisted jobs failed — fixing these raises the KPI")
        for r in blocked:
            why = (r.get("note") or "").split(".")[0][:110]
            print(f"- **{r.get('company')}** ({r.get('portal') or '?'}): {why}")
    pf = collections.defaultdict(lambda: [0,0])
    for r in recs:
        k = r.get("portal") or "unknown"; pf[k][1]+=1
        if r.get("status")=="applied": pf[k][0]+=1
    print("\n## Applications landed, by portal — aim the search here")
    for k,v in sorted(pf.items(), key=lambda x:-x[1][0]): print(f"- {k}: {v[0]}/{v[1]}")
    done=[r for r in applied if r.get("result")]; pos={"screen","interview","offer"}
    print("\n## Replies")
    if done:
        g=sum(1 for r in done if r["result"] in pos)
        print(f"- {g}/{len(done)} answered applications got a positive reply")
    else:
        print(f"- 0 of {len(applied)} answered yet — feed results back with `set-result`")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("log-outcome"); g.set_defaults(f=cmd_log)
    g.add_argument("--company", required=True); g.add_argument("--role", required=True)
    g.add_argument("--url", default=""); g.add_argument("--source", default="linkedin")
    g.add_argument("--score", default=None); g.add_argument("--portal", default="")
    g.add_argument("--status", default="applied", choices=STATUSES)
    g.add_argument("--cv-variant", default=""); g.add_argument("--contact-set", default="")
    g.add_argument("--keywords", default=""); g.add_argument("--note", default="")
    g.add_argument("--job-key", default="")

    g = sub.add_parser("set-result"); g.set_defaults(f=cmd_set_result)
    g.add_argument("--job-key", required=True)
    g.add_argument("--result", required=True, choices=RESULTS)
    g.add_argument("--note", default="")

    g = sub.add_parser("add-lesson"); g.set_defaults(f=cmd_add_lesson)
    g.add_argument("text")
    g.add_argument("--tag", default="general",
                   choices=["scoring", "cv", "apply", "sourcing", "general"])

    g = sub.add_parser("consolidate"); g.set_defaults(f=cmd_consolidate)
    g.add_argument("--threshold", type=int, default=3)

    sub.add_parser("kpi").set_defaults(f=cmd_kpi)
    for name, fn in (("show", cmd_show), ("stats", cmd_stats), ("pending", cmd_pending)):
        sub.add_parser(name).set_defaults(f=fn)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
