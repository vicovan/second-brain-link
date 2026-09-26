#!/usr/bin/env python3
"""
ledger.py - the target records. The one object every other part of the plugin projects.

Every fund, program, angel, strategic, grant or syndicate is ONE record in
<state root>/targets.jsonl. Every status change is ONE line in events.jsonl. Nothing
else is the source of truth: the Funding Plan, the dashboard and the target notes are
all rendered from here.

A record carries its evidence. Each claim is {v, stamp, src, at}:

    ✅   read on the target's OWN site/page, on the date in `at`
    3P   third-party only (a database, a press piece, a directory)
    📋   desk-screened from a list's one-line description — no page read
    ⚠    unverified, conflicting, or a deadline whose year is not confirmed

A list is a lead, never a source: imports create 📋 records, and the list's own
assertions are kept as `origin_text`, never promoted to claims.

Subcommands (all print JSON or a short table; all exit non-zero on a refused change):

    upsert --json '{...}'              create/merge a record (claims merge by stamp rank)
    set-claim KEY FIELD VALUE --stamp ✅ --src URL
    set-verdict KEY FILTER pass|fail|unknown|conditional --why TEXT
    set-tier KEY --tier N --fit N --why TEXT
    rescreen [--keys a,b]              re-run the filter chain from round.md, no network
    import-csv FILE --origin LABEL     Name/About/Website/Location-shaped lists → 📋 records
    import-text FILE|- --origin LABEL  pasted lists, one name per line ("Person - Fund" ok)
    set-status KEY STATUS --by founder|agent|reply [--note] [--different TEXT]
    log-app KEY [--day D]              create applications/<day>/<key>/ and mark drafted
    log-draft KEY --path P [--gmail-id ID] [--channel email]
    sent KEY [--days N]                founder confirms a draft went out → contacted
    log-outcome KEY RESULT [--note]    replied|meeting|passed|rejected|accepted|term_sheet|no_reply
    next KEY --action A --due D
    due [--days 14] [--count]          follow-ups, deadlines, stale dated claims
    list [--status s] [--tier n] [--kind k] [--json]
    show KEY
    stale                              claims past their re-verification age
    kpi                                reply / meeting / acceptance rates by tier, channel, kind
    add-lesson TEXT
    stats
    remove KEY --why TEXT              archive a duplicate/junk record to removed.jsonl (never deleted)
    snooze | mark-run                  silence the daily nudge for today / record a run
"""
import argparse, collections, csv, datetime, fcntl, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, render_dir  # noqa: E402
import founder_profile as prof  # noqa: E402

TODAY = datetime.date.today()
NOW = lambda: datetime.datetime.now().replace(microsecond=0).isoformat()  # noqa: E731

STAMPS = {"✅": 3, "3P": 2, "📋": 1, "⚠": 0}
KINDS = ("fund", "program", "angel", "strategic", "grant", "syndicate")
STATUSES = ["screened", "verified", "out", "queued", "drafted", "draft_ready", "filed",
            "contacted", "no_reply", "replied", "meeting", "passed", "accepted",
            "rejected", "term_sheet", "withdrawn"]
RESULTS = ["replied", "meeting", "passed", "rejected", "accepted", "term_sheet", "no_reply"]
TRANSITIONS = {
    "screened":    {"verified", "out", "queued"},
    "verified":    {"screened", "out", "queued"},
    "out":         {"screened", "verified"},
    "queued":      {"drafted", "out", "withdrawn", "verified"},
    "drafted":     {"filed", "draft_ready", "queued", "withdrawn"},
    "draft_ready": {"contacted", "filed", "drafted", "withdrawn"},
    "filed":       {"replied", "meeting", "accepted", "rejected", "passed", "withdrawn"},
    "contacted":   {"replied", "no_reply", "meeting", "passed", "rejected"},
    "no_reply":    {"draft_ready", "contacted", "passed", "replied"},
    "replied":     {"meeting", "passed", "accepted", "rejected"},
    "meeting":     {"term_sheet", "passed", "accepted", "rejected", "meeting"},
    "passed":      {"queued"},
    "rejected":    {"queued"},
    "accepted":    {"withdrawn"},
    "term_sheet":  {"withdrawn"},
    "withdrawn":   {"queued"},
}
# Only the founder can say something was sent. A draft the agent handed over is not
# an email that went out, and must never start a follow-up clock.
FOUNDER_ONLY = {"contacted"}
# Moving a closed door back to queued is a re-application; it must say what changed.
NEEDS_DIFFERENT = {("rejected", "queued"), ("passed", "queued")}
# Stamps age: dated facts go stale fast, a thesis slowly.
DATED_FIELDS = {"deadline", "status_open", "cohort"}
DATED_DAYS, STATIC_DAYS = 7, 30

