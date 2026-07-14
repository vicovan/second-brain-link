#!/usr/bin/env python3
"""
common.py — the source-agnostic core of Second Brain Link.

Every source adapter (LinkedIn, Facebook, Instagram, Google…) reads its own
export format and pushes records into a shared `Collector` using a small set of
canonical record types. The builder then renders ONE unified Obsidian vault from
the collector, regardless of how many sources fed it. Adding a new source = a new
adapter that fills the same collector. Nothing here is source-specific.

Privacy is enforced at the collector boundary: it refuses to store third-party
emails/phones, and message *content* can only enter as a derived signal — never
the body.
"""

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


# --- generated-file manifest context (lives HERE, not in build_vault, because
# emitters import build_vault as a SEPARATE module object — module globals there
# are stale across the two copies; sources.common is imported once). ------------
MANIFEST_CTX = None   # {"root": Path, "files": {relpath: sha256}} while emitting


def sha256_text(text: str) -> str:
    return hashlib.sha256((text.rstrip() + "\n").encode("utf-8")).hexdigest()


def manifest_begin(root):
    global MANIFEST_CTX
    MANIFEST_CTX = {"root": Path(root).resolve(), "files": {}}


def manifest_take():
    """Return and clear the active manifest context."""
    global MANIFEST_CTX
    ctx = MANIFEST_CTX
    MANIFEST_CTX = None
    return ctx


def record_write(path, text):
    """Record a generated file into the active manifest (no-op outside a build)."""
    if MANIFEST_CTX is None:
        return
    try:
        rel = Path(path).resolve().relative_to(MANIFEST_CTX["root"])
    except ValueError:
        return
    MANIFEST_CTX["files"][str(rel).replace("\\", "/")] = sha256_text(text)


class SearchQuery(str):
    """A search query string that ALSO carries provenance (`source`, `date`).
    Subclassing str keeps every legacy reader working (`" ".join`, f-strings,
    slicing) while the renderer can group by source and show dates."""
    source = ""
    date = ""

    def __new__(cls, q, source="", date=""):
        s = super().__new__(cls, q)
        s.source = source
        s.date = date
        return s

# ---------------------------------------------------------------------------
# normalization + Obsidian-safe naming (shared by all sources)
# ---------------------------------------------------------------------------

def nk(s: str) -> str:
    """Normalize a name/string to a comparison key: lowercase, alphanumerics only.
    This is the primary entity-resolution key (people/places merge by nk(name))."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def norm_file(name: str) -> str:
    """Normalize a filename to a stable lookup key: drop the extension and any
    export-specific shard/member-id suffix, then reduce to alphanumerics. This is
    the canonical `file_index` key — adapters/mappings MUST report consumed keys via
    norm_file (not nk) or coverage will show files as unclaimed."""
    stem = re.sub(r"\.(csv|json|html?|ics|vcf|mbox|js|txt|md|xml|eml|gpx)$", "", name, flags=re.I)
    stem = re.sub(r"_\d{6,}$", "", stem)      # linkedin member-id suffix
    stem = re.sub(r"_\d{1,3}$", "", stem)     # facebook/instagram _1,_2 shard suffix
    return re.sub(r"[^a-z0-9]", "", stem.lower())

def obsidian_name(s: str) -> str:
    """Make a string safe as BOTH an Obsidian note title and its filename: strip
    link/filename-illegal chars, collapse whitespace, cap at 100 chars. Keeps spaces
    (no slugging) so filename==title and [[wikilinks]] resolve. Defaults to "Unknown"."""
    s = re.sub(r'[\[\]#^|:\\/<>*?"]', "", s or "")
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:100] or "Unknown"

def link(name: str) -> str:
    """Render an Obsidian wikilink to a name's note: `[[Title]]` (title obsidian-safe)."""
    return f"[[{obsidian_name(name)}]]"

def canonical_url(u: str) -> str:
    """Normalize a public profile/company URL so the same target dedupes:
    lowercase scheme+host, drop query/fragment, strip a trailing slash, drop a
    leading 'www.'. Returns "" for empty/non-URLs. Public profile URLs are public
    identifiers (used as a secondary entity-resolution key) — NOT contact PII like
    emails/phones, which are stripped elsewhere."""
    s = (u or "").strip()
    if not s or "/" not in s:
        return ""
    s = re.split(r"[?#]", s, 1)[0]
    m = re.match(r"^(https?://)?(.*)$", s, re.I)
    rest = (m.group(2) if m else s)
    if "/" in rest:
        host, path = rest.split("/", 1)
    else:
        host, path = rest, ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    path = path.rstrip("/")
    if not host:
        return ""
    return f"https://{host}/{path}".rstrip("/")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

