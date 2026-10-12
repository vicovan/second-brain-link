#!/usr/bin/env python3
"""
threads.py - public conversations worth joining: the engagement twin of the target ledger.

Investors, operators and future customers argue about the founder's problem space in public —
LinkedIn posts, X threads, Hacker News, Reddit. A useful comment in the right thread is a warm
touch that no cold email buys. This keeps the threads the agent found, the comment it drafted
for each, and whether the founder posted it.

    <state root>/threads.jsonl          one record per thread (id = hash of the canonical URL)
    <state root>/engage-run.txt         today's date once the day's sweep is done (routine gate)
    <fundraising layer>/profile/engage.md   what to look for (topics, names, windows) — the founder's
    <fundraising layer>/engage/<YYYY-MM-DD>/<Author> — <topic>.md   one comment note per thread

    python3 threads.py queries [--limit N]          search strings from engage.md + Tier 1–2 people
    python3 threads.py add --url U --platform P --author A --title T [--posted D] [--topic T]
                           [--engagement TEXT] [--question Q ...] [--angle A] [--fit N]
                           [--investor-key KEY] [--unreadable]
    python3 threads.py draft ID --file COMMENT.txt [--day D]   check + write the comment note
    python3 threads.py check --file COMMENT.txt     the comment rules alone (exit 1 on red)
    python3 threads.py posted ID                    FOUNDER ONLY — "I posted the comment on <id>"
    python3 threads.py skip ID --why TEXT
    python3 threads.py list [--status S] [--json]
    python3 threads.py due [--count]                drafted but not posted (oldest first)
    python3 threads.py mark-run | snooze            stamp today (the routine's only_when gate)

Nothing here posts, likes, follows or messages anyone. The agent never logs in to a social
network and never drives one in a browser: it reads public pages, and the comment note carries
an ↗ link to the thread and a ✓ button that types "I posted the comment on <id>" into the chat —
the founder's own turn, the only way a thread becomes `posted`.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, sys, tempfile
from urllib.parse import urlsplit, urlunsplit, quote

HERE = os.path.dirname(os.path.abspath(__file__))
# the shared library: a sibling skill in the Claude packaging, the same folder in Codex's
for cand in (HERE, os.path.join(HERE, "..", "..", "raise-research", "scripts")):
    if os.path.isfile(os.path.join(cand, "ledger.py")):
        sys.path.insert(0, os.path.abspath(cand))
        break
else:
    sys.exit("threads.py: cannot find the shared scripts (ledger.py)")

import ledger as L  # noqa: E402
import founder_profile as prof  # noqa: E402
from paths import state_root, render_dir  # noqa: E402
from lint_claims import lint  # noqa: E402

TODAY = datetime.date.today().isoformat()
FILE = "threads.jsonl"
STAMP = "engage-run.txt"
SNOOZE = "snooze.txt"
STATUSES = ("found", "drafted", "posted", "skipped")
PLATFORMS = ("linkedin", "x", "hn", "reddit", "other")
SAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')

ENGAGE_DEFAULTS = {
    "topics": [],            # phrases the founder's market argues about
    "adjacent": [],          # products / projects whose threads the founder's buyers read
    "people": [],            # people whose threads are worth joining (investors, operators)
    "platforms": ["linkedin", "x", "hn", "reddit"],
    "window_days": 21,       # a thread older than this is history, not a conversation
    "max_per_run": 5,        # a few considered comments beat a feed of them
    "max_comment_chars": 1200,
}
# Phrases that turn a comment into an ad. The playbook explains why; the check enforces it.
PITCH = ["check out", "dm me", "link in bio", "book a demo", "sign up", "we're hiring",
         "shameless plug", "disclaimer: i'm the founder", "try it free", "our product",
         "game changer", "game-changer", "revolutionary", "great post", "love this", "so true"]


# ------------------------------------------------------------------ storage
def path():
    r = state_root()
    r.mkdir(parents=True, exist_ok=True)
    return r / FILE


def load():
    out = {}
    try:
        for line in path().read_text(encoding="utf-8").splitlines():
            if line.strip():
                t = json.loads(line)
                out[t["id"]] = t
    except OSError:
        pass
    return out


def save(recs):
    with L.Lock():
        tmp = path().with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in recs.values()),
                       encoding="utf-8")
        tmp.replace(path())


# Share links carry tracking parameters; a thread's identity can live in the query (HN's ?id=).
TRACKING = re.compile(r"^(utm_\w+|rcm|trk\w*|origin|highlighted\w*|s|t|ref\w*|fbclid|gclid|si)$", re.I)


def canon(url):
    """The same post reached by two links is one thread: drop tracking parameters, the fragment,
    `www.` and a trailing slash — but keep any query that names the thread."""
    s = urlsplit(url.strip())
    host = s.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    q = "&".join(sorted(kv for kv in s.query.split("&")
                        if kv and not TRACKING.match(kv.split("=", 1)[0])))
    return urlunsplit((s.scheme.lower() or "https", host, s.path.rstrip("/"), q, ""))


def tid(url):
    return "t-" + hashlib.sha1(canon(url).encode("utf-8")).hexdigest()[:8]


def engage_settings(pdir=None):
    s = dict(ENGAGE_DEFAULTS)
    txt = prof.read("engage.md", pdir)
    if txt:
        for k, v in prof.frontmatter(txt).items():
            if k in s:
                s[k] = v if not isinstance(s[k], list) or isinstance(v, list) else [v]
    return s


def product_names(pdir=None):
    """The founder's product name(s): company.md's H1 and its `name:`/`product:` frontmatter."""
    txt = prof.read("company.md", pdir) or ""
    names = set()
    fm = prof.frontmatter(txt)
    for k in ("name", "product", "company"):
        if isinstance(fm.get(k), str) and fm[k].strip():
            names.add(fm[k].strip())
    m = re.search(r"^#\s+(.+)$", txt, re.M)
    if m:
        names.add(m.group(1).strip())
    return sorted(n for n in names if len(n) >= 2)


# ------------------------------------------------------------------ the comment rules
def check_comment(text, pdir=None, limit=None):
    """Red stops the draft; amber is reported. Facts go through the same lint as an email."""
    red, amber = [], []
    s = engage_settings(pdir)
    limit = limit or int(s["max_comment_chars"])
    body = text.strip()
    if not body:
        return {"ok": False, "red": ["the comment is empty"], "amber": []}
    if len(body) > limit:
        red.append(f"{len(body)} characters > {limit} — a comment is not a post; cut it")
    low = body.lower()
    for p in PITCH:
        if p in low:
            red.append(f"«{p}» reads as a pitch or as filler — say something the thread does not know yet")
    mentions = sum(len(re.findall(r"(?<!\w)" + re.escape(n.lower()) + r"(?!\w)", low)) for n in product_names(pdir))
    if mentions > 1:
        red.append(f"the product is named {mentions} times — at most once, and only where it answers the thread")
    links = re.findall(r"https?://\S+", body)
    if len(links) > 1:
        red.append(f"{len(links)} links — at most one, and only when the thread asked for it")
    elif links:
        amber.append("a link in a comment is often down-ranked — keep it only if someone asked for it")
    if len(re.findall(r"(?<!\w)#\w+", body)) > 0:
        amber.append("hashtags in a comment read as a post template — drop them")
    if not re.search(r"\?|\b(we|i)\s+(found|saw|learned|tried|built|ran|hit|measured)\b", low):
        amber.append("no question and no first-hand experience — add what you saw, or ask the thread something real")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "comment.md"
        f.write_text(body, encoding="utf-8")
        g = lint([str(f)], pdir)
    red += [r.replace("comment.md · comment.md: ", "") for r in g["red"]]
    amber += g["amber"]
    return {"ok": not red, "red": red, "amber": amber, "chars": len(body)}


# ------------------------------------------------------------------ commands
def cmd_queries(a):
    s = engage_settings()
    plats = [p for p in s["platforms"] if p in PLATFORMS]
    site = {"linkedin": "site:linkedin.com/posts", "x": "site:x.com",
            "hn": "site:news.ycombinator.com", "reddit": "site:reddit.com"}
    terms = list(s["topics"]) + list(s["adjacent"])
    out = [f'{site[p]} "{t}"' for t in terms for p in plats if p in site]
    people = list(s["people"])
    for r in L.load().values():
        if r.get("tier") in (1, 2) and r["status"] not in ("out", "withdrawn"):
            who = (r.get("claims", {}).get("partner") or {}).get("v")
            if who:
                people.append(str(who))
    out += [f'site:linkedin.com/posts "{p}"' for p in dict.fromkeys(people)]
    print(json.dumps({"window_days": s["window_days"], "max_per_run": s["max_per_run"],
                      "queries": out[: a.limit] if a.limit else out}, indent=1, ensure_ascii=False))


def cmd_add(a):
    recs = load()
    i = tid(a.url)
    s = engage_settings()
    if a.posted:
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(a.posted[:10])).days
        except ValueError:
            sys.exit(f"--posted must be YYYY-MM-DD, got {a.posted}")
        if age > int(s["window_days"]) and not a.force:
            sys.exit(f"{a.posted} is {age} days old (> window_days {s['window_days']}) — the conversation "
                     "has moved on; --force only if it is still active")
    if a.platform not in PLATFORMS:
        sys.exit(f"--platform must be one of {', '.join(PLATFORMS)}")
    is_new = i not in recs
    t = recs.get(i) or {"id": i, "url": canon(a.url), "found": TODAY, "status": "found"}
    t.update({k: v for k, v in {
        "platform": a.platform, "author": a.author, "title": a.title, "posted": a.posted,
        "topic": a.topic, "engagement": a.engagement, "angle": a.angle, "fit": a.fit,
        "investor_key": a.investor_key}.items() if v not in (None, "")})
    if a.question:
        t["questions"] = list(dict.fromkeys((t.get("questions") or []) + a.question))
    t["readable"] = not a.unreadable
    recs[i] = t
    save(recs)
    print(json.dumps({"id": i, "status": t["status"], "new": is_new}))


def note_title(t):
    who = SAFE.sub("", t.get("author") or "thread").strip()[:40]
    topic = SAFE.sub("", t.get("topic") or t.get("title") or t["id"]).strip()[:50]
    return f"{who} — {topic}"


def comment_note(t, body, res, day):
    ask = quote(f"I posted the comment on {t['id']}", safe="")
    fm = ["---", "type: fundraising-comment", f"thread: {t['id']}", f"platform: {t.get('platform', '')}",
          f"url: {t['url']}", f"author: \"{(t.get('author') or '').replace(chr(34), '')}\"",
          f"posted: {t.get('posted') or ''}", f"drafted: {day}", "status: drafted",
          f"fit: {t.get('fit') or ''}", "tags: [fundraising, engage]", "---", ""]
    out = fm + [f"# {note_title(t)}\n",
                f"[↗ Open the thread]({t['url']}) · [✓ I posted it](sbl-ask:{ask})\n",
                "Nothing is posted for you: open the thread, paste the comment, post it yourself, "
                "then press ✓ (or tell the agent).\n",
                "## The thread\n",
                f"- **{t.get('title') or '—'}** — {t.get('author') or '—'} on {t.get('platform') or '—'}"
                + (f", {t['posted']}" if t.get("posted") else "")
                + (f" · {t['engagement']}" if t.get("engagement") else ""),
                ("- ⚠ the page could not be read in full — check the thread before posting"
                 if not t.get("readable", True) else "")]
    if t.get("questions"):
        out.append("\n**Open questions in the thread**\n")
        out += [f"- {q}" for q in t["questions"]]
    if t.get("angle"):
        out.append(f"\n**Angle:** {t['angle']}")
    if t.get("investor_key"):
        out.append(f"\n**Why this one:** the author is on the target list — `{t['investor_key']}`")
    out += ["\n## Comment — paste this\n", "```text", body.strip(), "```",
            f"\n{res['chars']} characters · rules: " + ("green" if res["ok"] else "RED")]
    if res["amber"]:
        out += [f"- amber: {x}" for x in res["amber"]]
    return "\n".join(x for x in out if x is not None) + "\n"


def cmd_draft(a):
    recs = load()
    t = recs.get(a.id) or sys.exit(f"no thread {a.id}")
    body = pathlib.Path(a.file).read_text(encoding="utf-8")
    res = check_comment(body)
    if not res["ok"]:
        print(json.dumps(res, indent=1, ensure_ascii=False))
        sys.exit(1)
    day = a.day or TODAY
    rel = f"engage/{day}/{note_title(t)}.md"
    p = render_dir() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(comment_note(t, body, res, day), encoding="utf-8")
    t.update({"status": "drafted", "note": rel, "drafted": day})
    save(recs)
    print(json.dumps({"id": t["id"], "note": rel, "chars": res["chars"], "amber": res["amber"]},
                     ensure_ascii=False))


def cmd_check(a):
    res = check_comment(pathlib.Path(a.file).read_text(encoding="utf-8"))
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(0 if res["ok"] else 1)


def _set_note_status(t, status):
    if not t.get("note"):
        return
    p = render_dir() / t["note"]
    try:
        txt = p.read_text(encoding="utf-8")
        p.write_text(re.sub(r"^status: \w+$", f"status: {status}", txt, count=1, flags=re.M),
                     encoding="utf-8")
    except OSError:
        pass


def cmd_posted(a):
    recs = load()
    t = recs.get(a.id) or sys.exit(f"no thread {a.id}")
    if t["status"] != "drafted":
        sys.exit(f"{a.id} is {t['status']} — only a drafted comment can be posted")
    t.update({"status": "posted", "posted_at": TODAY,
              "check_replies": (datetime.date.today() + datetime.timedelta(days=2)).isoformat()})
    _set_note_status(t, "posted")
    save(recs)
    print(json.dumps({"id": a.id, "status": "posted", "check_replies": t["check_replies"]}))


def cmd_skip(a):
    recs = load()
    t = recs.get(a.id) or sys.exit(f"no thread {a.id}")
    if t["status"] == "posted":
        sys.exit(f"{a.id} was posted — nothing to skip")
    t.update({"status": "skipped", "why": a.why})
    _set_note_status(t, "skipped")
    save(recs)
    print(json.dumps({"id": a.id, "status": "skipped"}))


def due_items():
    return sorted([t for t in load().values() if t["status"] == "drafted"],
                  key=lambda t: t.get("drafted") or "")


def cmd_due(a):
    items = due_items()
    if a.count:
        print(len(items))
        return
    for t in items:
        print(f"{t['id']}  {t.get('drafted')}  {note_title(t)}  {t['url']}")


def cmd_list(a):
    rows = [t for t in load().values() if not a.status or t["status"] == a.status]
    rows.sort(key=lambda t: (t.get("found") or "", t["id"]), reverse=True)
    if a.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return
    for t in rows:
        print(f"{t['id']}  {t['status']:8} {t.get('fit') or '—':>3}  {note_title(t)}")


def _stamp(name):
    (state_root() / name).parent.mkdir(parents=True, exist_ok=True)
    (state_root() / name).write_text(TODAY, encoding="utf-8")
    print(f"{name} = {TODAY}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queries"); q.add_argument("--limit", type=int, default=0)
    d = sub.add_parser("add")
    d.add_argument("--url", required=True); d.add_argument("--platform", required=True)
    d.add_argument("--author", default=""); d.add_argument("--title", default="")
    d.add_argument("--posted", default=""); d.add_argument("--topic", default="")
    d.add_argument("--engagement", default=""); d.add_argument("--question", action="append")
    d.add_argument("--angle", default=""); d.add_argument("--fit", type=int)
    d.add_argument("--investor-key", default=""); d.add_argument("--unreadable", action="store_true")
    d.add_argument("--force", action="store_true")
    r = sub.add_parser("draft"); r.add_argument("id"); r.add_argument("--file", required=True)
    r.add_argument("--day")
    c = sub.add_parser("check"); c.add_argument("--file", required=True)
    p = sub.add_parser("posted"); p.add_argument("id")
    s = sub.add_parser("skip"); s.add_argument("id"); s.add_argument("--why", required=True)
    li = sub.add_parser("list"); li.add_argument("--status", choices=STATUSES)
    li.add_argument("--json", action="store_true")
    du = sub.add_parser("due"); du.add_argument("--count", action="store_true")
    sub.add_parser("mark-run"); sub.add_parser("snooze")
    a = ap.parse_args(argv)
    if a.cmd == "mark-run":
        return _stamp(STAMP)
    if a.cmd == "snooze":
        return _stamp(SNOOZE)
    {"queries": cmd_queries, "add": cmd_add, "draft": cmd_draft, "check": cmd_check,
     "posted": cmd_posted, "skip": cmd_skip, "list": cmd_list, "due": cmd_due}[a.cmd](a)


if __name__ == "__main__":
    main()