EXCLUSION_SYNONYMS = {
    "crypto": ["crypto", "web3", "token", "blockchain", "dao", "defi", "stablecoin",
               "cardano", "nft", "on-chain"],
}
REGIONS = {
    "global": ["global", "anywhere", "worldwide", "across borders", "international",
               "any geography", "geo-agnostic", "all over the world"],
    "us": ["united states", "u.s.", "us only", "us-based", "north america", "us and canada",
           "americas", "bay area", "silicon valley", "new york", "nyc", "los angeles",
           "midwest", "pacific northwest", "oregon", "seattle", "boston", "chattanooga",
           "minnesota", "reno", "brooklyn", "la's", "san francisco"],
    "europe": ["europe", "european", "united kingdom", "uk", "london", "berlin", "paris",
               "germany", "france", "netherlands", "spain", "portugal"],
    "cee": ["cee", "central and eastern", "eastern europe", "romania", "romanian", "poland",
            "polish", "baltic", "estonia", "hungary", "bulgaria", "see "],
    "nordics": ["nordic", "finland", "sweden", "norway", "denmark"],
    "mena": ["mena", "gcc", "uae", "dubai", "abu dhabi", "saudi", "middle east"],
    "israel": ["israel", "israeli"],
    "anz": ["anz", "australia", "new zealand"],
    "asia": ["asia", "india", "singapore", "southeast asia", "japan"],
    "latam": ["latin america", "latam", "brazil", "mexico"],
}
HEADER_ALIASES = {
    "name": ["name", "fund", "fund name", "investor", "firm", "program", "organisation",
             "organization", "company"],
    "about": ["about", "description", "thesis", "focus", "notes", "summary"],
    "url": ["website", "url", "site", "link", "homepage", "web"],
    "location": ["location", "region", "geography", "hq", "country", "city"],
    "partner": ["partner", "person", "contact", "gp", "people"],
    "cheque": ["check", "cheque", "check size", "cheque size", "ticket", "amount"],
    "stage": ["stage", "stages"],
    "email": ["email", "e-mail", "contact email"],
    "portfolio": ["portfolio"],
    "crunchbase": ["crunchbase"],
}


# ------------------------------------------------------------------ storage
def root():
    r = state_root()
    r.mkdir(parents=True, exist_ok=True)
    return r


class Lock:
    def __enter__(self):
        self.f = open(root() / ".ledger.lock", "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def load():
    p = root() / "targets.jsonl"
    recs = collections.OrderedDict()
    if p.is_file():
        for line in p.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    recs[r["key"]] = r
                except (ValueError, KeyError):
                    continue
    return recs


def save(recs):
    p = root() / "targets.jsonl"
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs.values()),
                   encoding="utf-8")
    tmp.replace(p)


def event(key, frm, to, by, note=""):
    with open(root() / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "from": frm, "to": to, "by": by, "at": NOW(),
                            "note": note}, ensure_ascii=False) + "\n")


def events():
    p = root() / "events.jsonl"
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


# ------------------------------------------------------------------ helpers
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "target"


_NOISE = r"\b(the|ventures?|capital|vc|fund|partners|management|group|llc|inc)\b"


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(_NOISE, "", (s or "").lower()))


def domain(url):
    m = re.search(r"(?:https?://)?(?:www\.)?([^/\s?#]+)", (url or "").strip().lower())
    return m.group(1) if m and "." in m.group(1) else ""


def find(recs, name=None, url=None):
    n, d = norm_name(name), domain(url)
    for r in recs.values():
        if n and norm_name(r.get("name")) == n:
            return r
        if d and domain(r.get("url")) == d:
            return r
    return None


def new_record(name, kind="fund"):
    return {"key": slug(name), "kind": kind if kind in KINDS else "fund", "name": name,
            "url": "", "people": [], "claims": {}, "verdicts": {}, "overrides": {},
            "fit": None, "tier": None, "why": "", "status": "screened", "origin": [],
            "origin_text": [], "apps": [], "drafts": [], "next": None,
            "created": TODAY.isoformat(), "updated": TODAY.isoformat()}


def unique_key(recs, key):
    k, i = key, 2
    while k in recs:
        k, i = f"{key}-{i}", i + 1
    return k


def claim_wins(new, old):
    """A new claim replaces an old one when its stamp ranks higher, or ranks the same and
    is at least as recent. A ✅ is never overwritten by a 📋 import."""
    if not old:
        return True
    rn, ro = STAMPS.get(new.get("stamp"), 0), STAMPS.get(old.get("stamp"), 0)
    if rn != ro:
        return rn > ro
    return (new.get("at") or "") >= (old.get("at") or "")