def iso_date(s):
    """Normalize varied date strings (and unix timestamps) to ISO."""
    if isinstance(s, (int, float)) and s > 0:
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = (s or "").strip() if isinstance(s, str) else ""
    if not s:
        return ""
    if re.match(r"^\d{10}$", s):          # unix epoch seconds as string
        return iso_date(int(s))
    if re.match(r"^\d{13}$", s):          # unix epoch milliseconds as string
        return iso_date(int(s) // 1000)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m: return m.group(1)
    m = re.match(r"^(\d{1,2})[ /]([A-Za-z]{3,})[ ,]+(\d{4})$", s)
    if m and m.group(2)[:3].lower() in _MONTHS:
        return f"{int(m.group(3)):04d}-{_MONTHS[m.group(2)[:3].lower()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"^([A-Za-z]{3,})[ ,]+(\d{4})$", s)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return f"{int(m.group(2)):04d}-{_MONTHS[m.group(1)[:3].lower()]:02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # Twitter/X archive format: "Mon Apr 01 10:00:00 +0000 2024"
    m = re.match(r"^[A-Za-z]{3} ([A-Za-z]{3}) (\d{1,2}) [\d:]{8} [+-]\d{4} (\d{4})$", s)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}"
    if re.match(r"^\d{4}$", s): return s
    return s

# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
SENSITIVE_COL_HINTS = ("email", "phone", "number", "content", "body", "message",
                       "password", "address", "ssn", "ip", "token", "secret")

def strip_pii(text: str) -> str:
    """Redact emails out of free text before it's stored (posts/comments/notes).
    Privacy invariant: third-party emails never reach the vault, even inside prose."""
    if not text:
        return text
    text = EMAIL_RE.sub("[email removed]", text)
    return text

def fix_mojibake(s: str) -> str:
    """Facebook/Instagram JSON often double-encodes UTF-8 as latin-1."""
    if not isinstance(s, str):
        return s
    try:
        if re.search(r"Ã.|â..", s):
            return s.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    return s

# ---------------------------------------------------------------------------
# robust readers
# ---------------------------------------------------------------------------

def _header_index(rows):
    """Find the real header row, skipping any leading preamble block. Real
    LinkedIn exports (e.g. Connections.csv) prepend a 'Notes:' line and a quoted
    disclaimer (which parses as ONE cell because it's quoted) before the header.
    Heuristic: the header is the first of the leading rows that has >=2 non-empty
    short fields. Single-column files (e.g. Skills.csv -> 'Name') have no such row,
    so we fall back to row 0."""
    for i, r in enumerate(rows[:8]):
        nonempty = [c for c in r if (c or "").strip()]
        if len(nonempty) >= 2 and all(len(c or "") <= 100 for c in r):
            return i
    return 0

def read_csv(path: Path):
    """Read a CSV into a list of dicts (DictReader semantics), skipping any
    leading 'Notes:'/disclaimer preamble so the real header row is used."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as f:
                rows = list(csv.reader(f))
        except Exception:
            continue
        if not rows:
            return []
        idx = _header_index(rows)
        header = rows[idx]
        out = []
        for r in rows[idx + 1:]:
            if not any((c or "").strip() for c in r):
                continue  # skip blank rows, like csv.DictReader
            d = {h: (r[j] if j < len(r) else None) for j, h in enumerate(header)}
            if len(r) > len(header):           # extras -> restkey None (as DictReader)
                d[None] = r[len(header):]
            out.append(d)
        return out
    return []

def read_json(path: Path):
    """Parse a JSON file, falling back across common encodings; returns None on failure."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return json.loads(Path(path).read_text(encoding=enc))
        except Exception:
            continue
    return None

def walk_json_arrays(obj, want_keys):
    """Yield every list-of-dicts found anywhere in a JSON structure whose dicts
    contain any of want_keys. Deduplicates by object identity so an array found
    at multiple nesting levels is only returned once."""
    found = []
    seen_ids = set()
    def rec(o):
        if isinstance(o, list):
            if o and isinstance(o[0], dict) and any(k in o[0] for k in want_keys):
                if id(o) not in seen_ids:
                    seen_ids.add(id(o)); found.append(o)
            for it in o:
                rec(it)
        elif isinstance(o, dict):
            for v in o.values():
                rec(v)
    rec(obj)
    return found

# ---------------------------------------------------------------------------
# the canonical collector (privacy enforced here)
# ---------------------------------------------------------------------------

class Collector:
    """The canonical, source-agnostic sink every adapter pushes records into, and
    the single point where privacy is enforced. Holds typed buckets (identity,
    people, orgs, posts, comments, reactions, interests, places, msg_signal,
    uncategorized, …) plus run context, and the builder renders one vault from it.
    Default mode strips third-party PII; full=True is owner-mode (keeps everything)."""

    def __init__(self, full=False):
        # full=True → FULL-FIDELITY / OWNER mode: this is the user's OWN data on
        # their OWN machine for their OWN private brain (still zero network calls).
        # It stores everything — emails, phones, every extra column, message
        # bodies, and imports the otherwise-quarantined files — because for a
        # personal brain "missing fields = no value". Default (full=False) stays
        # privacy-safe for distribution / company / GBrain use (third-party +
        # employee PII stripped). The owner opts in with build_vault.py --full.
        self.full = full
        self.structure_spec = None          # brain_structure.json spec (set by builder)
        self.file_keys = set()              # normalized file keys (set by builder)
        self.skipped_keys = set()           # consumed-but-deliberately-not-extracted
                                            # (low-signal by design; shown honestly
                                            # in _COVERAGE.md as "skipped")
        self.subject = "person"             # "person" | "company" — what the brain is rooted on
        self.subject_entity = ""            # the root entity name (the user, or the company)
        self.entity_name = ""               # named-entity folder this brain came from (multi-entity)
        self.entity_kind = ""               # "person" | "company"
        self.entity_vault = None            # Path to this entity's built vault (for correlation links)
        self.identity = {}                  # merged single identity
        self.people = {}                    # nk(name) -> record
        self.orgs = {}                      # name -> {category, sources}
        self.posts = []                     # {text,date,kind,source}
        self.comments = []                  # {text,date,source}
        self.reactions = Counter()
        self.interests = Counter()          # tag/topic -> count
        self.saved_count = 0
        self.reputation_received = []       # {who,text}
        self.reputation_given = []
        self.endorse_received = Counter()   # skill -> n
        self.endorse_given = 0
        self.applications = Counter()       # company -> n
        self.app_titles = Counter()
        self.app_dates = []
        self.prefs = {}
        self.reusable = []                  # {q,a}
        self.saved_jobs = []                # {title, company}
        self.mirror_inferences = []
        self.ad_segments = []
        self.searches = []                  # list[SearchQuery] (str subclass w/ source+date)
        self.events = []                    # canonical via add_event: {name,date,kind,source,
                                            #   location,description,attendees,tags,url,value}
        self.places = {}                    # key -> {name,address,lat,lng,url,kind,note,lists}
        self._place_index = {}              # nk(name) -> [place rec, …] (merge lookup)
        self.purchases = []                 # canonical via add_purchase: {item,merchant,date,
                                            #   amount,currency,category,url,source,tags}
        self._purchase_keys = set()         # (source, nk(item), date, amount) dedupe
        self.learning_count = 0
        self.services = Counter()           # label -> n
        self.msg_signal = {}                # nk(name) -> {"n","first","last","by":Counter(source)}
        self.interest_meta = {}             # tag -> {"sources": set, "date": first_iso}
        self.reaction_sources = {}          # kind -> set(sources)
        self._event_keys = set()            # (source, kind, nk(name), date) dedupe
        self._post_keys = set()             # (source, date, sha1(text)) dedupe
        self._comment_keys = set()          # (source, date, sha1(text)) dedupe
        self._msg_keys = set()              # (source, nk(party), ts) dedupe (ts-bearing only)
        self.uncategorized = []             # {source,file,columns,rows}
        self.sources = set()
        self.companies = set()
        self.log = []

    # ---- identity
    def set_identity(self, source, **fields):
        """Merge fields into the single owner identity (first non-empty value wins),
        repairing mojibake; tracks which sources contributed."""
        self.sources.add(source)
        for k, v in fields.items():
            # never let an email/phone-shaped value become the identity name/title
            # (an IG export lists "Email address"/"Phone number" first in its
            # profile map, which would otherwise win the name slot).
            if k == "name" and isinstance(v, str) and (EMAIL_RE.search(v) or PHONE_RE.search(v)):
                continue
            if v and not self.identity.get(k):
                self.identity[k] = fix_mojibake(v) if isinstance(v, str) else v
        self.identity.setdefault("sources", set()).add(source)

    # ---- people
    # Default (privacy-safe): email/phone are NEVER stored; `url` (a public
    # profile link) IS kept. FULL mode (self.full): email/phone/extra ARE stored
    # too — the owner explicitly wants their complete data.
    def add_person(self, source, name, company="", role="", date="", handle="",
                   url="", email="", phone="", extra=None, tags=None, location="",
                   connected_on="", dept=""):
        """Add/merge a person keyed by nk(name); merges across sources (first
        non-empty value wins per field). Privacy invariant: a name matching
        EMAIL_RE is dropped entirely, and email/phone/extra are stored ONLY in full
        mode — in default mode they're forced empty even if an adapter passes them.
        A public profile `url` is kept in both modes (public identifier, not PII).
        `location` is a public place string (a city, not an address) — kept in both
        modes and geocoded offline at render time for the map view.
        `tags` are semantic tags (e.g. "person/friend") merged across sources and
        rendered alongside the automatic source/type tags."""
        name = fix_mojibake((name or "").strip())
        if not name or EMAIL_RE.search(name):
            return  # privacy: never store a "person" whose name is actually an email
        self.sources.add(source)
        key = nk(name)
        if not key:
            return
        rec = self.people.get(key)
        company = fix_mojibake((company or "").strip())
        if company:
            self.companies.add(company)
        cu = canonical_url(url)
        tags = {str(t).strip() for t in (tags or []) if str(t).strip()}
        # PII only enters in full mode; otherwise these are coerced to "" (and the
        # extra-column dict to {}) regardless of what the adapter passed in.
        email = (email or "").strip() if self.full else ""
        phone = (phone or "").strip() if self.full else ""
        extra = {k: v for k, v in (extra or {}).items()
                 if v and str(v).strip()} if self.full else {}
        location = fix_mojibake((location or "").strip())
        connected_on = iso_date(connected_on)
        dept = fix_mojibake((dept or "").strip())
        if rec is None:
            self.people[key] = {
                "name": name, "company": company, "role": role,
                "date": iso_date(date), "handles": {handle} if handle else set(),
                "url": cu, "email": email, "phone": phone, "extra": dict(extra),
                "location": location, "connected_on": connected_on, "dept": dept,
                "sources": {source}, "tags": set(tags),
                # provenance: which source first supplied each field, and any
                # CONFLICTING later values (first-non-empty still wins, but the
                # losing claim is preserved and rendered as "Also reported")
                "prov": {f: source for f, v in
                         (("company", company), ("role", role),
                          ("location", location), ("dept", dept)) if v},
                "alt": {},
            }
        else:
            rec["sources"].add(source)
            rec.setdefault("tags", set()).update(tags)
            if handle: rec["handles"].add(handle)
            for field, val in (("company", company), ("role", role),
                               ("location", location), ("dept", dept)):
                if not val:
                    continue
                cur = rec.get(field, "")
                if not cur:
                    rec[field] = val
                    rec.setdefault("prov", {})[field] = source
                elif nk(val) != nk(cur):
                    # conflicting claim from another source — keep, don't lose
                    alts = rec.setdefault("alt", {}).setdefault(field, [])
                    if (val, source) not in alts:
                        alts.append((val, source))
            if date and not rec["date"]: rec["date"] = iso_date(date)
            if connected_on and not rec.get("connected_on"):
                rec["connected_on"] = connected_on
            if cu and not rec.get("url"): rec["url"] = cu
            if email and not rec.get("email"): rec["email"] = email
            if phone and not rec.get("phone"): rec["phone"] = phone
            if extra:
                merged = dict(rec.get("extra") or {})
                for k, v in extra.items():
                    merged.setdefault(k, v)
                rec["extra"] = merged
        self.companies.discard("")  # never let an empty company name linger in the set

    def add_org(self, source, name, category="referenced", url="", extra=None,
                tags=None, location="", industry="", size="", domain="", about=""):
        """Add/merge an organization keyed by exact name; tracks category, public
        url, and contributing sources. `extra` fields are kept only in full mode.
        `location` (HQ city), `industry`, `size` (headcount/range), `domain`
        (website domain) and `about` (self-description, e.g. a Slack channel's
        topic/purpose) are PUBLIC business facts — kept in both modes; location
        geocodes offline at render time for the map view.
        `tags` are semantic tags merged across sources (rendered with source/type)."""
        name = fix_mojibake((name or "").strip())
        if not name:
            return
        self.companies.add(name)
        self.sources.add(source)
        cu = canonical_url(url)
        tags = {str(t).strip() for t in (tags or []) if str(t).strip()}
        location = fix_mojibake((location or "").strip())
        industry = fix_mojibake((industry or "").strip())
        size = str(size or "").strip()
        domain = re.sub(r"^(https?://)?(www\.)?", "", (domain or "").strip().lower()).rstrip("/")
        about = fix_mojibake(strip_pii((about or "").strip()))
        extra = {k: v for k, v in (extra or {}).items()
                 if v and str(v).strip()} if self.full else {}
        cur = self.orgs.get(name)
        if cur is None:
            self.orgs[name] = {"category": category, "sources": {source},
                               "url": cu, "extra": dict(extra), "tags": set(tags),
                               "location": location, "industry": industry,
                               "size": size, "domain": domain, "about": about,
                               "prov": {f: source for f, v in
                                        (("industry", industry), ("location", location))
                                        if v},
                               "alt": {}}
        else:
            cur["sources"].add(source)
            cur.setdefault("tags", set()).update(tags)
            if cu and not cur.get("url"): cur["url"] = cu
            for field, val in (("location", location), ("industry", industry),
                               ("size", size), ("domain", domain), ("about", about)):
                if not val:
                    continue
                if not cur.get(field):
                    cur[field] = val
                    cur.setdefault("prov", {})[field] = source
                elif field in ("location", "industry") and nk(val) != nk(cur[field]):
                    alts = cur.setdefault("alt", {}).setdefault(field, [])
                    if (val, source) not in alts:
                        alts.append((val, source))
            if extra:
                merged = dict(cur.get("extra") or {})
                for k, v in extra.items():
                    merged.setdefault(k, v)
                cur["extra"] = merged

    def add_post(self, source, text="", date="", kind="post", url="", tags=None):
        """Record one of the owner's own posts/writings. Privacy: text is run
        through strip_pii so any embedded emails are redacted before storage.
        Idempotent: the same (source, date, text) seen again — e.g. when an old
        and a new export of the same archive sit in the data folder together —
        is recorded once."""
        text = fix_mojibake(strip_pii((text or "").strip()))
        d = iso_date(date)
        k = (source, d, hashlib.sha1(text.encode("utf-8")).hexdigest())
        if text and k in self._post_keys:
            return
        self._post_keys.add(k)
        self.sources.add(source)
        tags = sorted({str(t).strip() for t in (tags or []) if str(t).strip()})
        self.posts.append({"text": text, "date": d, "kind": kind,
                           "url": url, "source": source, "tags": tags})

    def add_place(self, source, name="", address="", lat="", lng="", url="",
                  kind="place", note="", date="", tags=None, category=""):
        """A geographic place — saved/reviewed location (Google Maps, IG locations).
        Merged by normalized name so the SAME place seen in more than one source —
        e.g. a bare entry from a saved-list CSV (title + URL only) and the rich
        GeoJSON entry (address + coordinates) — becomes ONE node carrying the union
        of details, instead of two thin duplicates. Precision-biased: two places that
        share a name but have different non-empty addresses stay separate (a wrong
        merge is worse than a miss). `category` is the saved-list it came from
        (e.g. "Favorite places", "Want to go"), collected into `lists`. `note` is the
        owner's own review text; strip_pii'd. `tags` are semantic tags merged across
        sources (rendered with source/type)."""
        name = fix_mojibake((name or "").strip())
        if not name:
            return
        self.sources.add(source)
        address = (address or "").strip()
        note = fix_mojibake(strip_pii((note or "").strip()))
        tags = {str(t).strip() for t in (tags or []) if str(t).strip()}
        category = (category or "").strip()
        na = nk(address)
        # Find an existing place with the same name whose address is compatible
        # (one side empty, or equal) → merge. Else this is a distinct place.
        base = nk(name)
        rec = None
        for p in self._place_index.get(base, ()):
            pa = nk(p.get("address", ""))
            if not pa or not na or pa == na:
                rec = p
                break
        if rec is None:
            key = base if base not in self.places else base + "|" + na
            rec = {"name": name, "address": address,
                   "lat": str(lat or ""), "lng": str(lng or ""),
                   "url": url or "", "kind": kind,
                   "note": note, "date": iso_date(date),
                   "sources": {source},
                   "tags": set(tags),
                   "lists": {category} if category else set()}
            self.places[key] = rec
            self._place_index.setdefault(base, []).append(rec)
        else:
            rec["sources"].add(source)
            rec.setdefault("tags", set()).update(tags)
            if category:
                rec.setdefault("lists", set()).add(category)
            # Fill any missing scalar from this sighting (don't overwrite richer data).
            for k, v in (("address", address), ("url", url), ("note", note),
                         ("lat", str(lat or "")), ("lng", str(lng or "")),
                         ("date", iso_date(date))):
                if v and not rec.get(k):
                    rec[k] = v
            # A real review/coordinates upgrade a bare "saved" pin to its richer kind.
            if kind == "reviewed" or (kind == "labeled" and rec.get("kind") == "saved"):
                rec["kind"] = kind

    def add_comment(self, source, text="", date=""):
        """Record one of the owner's own comments. Privacy: text is strip_pii'd
        (emails redacted) before storage; empty comments are skipped. Idempotent
        on (source, date, text) like add_post."""
        text = fix_mojibake(strip_pii((text or "").strip()))
        if not text:
            return
        d = iso_date(date)
        k = (source, d, hashlib.sha1(text.encode("utf-8")).hexdigest())
        if k in self._comment_keys:
            return
        self._comment_keys.add(k)
        self.comments.append({"text": text, "date": d, "source": source})

    def add_reaction(self, source, kind="like", date=""):
        """Tally one reaction by kind (defaults to 'like'); aggregate count only,
        no per-target detail is retained. Contributing sources are tracked so the
        reactions note can attribute its counts."""
        kind = kind or "like"
        self.reactions[kind] += 1
        self.reaction_sources.setdefault(kind, set()).add(source)

    def add_interest(self, source, tag, date=""):
        """Tally an interest/topic tag (e.g. a followed page or YouTube topic).
        Provenance (which sources, earliest date) is kept in interest_meta so the
        interests note can group by source."""
        tag = fix_mojibake((tag or "").strip())
        if not tag:
            return
        self.interests[tag] += 1
        m = self.interest_meta.setdefault(tag, {"sources": set(), "date": ""})
        m["sources"].add(source)
        d = iso_date(date)
        if d and (not m["date"] or d < m["date"]):
            m["date"] = d

    def add_search(self, source, query, date=""):
        """Record a search query WITH provenance. Entries remain plain strings
        (SearchQuery subclasses str) so legacy readers keep working."""
        q = fix_mojibake((query or "").strip())
        if q:
            self.sources.add(source)
            self.searches.append(SearchQuery(q, source=source, date=iso_date(date)))

    def add_event(self, source, name, date="", kind="event", location="",
                  description="", attendees=None, tags=None, url="", value=""):
        """THE canonical event verb (replaces raw events.append): a dated
        happening — calendar event/meeting, CRM deal or campaign, activity.
        `kind` routes rendering (deal/campaign → pipeline in company brains;
        attendees → meeting pages in GBrain). Idempotent on
        (source, kind, nk(name), date)."""
        name = fix_mojibake((name or "").strip())
        if not name:
            return
        d = iso_date(date)
        k = (source, kind, nk(name), d)
        if k in self._event_keys:
            return
        self._event_keys.add(k)
        self.sources.add(source)
        ev = {"name": name, "date": d, "kind": kind or "event", "source": source}
        if location:
            ev["location"] = fix_mojibake(str(location).strip())
        if description:
            ev["description"] = fix_mojibake(strip_pii(str(description).strip()))[:500]
        att = [fix_mojibake(str(a).strip()) for a in (attendees or []) if str(a).strip()]
        if att:
            ev["attendees"] = att
        tags = sorted({str(t).strip() for t in (tags or []) if str(t).strip()})
        if tags:
            ev["tags"] = tags
        if url:
            ev["url"] = url
        if value:
            ev["value"] = str(value).strip()
        self.events.append(ev)

    # ---- shopping / commerce (35-shopping): what the owner buys & consumes.
    def add_purchase(self, source, item="", merchant="", date="", amount="",
                     currency="", category="", url="", tags=None):
        """A commerce/consumption record — an order/purchase/subscription (e.g.
        Amazon orders). ONE note per purchase, rendered in the 35-shopping layer.
        Privacy boundary: there is deliberately NO card=/address= parameter — the
        adapter must never pass payment cards, billing/shipping addresses, IPs or
        serial numbers (they are read past, exactly like email/phone). `merchant`
        is registered as an org so a [[merchant]] wikilink resolves. Idempotent on
        (source, nk(item), date, amount)."""
        item = fix_mojibake((item or "").strip())
        if not item or nk(item) in ("notapplicable", "notavailable"):
            return  # skip Amazon's pervasive placeholder rows
        d = iso_date(date)
        amt = str(amount or "").strip()
        k = (source, nk(item), d, amt)
        if k in self._purchase_keys:
            return
        self._purchase_keys.add(k)
        self.sources.add(source)
        merchant = fix_mojibake((merchant or "").strip())
        if merchant:
            # register a real org (carries the source tag) so the [[merchant]]
            # wikilink resolves to a proper, attributed note — not an empty stub.
            self.add_org(source, merchant, category="merchant")
        tags = sorted({str(t).strip() for t in (tags or []) if str(t).strip()})
        self.purchases.append({
            "item": item, "merchant": merchant, "date": d, "amount": amt,
            "currency": (currency or "").strip(), "category": (category or "").strip(),
            "url": url or "", "source": source, "tags": tags,
        })

    # ---- the algorithmic mirror (50-mirror): how the platforms model the user.
    # These are inferences/segments DERIVED about the owner by a platform (FB ad
    # interests, advertisers using your data, off-Meta activity, age/language
    # predictions; LinkedIn inferences/ad targeting), kept distinct from
    # `interests` (things the owner actually chose). Stored as plain strings;
    # the renderer dedupes (dict.fromkeys) — see VaultWriter.mirror().
    def add_mirror_inference(self, source, text):
        """Record one algorithmic inference the platform makes about the owner
        (e.g. an ad-interest topic, a predicted attribute). 50-mirror layer."""
        text = fix_mojibake((text or "").strip())
        if text:
            self.sources.add(source)
            self.mirror_inferences.append(text)

    def add_ad_segment(self, source, text):
        """Record one ad-targeting segment / advertiser / off-platform signal the
        platform uses to reach the owner (the ad side of the mirror)."""
        text = fix_mojibake((text or "").strip())
        if text:
            self.sources.add(source)
            self.ad_segments.append(text)

    def add_message_signal(self, source, party_name, date="", ts=""):
        """Records ONLY that a message exchange happened + when. Never the body.
        Record: {"n": count, "first": iso, "last": iso, "by": Counter(source)}.
        When a precise `ts` is supplied (epoch/timestamp string), the signal is
        idempotent on (source, party, ts) — so re-reading the same history in an
        accumulated data folder can't inflate relationship strength."""
        key = nk(party_name)
        if not key:
            return
        if ts:
            mk = (source, key, str(ts))
            if mk in self._msg_keys:
                return
            self._msg_keys.add(mk)
        d = iso_date(date) or iso_date(ts) or ""
        rec = self.msg_signal.get(key)
        if rec is None:
            rec = self.msg_signal[key] = {"n": 0, "first": "", "last": "",
                                          "by": Counter()}
        rec["n"] += 1
        rec["by"][source] += 1
        if d:
            rec["last"] = max(rec["last"], d)
            rec["first"] = min(rec["first"], d) if rec["first"] else d

    def add_uncategorized(self, source, filename, columns, rows):
        """Stash a file no adapter/mapping claimed (columns + sample rows) so the
        harvester can render it into 99-uncategorized/ — nothing is silently dropped."""
        self.uncategorized.append({"source": source, "file": filename,
                                   "columns": columns, "rows": rows})

    def note(self, msg):
        """Append a free-form message to the build log (surfaced in build reports)."""
        self.log.append(msg)