def merge(rec, data):
    for k in ("name", "url", "kind", "why", "fit", "tier"):
        if data.get(k) not in (None, ""):
            rec[k] = data[k]
    for field, c in (data.get("claims") or {}).items():
        if not isinstance(c, dict):
            c = {"v": c, "stamp": "⚠"}
        c.setdefault("at", TODAY.isoformat())
        if c.get("stamp") not in STAMPS:
            c["stamp"] = "⚠"
        if claim_wins(c, rec["claims"].get(field)):
            rec["claims"][field] = c
    have = {p.get("name", "").lower() for p in rec["people"]}
    for p in data.get("people") or []:
        if isinstance(p, str):
            p = {"name": p}
        if p.get("name") and p["name"].lower() not in have:
            rec["people"].append(p)
            have.add(p["name"].lower())
    for o in data.get("origin") or []:
        if o not in rec["origin"]:
            rec["origin"].append(o)
    for t in data.get("origin_text") or []:
        if t and t not in rec["origin_text"]:
            rec["origin_text"].append(t)
    if any(STAMPS.get(c.get("stamp"), 0) == 3 for c in rec["claims"].values()) \
            and rec["status"] == "screened":
        rec["status"] = "verified"
    rec["updated"] = TODAY.isoformat()
    return rec


# ------------------------------------------------------------------ money
_MONEY = re.compile(r"([$€£])?\s*(\d+(?:[.,]\d+)?)\s*(k|m|mm|million|thousand|bn|b)?\b",
                    re.I)


def money_values(text):
    """Every amount in `text`, in units (currency symbols are treated as roughly equal —
    the floor is a screen, not an FX calculation)."""
    vals = []
    t = (text or "").replace("–", "-").replace("—", "-")
    # "0.5–5M": the unit after the range applies to both ends
    for m in re.finditer(r"([$€£])?\s*(\d+(?:\.\d+)?)\s*-\s*([$€£])?\s*(\d+(?:\.\d+)?)\s*(k|m|mm|million)\b",
                         t, re.I):
        mult = 1_000 if m.group(5).lower() == "k" else 1_000_000
        vals += [float(m.group(2)) * mult, float(m.group(4)) * mult]
    for m in _MONEY.finditer(t):
        sym, num, unit = m.group(1), m.group(2).replace(",", ""), (m.group(3) or "").lower()
        if not sym and not unit:
            continue                    # a bare number is not money
        try:
            v = float(num)
        except ValueError:
            continue
        v *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6,
              "b": 1e9, "bn": 1e9}.get(unit, 1)
        if v >= 1000:
            vals.append(v)
    return vals


def cash_range(rec):
    """(low, high) cash per cheque, net of fees when the record says so."""
    cash = (rec["claims"].get("cash") or {}).get("v")
    if isinstance(cash, dict) and cash.get("net") is not None:
        n = float(cash["net"])
        return n, n
    texts = [str((rec["claims"].get(f) or {}).get("v") or "") for f in ("cheque", "cash")]
    if not any(texts):
        texts = rec.get("origin_text") or []
    vals = [v for t in texts for v in money_values(t)]
    if not vals:
        return None, None
    joined = " ".join(texts).lower()
    if re.search(r"\bup to\b", joined) and len(vals) == 1:
        return None, vals[0]
    return min(vals), max(vals)


# ------------------------------------------------------------------ filters
def text_of(rec, fields=None):
    parts = []
    for f, c in rec["claims"].items():
        if fields is None or f in fields:
            parts.append(str(c.get("v") or ""))
    parts += rec.get("origin_text") or []
    return " ".join(parts).lower()


def regions_in(text):
    t = f" {text} "
    return {r for r, kws in REGIONS.items() if any(k in t for k in kws)}


def verdict(rec, flt, rs):
    """(verdict, why). 'unknown' passes and is marked; it never fails a record."""
    ov = (rec.get("overrides") or {}).get(flt)
    if ov:
        return ov["v"], ov.get("why", "set by hand")
    if flt == "floor":
        floor = float(rs.get("min_net_cash") or 0)
        if floor <= 0:
            return "pass", "no floor set"
        lo, hi = cash_range(rec)
        if hi is not None and hi < floor:
            return "fail", f"cheque up to {int(hi):,} < floor {int(floor):,}"
        if lo is not None and lo >= floor:
            return "pass", f"cheque from {int(lo):,}"
        return "unknown", "cheque size not established"
    if flt == "geo":
        g = (rec["claims"].get("geography") or {}).get("v")
        found = regions_in(str(g).lower() if g else text_of(rec, {"location", "geography"}))
        ok = {x.lower() for x in rs.get("geography_ok") or []}
        if not found:
            return "unknown", "geography not stated"
        if "global" in found or found & ok:
            return "pass", ", ".join(sorted(found))
        if found <= {"us"} and str(rs.get("relocation", "no")).lower() in ("ok", "yes", "open"):
            return "conditional", "US-focused — only after relocating / a US entity"
        return "fail", "invests in " + ", ".join(sorted(found))
    if flt == "thesis":
        kws = [k.lower() for k in rs.get("thesis_keywords") or []]
        off = [k.lower() for k in rs.get("off_thesis") or []]
        t = text_of(rec, {"thesis", "about", "focus"}) or text_of(rec)
        if not t.strip():
            return "unknown", "no thesis text"
        hit = [k for k in kws if re.search(r"\b" + re.escape(k) + r"\b", t)]
        bad = [k for k in off if re.search(r"\b" + re.escape(k), t)]
        if hit and bad:
            return "unknown", f"mixed — matches {', '.join(hit[:2])}; also {', '.join(bad[:2])}"
        if hit:
            return "pass", "matches " + ", ".join(hit[:3])
        if bad:
            return "fail", "off-thesis: " + ", ".join(bad[:3])
        return "unknown", "no thesis keyword matched"
    if flt == "access":
        c = str((rec["claims"].get("cold_path") or {}).get("v") or "").lower()
        if not c:
            return "unknown", "no cold path found yet"
        return ("pass", "warm intro only") if "warm" in c and "form" not in c else ("pass", c[:60])
    if flt == "entity":
        need = str((rec["claims"].get("entity_required") or {}).get("v") or "").lower()
        if not need:
            return "unknown", "entity requirement not stated"
        ok = {e.lower() for e in rs.get("entities_ok") or []} | {str(rs.get("entity_now", "")).lower()}
        if any(need.startswith(e.split("-")[0]) or e.startswith(need) for e in ok if e):
            return "pass", f"needs {need} — acceptable"
        return "fail", f"needs {need}"
    if flt == "exclusions":
        t = text_of(rec)
        for ex in rs.get("exclusions") or []:
            for kw in EXCLUSION_SYNONYMS.get(ex.lower(), [ex.lower()]):
                if re.search(r"\b" + re.escape(kw) + r"\b", t):
                    return "fail", f"excluded: {ex} ({kw})"
        return "pass", "no exclusion matched"
    return "unknown", ""


def rescreen_one(rec, rs):
    rec["verdicts"] = {}
    first_fail = None
    for flt in rs["filter_order"]:
        v, why = verdict(rec, flt, rs)
        rec["verdicts"][flt] = {"v": v, "why": why}
        if v == "fail" and first_fail is None:
            first_fail = (flt, why)
    before = rec["status"]
    if first_fail and (before in ("screened", "verified")
                       or (before == "out" and rec.get("out_by") == "rescreen")):
        rec["status"], rec["out_reason"], rec["out_by"] = "out", f"{first_fail[0]}: {first_fail[1]}", "rescreen"
    elif not first_fail and before == "out" and rec.get("out_by") == "rescreen":
        rec["status"] = "verified" if any(c.get("stamp") == "✅" for c in rec["claims"].values()) else "screened"
        rec.pop("out_reason", None)
        rec.pop("out_by", None)
    if rec["status"] != before:
        event(rec["key"], before, rec["status"], "agent", "rescreen: " + (rec.get("out_reason") or "passes"))
    rec["updated"] = TODAY.isoformat()


# ------------------------------------------------------------------ ageing
def stale_claims(rec):
    out = []
    for f, c in rec["claims"].items():
        try:
            at = datetime.date.fromisoformat((c.get("at") or "")[:10])
        except ValueError:
            continue
        limit = DATED_DAYS if f in DATED_FIELDS else STATIC_DAYS
        if (TODAY - at).days > limit:
            out.append(f)
    return out


def deadline_of(rec):
    c = rec["claims"].get("deadline") or {}
    v = c.get("v")
    if isinstance(v, dict):
        v = v.get("date")
    try:
        return datetime.date.fromisoformat(str(v)[:10]), bool(c.get("year_confirmed"))
    except (TypeError, ValueError):
        return None, False


# ------------------------------------------------------------------ commands
def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def need(recs, key):
    if key not in recs:
        hit = find(recs, name=key)
        if hit:
            return hit
        sys.exit(f"no such target: {key}")
    return recs[key]


def cmd_upsert(a):
    data = json.loads(a.json)
    with Lock():
        recs = load()
        rec = recs.get(data.get("key", "")) or find(recs, data.get("name"), data.get("url"))
        if rec is None:
            if not data.get("name"):
                sys.exit("upsert needs a name for a new record")
            rec = new_record(data["name"], data.get("kind", "fund"))
            rec["key"] = unique_key(recs, data.get("key") or rec["key"])
            recs[rec["key"]] = rec
            event(rec["key"], None, rec["status"], "agent", "created")
        merge(rec, data)
        save(recs)
    out({"key": rec["key"], "status": rec["status"]})


def cmd_set_claim(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        c = {"v": a.value, "stamp": a.stamp, "src": a.src, "at": a.at or TODAY.isoformat()}
        if a.year_confirmed:
            c["year_confirmed"] = True
        merge(rec, {"claims": {a.field: c}})
        save(recs)
    out({"key": rec["key"], a.field: rec["claims"].get(a.field)})


def cmd_set_verdict(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        rec.setdefault("overrides", {})[a.filter] = {"v": a.value, "why": a.why}
        rescreen_one(rec, prof.round_settings())
        save(recs)
    out({"key": rec["key"], "verdicts": rec["verdicts"], "status": rec["status"]})


def cmd_set_tier(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        if a.tier is not None:
            rec["tier"] = a.tier
        if a.fit is not None:
            rec["fit"] = a.fit
        if a.why:
            rec["why"] = a.why
        rec["updated"] = TODAY.isoformat()
        save(recs)
    out({"key": rec["key"], "tier": rec["tier"], "fit": rec["fit"]})


def cmd_rescreen(a):
    rs = prof.round_settings()
    keys = set(a.keys.split(",")) if a.keys else None
    with Lock():
        recs = load()
        for r in recs.values():
            if keys is None or r["key"] in keys:
                rescreen_one(r, rs)
        save(recs)
    c = collections.Counter(r["status"] for r in recs.values())
    reasons = collections.Counter((r.get("out_reason") or "").split(":")[0]
                                  for r in recs.values() if r["status"] == "out")
    out({"statuses": dict(c), "out_by_filter": dict(reasons),
         "filter_order": rs["filter_order"]})


def _header_map(headers):
    m = {}
    for h in headers:
        hl = (h or "").strip().lower()
        for canon, al in HEADER_ALIASES.items():
            if hl in al and canon not in m:
                m[canon] = h
    return m


def _ingest(recs, name, origin, about="", url="", location="", partner="", cheque="",
            email="", kind="fund"):
    name = (name or "").strip()
    if not name:
        return None, False
    rec = find(recs, name, url)
    created = rec is None
    if created:
        rec = new_record(name, kind)
        rec["key"] = unique_key(recs, rec["key"])
        recs[rec["key"]] = rec
        event(rec["key"], None, "screened", "agent", f"imported from {origin}")
    texts = [t for t in (about, f"Location: {location}" if location else "",
                         f"Cheque: {cheque}" if cheque else "") if t]
    data = {"origin": [origin], "origin_text": texts}
    if url and not rec.get("url"):
        u = url.strip()
        data["url"] = u if u.startswith("http") else "https://" + u
    if partner:
        data["people"] = [{"name": partner.strip(), "role": "partner"}]
    if email:
        data["claims"] = {"contact_email": {"v": email.strip(), "stamp": "📋", "src": origin}}
    merge(rec, data)
    return rec, created


def cmd_import_csv(a):
    with open(a.file, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("empty CSV")
    hm = _header_map(rows[0].keys())
    if "name" not in hm:
        sys.exit(f"no name column found in {list(rows[0].keys())}")
    made = merged = 0
    with Lock():
        recs = load()
        for r in rows:
            g = lambda k: (r.get(hm[k]) or "").strip() if k in hm else ""  # noqa: E731
            rec, created = _ingest(recs, g("name"), a.origin, g("about"), g("url"),
                                   g("location"), g("partner"), g("cheque"), g("email"),
                                   a.kind)
            if rec is None:
                continue
            made += created
            merged += not created
        if not a.no_rescreen:
            rs = prof.round_settings()
            for r in recs.values():
                if a.origin in r["origin"]:
                    rescreen_one(r, rs)
        save(recs)
    out({"rows": len(rows), "created": made, "merged": merged, "columns": hm})


def cmd_import_text(a):
    text = sys.stdin.read() if a.file == "-" else pathlib.Path(a.file).read_text(encoding="utf-8")
    made = merged = 0
    with Lock():
        recs = load()
        for raw in text.split("\n"):
            # bullets and list NUMBERS ("1.", "2)") — never a leading number that is part of
            # the name ("500 Global"), which a bare digit strip used to eat
            line = re.sub(r"^\s*(?:[>*•\-–🔥📱➞→]+\s*|\d{1,3}[.)]\s+)+", "", raw).strip()
            if not line or line.endswith(":") or len(line) > 140 or line.startswith("http"):
                continue
            person, name = "", line
            m = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", line)
            if m and len(m.group(1).split()) <= 4:
                person, name = m.group(1).strip(), m.group(2).strip()
            name = re.sub(r"\s*[:|(].*$", "", name).strip()
            rec, created = _ingest(recs, name, a.origin, about=line if person else "",
                                   partner=person, kind=a.kind)
            if rec is None:
                continue
            made += created
            merged += not created
        save(recs)
    out({"created": made, "merged": merged})


def _transition(rec, to, by, note="", different=""):
    frm = rec["status"]
    if to == frm and to != "meeting":
        return
    if to not in STATUSES:
        sys.exit(f"unknown status {to}; one of {STATUSES}")
    if to not in TRANSITIONS.get(frm, set()):
        sys.exit(f"refused: {rec['key']} cannot go {frm} → {to}")
    if to in FOUNDER_ONLY and by != "founder":
        sys.exit(f"refused: only the founder can mark {rec['key']} as {to} "
                 "(a handed-over draft is not a sent email)")
    if (frm, to) in NEEDS_DIFFERENT and not different.strip():
        sys.exit(f"refused: re-queueing {rec['key']} after '{frm}' needs --different "
                 "naming what is materially different this time")
    rec["status"] = to
    if different:
        rec["reapply_because"] = different
    rec["updated"] = TODAY.isoformat()
    event(rec["key"], frm, to, by, note or different)


def cmd_set_status(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        _transition(rec, a.status, a.by, a.note or "", a.different or "")
        save(recs)
    out({"key": rec["key"], "status": rec["status"]})


def cmd_log_app(a):
    day = a.day or TODAY.isoformat()
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        d = render_dir() / "applications" / day / rec["key"]
        d.mkdir(parents=True, exist_ok=True)
        rel = f"applications/{day}/{rec['key']}"
        if rel not in rec["apps"]:
            rec["apps"].append(rel)
        if rec["status"] in ("screened", "verified"):
            _transition(rec, "queued", "agent", "picked for application")
        if rec["status"] == "queued":
            _transition(rec, "drafted", "agent", "application folder created")
        save(recs)
    out({"key": rec["key"], "folder": str(d), "status": rec["status"]})


def cmd_log_draft(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        entry = {"path": a.path, "gmail_draft_id": a.gmail_id or None,
                 "channel": a.channel, "at": TODAY.isoformat()}
        rec["drafts"] = [d for d in rec["drafts"] if d.get("path") != a.path] + [entry]
        if rec["status"] in ("screened", "verified"):
            _transition(rec, "queued", "agent", "picked for outreach")
        if rec["status"] in ("queued",):
            _transition(rec, "drafted", "agent", "draft written")
        if rec["status"] in ("drafted", "no_reply"):
            _transition(rec, "draft_ready", "agent", f"{a.channel} draft handed over")
        save(recs)
    out({"key": rec["key"], "status": rec["status"], "draft": entry})


def cmd_sent(a):
    days = a.days or int(prof.round_settings().get("followup_days", 7) or 7)
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        _transition(rec, "contacted", "founder", a.note or "founder confirmed sent")
        rec["next"] = {"action": "follow-up",
                       "due": (TODAY + datetime.timedelta(days=days)).isoformat()}
        save(recs)
    out({"key": rec["key"], "status": rec["status"], "next": rec["next"]})


def cmd_log_outcome(a):
    if a.result not in RESULTS:
        sys.exit(f"result must be one of {RESULTS}")
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        _transition(rec, a.result, "reply", a.note or "")
        if a.result in ("passed", "rejected", "accepted", "term_sheet"):
            rec["next"] = None
        save(recs)
    out({"key": rec["key"], "status": rec["status"]})


def cmd_next(a):
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        rec["next"] = {"action": a.action, "due": a.due}
        save(recs)
    out({"key": rec["key"], "next": rec["next"]})


def due_items(days):
    recs = load()
    horizon = TODAY + datetime.timedelta(days=days)
    items = []
    for r in recs.values():
        if r["status"] in ("out", "withdrawn", "passed", "rejected", "accepted", "term_sheet"):
            continue
        n = r.get("next") or {}
        try:
            nd = datetime.date.fromisoformat(n.get("due", "")[:10]) if n.get("due") else None
        except ValueError:
            nd = None
        if nd and nd <= horizon:
            items.append({"key": r["key"], "name": r["name"], "type": n.get("action", "follow-up"),
                          "due": nd.isoformat(), "days": (nd - TODAY).days})
        dl, yc = deadline_of(r)
        if dl and TODAY <= dl <= horizon and r["status"] not in ("filed", "contacted"):
            items.append({"key": r["key"], "name": r["name"], "type": "deadline",
                          "due": dl.isoformat(), "days": (dl - TODAY).days,
                          "year_confirmed": yc})
        st = [f for f in stale_claims(r) if f in DATED_FIELDS]
        if st and r["status"] not in ("screened",):
            items.append({"key": r["key"], "name": r["name"], "type": "re-verify",
                          "fields": st, "due": TODAY.isoformat(), "days": 0})
    return sorted(items, key=lambda x: (x["days"], x["type"]))


def cmd_due(a):
    items = due_items(a.days)
    if a.count:
        print(len(items))
        return
    out(items)


def cmd_list(a):
    recs = load()
    rows = [r for r in recs.values()
            if (not a.status or r["status"] in a.status.split(","))
            and (a.tier is None or r.get("tier") == a.tier)
            and (not a.kind or r["kind"] == a.kind)]
    if a.json:
        out(rows)
        return
    for r in sorted(rows, key=lambda r: (r.get("tier") or 9, -(r.get("fit") or 0), r["name"])):
        print(f"{r['key']:<34} {r['status']:<11} T{r.get('tier') or '-'} fit {r.get('fit') or '-':<3} "
              f"{r['name']}")


def cmd_show(a):
    recs = load()
    rec = need(recs, a.key)
    rec = dict(rec)
    rec["events"] = [e for e in events() if e["key"] == rec["key"]]
    out(rec)


def cmd_stale(a):
    out([{"key": r["key"], "fields": stale_claims(r)} for r in load().values() if stale_claims(r)])


def _rate(rows, pred):
    n = len(rows)
    return f"{sum(1 for r in rows if pred(r))}/{n}" if n else "0/0"


def cmd_kpi(a):
    recs = list(load().values())
    touched = [r for r in recs if r["status"] in
               ("filed", "contacted", "no_reply", "replied", "meeting", "passed", "accepted",
                "rejected", "term_sheet")]
    replied = lambda r: r["status"] in ("replied", "meeting", "passed", "accepted", "rejected", "term_sheet")  # noqa: E731
    met = lambda r: r["status"] in ("meeting", "term_sheet", "accepted")  # noqa: E731
    by = {}
    for dim in ("tier", "kind"):
        g = collections.defaultdict(list)
        for r in touched:
            g[str(r.get(dim) or "-")].append(r)
        by[dim] = {k: {"n": len(v), "replied": _rate(v, replied), "meeting": _rate(v, met)}
                   for k, v in sorted(g.items())}
    ch = collections.defaultdict(list)
    for r in touched:
        c = (r["drafts"][-1]["channel"] if r.get("drafts") else ("form" if r.get("apps") else "-"))
        ch[c].append(r)
    by["channel"] = {k: {"n": len(v), "replied": _rate(v, replied), "meeting": _rate(v, met)}
                     for k, v in sorted(ch.items())}
    out({"targets": len(recs), "touched": len(touched),
         "replied": _rate(touched, replied), "meetings": _rate(touched, met),
         "accepted": sum(1 for r in recs if r["status"] == "accepted"),
         "term_sheets": sum(1 for r in recs if r["status"] == "term_sheet"),
         "by": by})


def cmd_add_lesson(a):
    p = root() / "lessons.md"
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"- {TODAY.isoformat()} — {a.text.strip()}\n")
    print(p)


def cmd_stamp(a):
    """snooze / mark-run: one date per file, read by the daily nudge."""
    name = {"snooze": "snooze.txt", "mark-run": "last-run.txt"}[a.cmd]
    (root() / name).write_text(TODAY.isoformat() + "\n", encoding="utf-8")
    print(f"{name} = {TODAY.isoformat()}")


def cmd_remove(a):
    """Take a record out of the ledger WITHOUT losing it: it is appended to removed.jsonl
    (with the reason) and an event is logged. Nothing is ever deleted."""
    with Lock():
        recs = load()
        rec = need(recs, a.key)
        rec["removed_because"] = a.why
        with open(root() / "removed.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        del recs[rec["key"]]
        event(rec["key"], rec["status"], "removed", "founder" if a.by == "founder" else "agent", a.why)
        save(recs)
    out({"removed": rec["key"], "why": a.why, "archive": str(root() / "removed.jsonl")})


def cmd_stats(a):
    recs = load()
    out({"targets": len(recs),
         "by_status": dict(collections.Counter(r["status"] for r in recs.values())),
         "by_kind": dict(collections.Counter(r["kind"] for r in recs.values())),
         "by_stamp": dict(collections.Counter(c.get("stamp") for r in recs.values()
                                              for c in r["claims"].values())),
         "state_root": str(root())})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("upsert"); g.add_argument("--json", required=True); g.set_defaults(f=cmd_upsert)
    g = sub.add_parser("set-claim"); g.add_argument("key"); g.add_argument("field"); g.add_argument("value")
    g.add_argument("--stamp", default="⚠", choices=list(STAMPS)); g.add_argument("--src")
    g.add_argument("--at"); g.add_argument("--year-confirmed", action="store_true"); g.set_defaults(f=cmd_set_claim)
    g = sub.add_parser("set-verdict"); g.add_argument("key"); g.add_argument("filter", choices=prof.FILTERS)
    g.add_argument("value", choices=["pass", "fail", "unknown", "conditional"]); g.add_argument("--why", default="")
    g.set_defaults(f=cmd_set_verdict)
    g = sub.add_parser("set-tier"); g.add_argument("key"); g.add_argument("--tier", type=int)
    g.add_argument("--fit", type=int); g.add_argument("--why"); g.set_defaults(f=cmd_set_tier)
    g = sub.add_parser("rescreen"); g.add_argument("--keys"); g.set_defaults(f=cmd_rescreen)
    g = sub.add_parser("import-csv"); g.add_argument("file"); g.add_argument("--origin", required=True)
    g.add_argument("--kind", default="fund", choices=KINDS); g.add_argument("--no-rescreen", action="store_true")
    g.set_defaults(f=cmd_import_csv)
    g = sub.add_parser("import-text"); g.add_argument("file"); g.add_argument("--origin", required=True)
    g.add_argument("--kind", default="fund", choices=KINDS); g.set_defaults(f=cmd_import_text)
    g = sub.add_parser("set-status"); g.add_argument("key"); g.add_argument("status")
    g.add_argument("--by", required=True, choices=["founder", "agent", "reply"])
    g.add_argument("--note"); g.add_argument("--different"); g.set_defaults(f=cmd_set_status)
    g = sub.add_parser("log-app"); g.add_argument("key"); g.add_argument("--day"); g.set_defaults(f=cmd_log_app)
    g = sub.add_parser("log-draft"); g.add_argument("key"); g.add_argument("--path", required=True)
    g.add_argument("--gmail-id"); g.add_argument("--channel", default="email",
                                                 choices=["email", "intro", "form", "linkedin", "x", "other"])
    g.set_defaults(f=cmd_log_draft)
    g = sub.add_parser("sent"); g.add_argument("key"); g.add_argument("--days", type=int)
    g.add_argument("--note"); g.set_defaults(f=cmd_sent)
    g = sub.add_parser("log-outcome"); g.add_argument("key"); g.add_argument("result")
    g.add_argument("--note"); g.set_defaults(f=cmd_log_outcome)
    g = sub.add_parser("next"); g.add_argument("key"); g.add_argument("--action", required=True)
    g.add_argument("--due", required=True); g.set_defaults(f=cmd_next)
    g = sub.add_parser("due"); g.add_argument("--days", type=int, default=14)
    g.add_argument("--count", action="store_true"); g.set_defaults(f=cmd_due)
    g = sub.add_parser("list"); g.add_argument("--status"); g.add_argument("--tier", type=int)
    g.add_argument("--kind"); g.add_argument("--json", action="store_true"); g.set_defaults(f=cmd_list)
    g = sub.add_parser("show"); g.add_argument("key"); g.set_defaults(f=cmd_show)
    sub.add_parser("stale").set_defaults(f=cmd_stale)
    sub.add_parser("kpi").set_defaults(f=cmd_kpi)
    g = sub.add_parser("add-lesson"); g.add_argument("text"); g.set_defaults(f=cmd_add_lesson)
    sub.add_parser("stats").set_defaults(f=cmd_stats)
    g = sub.add_parser("remove"); g.add_argument("key"); g.add_argument("--why", required=True)
    g.add_argument("--by", default="agent", choices=["founder", "agent"]); g.set_defaults(f=cmd_remove)
    sub.add_parser("snooze").set_defaults(f=cmd_stamp)
    sub.add_parser("mark-run").set_defaults(f=cmd_stamp)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
