#!/usr/bin/env python3
"""
Google Takeout adapter — a multi-product, multi-ARCHIVE export.

Takeout is downloaded as ONE OR MORE archives ("Takeout", "Takeout 2", … — Google
splits large exports and macOS auto-renames repeat unzips). Sub-products land in
whichever archive folder they happened to come in, so every rule here scopes by a
path SUBSTRING (e.g. ".../Maps/My labeled places/...") and is archive-agnostic: it
does not matter whether a product sits under `Takeout/` or `Takeout 2/`.

Google is a single Python adapter (not a JSON mapping) because the export mixes
formats the declarative engine cannot parse — vCard (.vcf), iCalendar (.ics) and
HTML (YouTube history) — with ones it can (JSON/GeoJSON/CSV). One file = one source
of truth, a unified `source: google` tag. All output flows through the Collector,
so privacy holds automatically (third-party emails/phones dropped, message bodies
never read).

Coverage:
  Profile.json                          -> identity
  Contacts (.vcf / .csv)                -> people (+ orgs)
  Calendar (.ics)                       -> events   (SUMMARY + DTSTART only)
  Maps (your places)/Saved Places.json  -> places   (GeoJSON)
  Maps (your places)/Reviews.json       -> places   (+ your review note)
  Maps/My labeled places/Labeled places -> places   (Home/Work/…)
  Saved/*.csv  (place lists)            -> places
  Maps/Your local followed places/*.csv -> places
  Semantic Location History/*.json      -> places   (visits, aggregated top 200)
  My Activity/Search/MyActivity.*       -> searches (capped)
  My Activity/Ads/MyActivity.json       -> ad segments (50-mirror)
  Google Photos/*.jpg.json sidecars     -> places   (photo spots, aggregated; never images)
  YouTube subscriptions.csv             -> interests (channels)
  YouTube playlists.csv + likes.csv     -> interests (+ like count)
  YouTube comments/comments.csv         -> voice    (own comments)
  YouTube history/watch-history.html    -> interests (channels, deduped + capped)
  YouTube history/search-history.html   -> searches  (queries, capped)
  Chrome bookmarks/reading list (.html) -> interests

Excluded BY DESIGN and shown honestly as `skipped` in _COVERAGE.md (never silent):
raw Location History pings (Records.json), Chrome history, Gmail MBOX, Fit, Drive,
Keep, Play — personal email/health/files don't belong in a brain (see docs).
"""
import re
import html as _html
import urllib.parse
from ..common import (read_csv, read_json, nk, norm_file, iso_date, EMAIL_RE,
                      fix_mojibake, strip_pii)

NAME = "google"

# Country NAME -> ISO code, so a place recovered from a map URL ("…, Switzerland") groups with
# the location-coded ones ("CH") instead of forming a duplicate country bucket.
_COUNTRY_CODE = {
    "united states": "US", "usa": "US", "united kingdom": "GB", "uk": "GB", "england": "GB",
    "romania": "RO", "switzerland": "CH", "france": "FR", "germany": "DE", "italy": "IT",
    "austria": "AT", "spain": "ES", "portugal": "PT", "greece": "GR", "netherlands": "NL",
    "belgium": "BE", "japan": "JP", "china": "CN", "thailand": "TH", "turkey": "TR",
    "united arab emirates": "AE", "uae": "AE", "egypt": "EG", "canada": "CA", "mexico": "MX",
    "brazil": "BR", "australia": "AU", "india": "IN", "singapore": "SG", "poland": "PL",
    "czechia": "CZ", "czech republic": "CZ", "hungary": "HU", "croatia": "HR", "serbia": "RS",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI", "ireland": "IE",
    "morocco": "MA", "saudi arabia": "SA", "qatar": "QA", "israel": "IL", "indonesia": "ID",
    "malaysia": "MY", "vietnam": "VN", "philippines": "PH",
}

_COORD_RE = re.compile(r"^-?\d+\.\d+\s*,\s*-?\d+\.\d+$")


def _looks_coord(s):
    """True if `s` is a bare coordinate (lat,lng or DMS) — not a usable place name."""
    s = str(s or "")
    return bool(s) and ("°" in s or bool(_COORD_RE.match(s.strip())))


def _place_from_maps_url(url):
    """Recover (name, address, country_code) from a Google Maps URL's ?q= param when the export
    has no location field (~22% of saved places). Returns ("","","") for coordinate-only pins."""
    if not url:
        return "", "", ""
    m = re.search(r"[?&]q=([^&]+)", url)
    if not m:
        return "", "", ""
    try:
        q = urllib.parse.unquote_plus(m.group(1)).strip()
    except Exception:
        q = m.group(1).replace("+", " ").strip()
    if not q or _looks_coord(q):
        return "", "", ""
    parts = [s.strip() for s in q.split(",") if s.strip()]
    name = next((s for s in parts if re.search(r"[A-Za-z]", s)), q)
    cc = _COUNTRY_CODE.get(parts[-1].lower(), "") if len(parts) > 1 else ""
    return name, q, cc


def _name_from_place_url(url):
    """Recover a place name from a Google Maps `/maps/place/<Name>/…` URL (the form
    saved-list CSVs use), falling back to a `?q=` name. '+' → space, '%xx' decoded."""
    if not url:
        return ""
    m = re.search(r"/maps/place/([^/?]+)", url)
    if m:
        try:
            nm = urllib.parse.unquote_plus(m.group(1)).strip()
        except Exception:
            nm = m.group(1).replace("+", " ").strip()
        if nm and not _looks_coord(nm):
            return nm
    nm, _, _ = _place_from_maps_url(url)
    return nm

# Sensitive Takeout files — catalogued in coverage, NEVER imported (norm_file keys).
QUARANTINE = {"accesslogactivity", "passwords", "recovery", "security"}

# Caps so a large history file can't bloat the vault.
_WATCH_CAP = 500
_SEARCH_CAP = 500

# YouTube channel anchors in watch-history.html; search-query anchors in search-history.html.
# YouTube HTML patterns are SHARED with the standalone youtube.py adapter
# (sources/personal/_youtube_common.py) so the two can't drift.
from ._youtube_common import RE_CHANNEL as _RE_CHANNEL, RE_QUERY as _RE_QUERY  # noqa: E402


def detect(file_index):
    """True if the archive looks like a Google Takeout export (a 'Takeout/' root, a
    Google profile, or contacts co-occurring with calendar/YouTube). Matches whether
    the data sits under `Takeout/`, `Takeout 2/`, … (substring 'takeout')."""
    joined = " ".join(file_index.keys())
    paths = [str(p).lower() for paths_list in file_index.values() for p in paths_list]
    blob = " ".join(paths)
    # strong product-folder signals (archive-agnostic — Takeout / Takeout 2 / loose folders)
    # NOTE: "youtube and youtube music" alone is NOT a google signal — a
    # standalone YouTube slice belongs to youtube.py; google owns it only when
    # it sits inside a real Takeout tree (the "takeout" signal covers that).
    for sig in ("takeout", "maps (your places)", "maps(your places)",
                "my labeled places", "google account"):
        if sig in blob:
            return True
    if "googleprofile" in joined:
        return True
    has_contacts = any("contact" in p for p in paths)
    has_cal = any(p.endswith(".ics") for p in paths)
    has_yt = any("subscription" in p for p in paths)
    return has_contacts and (has_cal or has_yt)


# --- small parsers ---------------------------------------------------------

def _vcard_field(card, key):
    """First value of a vCard property `key` (handles params and item-prefixes,
    e.g. 'FN;CHARSET=UTF-8:', 'item1.ORG:'); '' if absent."""
    m = re.search(r'(?im)^(?:item\d+\.)?' + key + r'[^:\r\n]*:(.*)$', card)
    return m.group(1).strip() if m else ""


def _vcard_photo(block):
    """Extract an embedded PHOTO from a vCard block → (bytes|None, url).
    Handles the folded-base64 form (`PHOTO;ENCODING=b;TYPE=JPEG:` + space-indented
    continuation lines), the v4 `data:image/…;base64,` form, and a plain URL value
    (returned as a url pointer, never fetched). Decode failures → (None, "")."""
    m = re.search(r'(?im)^(?:item\d+\.)?PHOTO([^:\r\n]*):(.*)$', block)
    if not m:
        return None, ""
    params, first = m.group(1) or "", m.group(2)
    # unfold: continuation lines start with a space/tab (RFC 2425)
    rest = []
    for line in block[m.end():].splitlines():
        if line[:1] in (" ", "\t"):
            rest.append(line.strip())
        elif line.strip():
            break
    val = (first.strip() + "".join(rest)).strip()
    if not val:
        return None, ""
    if val.lower().startswith(("http://", "https://")):
        return None, val
    if "base64," in val:                         # v4 data: URI form
        val = val.split("base64,", 1)[1]
    elif "encoding=b" not in params.lower() and "base64" not in params.lower():
        return None, ""
    try:
        import base64
        data = base64.b64decode(re.sub(r"\s+", "", val), validate=False)
    except Exception:
        return None, ""
    # sanity: recognizably an image, and non-trivial
    if len(data) < 64 or not (data[:2] == b"\xff\xd8" or data[:4] == b"\x89PNG"
                              or data[:3] == b"GIF"):
        return None, ""
    return data, ""


def _parse_vcards(text):
    """Yield (name, org, title, photo_bytes, photo_url) for each VCARD block that
    has a usable display name. Photos are bundled export data (never fetched)."""
    for block in re.split(r'(?i)BEGIN:VCARD', text):
        if "END:VCARD" not in block.upper():
            continue
        name = _vcard_field(block, "FN")
        if not name:
            n = _vcard_field(block, "N")          # structured 'Family;Given;…'
            if n:
                parts = [p.strip() for p in n.split(";") if p.strip()]
                # N is Family;Given;Additional;Prefix;Suffix → render "Given Family"
                if len(parts) >= 2:
                    name = (parts[1] + " " + parts[0]).strip()
                elif parts:
                    name = parts[0]
        name = fix_mojibake(name)
        if not name or EMAIL_RE.search(name):
            continue                               # Collector drops these too; skip early
        org = _vcard_field(block, "ORG").split(";")[0].strip()
        title = _vcard_field(block, "TITLE")
        photo, purl = _vcard_photo(block)
        yield name, org, title, photo, purl


def _ics_unescape(s):
    """Unescape RFC-5545 text values (\\n \\, \\; \\\\)."""
    return (s.replace("\\n", " ").replace("\\N", " ")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")).strip()


def _ics_events(text):
    """Yield (summary, iso_date, location, description) per VEVENT. Attendees are
    never read (privacy); location + description give the event real context."""
    summary = dtstart = loc = desc = None
    for line in text.splitlines():
        if line.startswith("SUMMARY:"):
            summary = _ics_unescape(line[8:])
        elif line.startswith("DTSTART"):
            m = re.search(r":(\d{8})", line)
            if m:
                g = m.group(1)
                dtstart = f"{g[:4]}-{g[4:6]}-{g[6:8]}"
        elif line.startswith("LOCATION:"):
            loc = _ics_unescape(line[9:])
        elif line.startswith("DESCRIPTION:"):
            desc = _ics_unescape(line[12:])
        elif line.startswith("END:VEVENT"):
            if summary:
                yield summary, (dtstart or ""), (loc or ""), (desc or "")
            summary = dtstart = loc = desc = None


def _features(data):
    """Yield GeoJSON features from a FeatureCollection dict (or []), defensively."""
    feats = (data or {}).get("features") if isinstance(data, dict) else None
    return feats if isinstance(feats, list) else []


def _dig(d, *path):
    """Nested dict.get following `path`; '' if any hop is missing/not a dict."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(k)
    return cur if isinstance(cur, (str, int, float)) else ""


# --- main extract ----------------------------------------------------------

def extract(root, file_index, all_paths, col):
    """Parse a Google Takeout export (one or more archives) into the Collector.
    Returns the set of consumed normalized filename keys."""
    consumed = set()
    low = lambda p: str(p).lower()

    pc = cc = ec = pl = yc = wc = sc = 0  # counters
    visits = {}   # nk(place name) -> {"name","address","lat","lng","n"}  (Semantic Location History)
    photos = {}   # rounded (lat,lng) -> {"lat","lng","n","first_date"}   (Photos EXIF sidecars)
    ac = mac = 0  # My Activity: searches / ad segments

    for p in all_paths:
        sfx = p.suffix.lower()
        lp = low(p)
        key = norm_file(p.name)

        # ---- Profile -> identity ----------------------------------------
        if p.name.lower() == "profile.json" and "profile" in lp:
            data = read_json(p) or {}
            nm = data.get("displayName") or _dig(data, "name", "formattedName")
            if not nm and isinstance(data.get("name"), dict):
                nm = (data["name"].get("givenName", "") + " " +
                      data["name"].get("familyName", "")).strip()
            if nm:
                col.set_identity(NAME, name=nm)
            consumed.add(key)
            continue

        # ---- Contacts: vCard --------------------------------------------
        # Match by extension OR by content: Google sometimes exports a contacts
        # group with NO file extension (e.g. "Importate pe 07.08.2012"), which would
        # otherwise be lost. Sniff such contacts-path files for a vCard header.
        _maybe_vcard = sfx == ".vcf" or (
            sfx not in (".json", ".csv", ".ics", ".html", ".jpg", ".jpeg", ".png", ".vcf")
            and "contact" in lp
        )
        if _maybe_vcard:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "BEGIN:VCARD" not in text.upper():
                continue  # not a vCard after all → let the harvester try it
            for name, org, title, photo, purl in _parse_vcards(text):
                col.add_person(NAME, name, org, title,
                               avatar_bytes=photo, avatar_url=purl)
                if org:
                    col.add_org(NAME, org, "contact-org")
                pc += 1
            consumed.add(key)
            continue

        # ---- Contacts: CSV ----------------------------------------------
        if sfx == ".csv" and "contact" in lp:
            for r in read_csv(p):
                name = (r.get("Name") or
                        ((r.get("Given Name", "") or "") + " " +
                         (r.get("Family Name", "") or "")).strip() or
                        r.get("File As") or "")
                org = r.get("Organization Name") or r.get("Organization 1 - Name") or ""
                title = r.get("Organization Title") or r.get("Organization 1 - Title") or ""
                if name and not EMAIL_RE.search(name):
                    col.add_person(NAME, name, org, title)
                    if org:
                        col.add_org(NAME, org, "contact-org")
                    pc += 1
            consumed.add(key)
            continue

        # ---- Calendar (.ics) -> events ----------------------------------
        if sfx == ".ics":
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for summary, dt, loc, desc in _ics_events(text):
                col.add_event(NAME, summary, date=dt, location=strip_pii(loc),
                              description=strip_pii(desc))
                ec += 1
            consumed.add(key)
            continue

        # ---- Maps GeoJSON (saved / reviews / labeled) -> places ---------
        if sfx == ".json" and "maps" in lp:
            data = read_json(p)
            feats = _features(data)
            if feats:
                kind = ("reviewed" if "review" in lp else
                        "labeled" if "labeled" in lp else "saved")
                for ft in feats:
                    props = ft.get("properties") if isinstance(ft, dict) else None
                    if not isinstance(props, dict):
                        continue
                    geom = ft.get("geometry") if isinstance(ft.get("geometry"), dict) else {}
                    coords = geom.get("coordinates") if isinstance(geom.get("coordinates"), list) else []
                    # GeoJSON order is [lng, lat]; Google writes [0,0] for "no location" pins —
                    # that's not a real coordinate, so don't plot a null-island marker.
                    has_geo = len(coords) >= 2 and not (coords[0] == 0 and coords[1] == 0)
                    lng = coords[0] if has_geo else ""
                    lat = coords[1] if has_geo else ""
                    loc = props.get("location") if isinstance(props.get("location"), dict) else {}
                    name = loc.get("name") or props.get("Title") or props.get("name") or ""
                    if _looks_coord(name):
                        name = ""
                    addr = loc.get("address") or props.get("address") or ""
                    country = (loc.get("country_code") or props.get("country_code") or "").strip()
                    # ~22% of saved places have no name field — recover name/address/country from
                    # the map URL's ?q= param (e.g. "?q=Caumasee,+7018+Flims,+Switzerland").
                    if not name:
                        u_name, u_addr, u_cc = _place_from_maps_url(props.get("google_maps_url", ""))
                        name = u_name
                        addr = addr or u_addr
                        country = country or u_cc
                    if not name or _looks_coord(name):
                        continue  # nameless / bare-coordinate pin → skip
                    # country as a filterable tag (e.g. place/country/RO) so the graph can
                    # group by geography; the full address already carries the country name.
                    tags = [f"place/country/{country.upper()}"] if country else None
                    # keep the star rating with the review so nothing is lost
                    rating = props.get("five_star_rating_published")
                    review = props.get("review_text_published", "") or ""
                    if rating and kind == "reviewed":
                        review = (f"★{rating} — " + review).strip(" —")
                    col.add_place(NAME, name=name, address=addr, lat=lat, lng=lng,
                                  url=props.get("google_maps_url", ""),
                                  note=review, date=props.get("date", ""),
                                  kind=kind, tags=tags)
                    pl += 1
            # Consume EVERY Maps .json (GeoJSON or not) — the non-GeoJSON Maps files
            # (commute routes, vehicle profiles, Q&A, photo geo-metadata, …) carry no
            # importable entity, but they are accounted-for Maps data, not "unmapped"
            # files that should fall to the harvester as uncategorized noise.
            consumed.add(key)
            continue

        # ---- Saved/*.csv place lists -> places --------------------------
        # Real Google Takeout puts saved places in Saved/<list name>.csv
        # (Title,Note,URL,Tags,Comment) — no address/coords. Keep the LIST name
        # (e.g. "Favorite places", "Want to go") as the meaningful detail; add_place
        # MERGES this with the richer Saved Places.json entry by name.
        if sfx == ".csv" and "/saved/" in lp:
            list_name = p.stem.strip()  # the .csv filename == the list's name
            for r in read_csv(p):
                name = (r.get("Title") or "").strip()
                url = (r.get("URL") or "").strip()
                if not name or _looks_coord(name):
                    name = _name_from_place_url(url)
                if not name or _looks_coord(name):
                    continue
                extra = [f"place/tag/{t.strip()}"
                         for t in re.split(r"[;,]", (r.get("Tags") or "")) if t.strip()]
                col.add_place(NAME, name=name, url=url,
                              note=(r.get("Comment") or r.get("Note") or "").strip(),
                              kind="saved", category=list_name, tags=extra)
                pl += 1
            consumed.add(key)
            continue

        # ---- Maps/Your local followed places/*.csv -> places ------------
        if sfx == ".csv" and "followed places" in lp:
            for r in read_csv(p):
                name = (r.get("Place") or "").strip()
                if not name or _looks_coord(name):
                    continue
                col.add_place(NAME, name=name, address=(r.get("Address") or "").strip(),
                              url=(r.get("URL") or "").strip(), kind="followed")
                pl += 1
            consumed.add(key)
            continue

        # ---- Chrome bookmarks / reading list -> interests ---------------
        # Netscape-bookmark HTML: <A HREF="…">Title</A>. The saved page titles are a
        # real interest signal; cap so a huge bookmark tree can't bloat the vault.
        if sfx == ".html" and "chrome" in lp and ("bookmark" in lp or "reading list" in lp):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for t in re.findall(r"<A[^>]*>([^<]+)</A>", text, flags=re.I)[:300]:
                t = _html.unescape(t).strip()
                if t:
                    col.add_interest(NAME, t)
                    yc += 1
            consumed.add(key)
            continue

        # ---- Chrome history / settings / extensions (skipped, by design) ----
        # No importable entity (and history can be enormous) — consumed AND flagged
        # `skipped` so _COVERAGE.md reports it honestly (never a silent drop).
        if "chrome" in lp and sfx in (".json", ".html", ".csv"):
            consumed.add(key)
            col.skipped_keys.add(key)
            continue

        # ---- Semantic Location History -> aggregated place visits ---------
        # Takeout/Location History (or Timeline)/Semantic Location History/<year>/
        # <year>_<MONTH>.json — placeVisit entries carry name/address + E7 coords.
        # Aggregate by place (visit count), emit the top places after the loop —
        # a decade of visits must become a map layer, not 50k notes.
        if sfx == ".json" and "semantic location history" in lp:
            data = read_json(p) or {}
            for obj in (data.get("timelineObjects") or []):
                v = obj.get("placeVisit") if isinstance(obj, dict) else None
                if not isinstance(v, dict):
                    continue
                loc = v.get("location") or {}
                nm = (loc.get("name") or "").strip()
                if not nm:
                    continue
                lat, lng = loc.get("latitudeE7"), loc.get("longitudeE7")
                rec = visits.setdefault(nk(nm), {
                    "name": nm, "address": (loc.get("address") or "").split("\n")[0],
                    "lat": (lat / 1e7) if isinstance(lat, (int, float)) else "",
                    "lng": (lng / 1e7) if isinstance(lng, (int, float)) else "",
                    "n": 0})
                rec["n"] += 1
            consumed.add(key)
            continue

        # ---- raw Location History pings / Timeline edits (skipped, by design) ----
        # Records.json is surveillance-grade raw GPS (can be GB-scale). Deliberately
        # never parsed — visits above carry the human-meaningful signal.
        if sfx == ".json" and ("location history" in lp or "timeline" in lp):
            consumed.add(key)
            col.skipped_keys.add(key)
            continue

        # ---- My Activity -> searches (Search) / ad segments (Ads) ---------
        # Takeout/My Activity/<Product>/MyActivity.json|.html. Search history is a
        # strong long-run intent graph; Ads activity is the algorithmic mirror.
        # Other products (Maps, Assistant, …) are skipped-by-design.
        if "my activity" in lp and p.stem.lower() == "myactivity":
            product = p.parent.name.lower()
            if product == "search" and ac < _SEARCH_CAP:
                if sfx == ".json":
                    for e in (read_json(p) or []):
                        t = (e.get("title") or "") if isinstance(e, dict) else ""
                        if t.lower().startswith("searched for"):
                            q = t[12:].strip()
                            if q:
                                col.add_search(NAME, q)
                                ac += 1
                                if ac >= _SEARCH_CAP:
                                    break
                elif sfx == ".html":
                    try:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        text = ""
                    for raw in re.findall(
                            r"Searched for\s*(?:<a[^>]*>)?([^<]{1,120})", text)[:_SEARCH_CAP - ac]:
                        q = _html.unescape(raw).strip()
                        if q:
                            col.add_search(NAME, q)
                            ac += 1
                consumed.add(key)
            elif product == "ads":
                if sfx == ".json":
                    for e in (read_json(p) or [])[:200]:
                        t = (e.get("title") or "") if isinstance(e, dict) else ""
                        if t:
                            col.add_ad_segment(NAME, t)
                            mac += 1
                consumed.add(key)
                if sfx == ".html":
                    col.skipped_keys.add(key)  # ads html variant: skipped (json preferred)
            else:
                consumed.add(key)
                col.skipped_keys.add(key)
            continue

        # ---- YouTube liked videos (likes.csv / Liked videos.csv) ----------
        if sfx == ".csv" and p.name.lower() in ("likes.csv", "liked videos.csv"):
            n_likes, titled = 0, 0
            for r in read_csv(p):
                n_likes += 1
                t = (r.get("Video Title") or r.get("Title") or "").strip()
                if t:
                    col.add_interest(NAME, t)
                    titled += 1
            if n_likes:
                col.add_reaction(NAME, "like")
                col.reactions["like"] += n_likes - 1
                yc += titled
            consumed.add(key)
            continue

        # ---- YouTube comments (comments.csv) -> voice ----------------------
        if sfx == ".csv" and "comment" in lp and "youtube" in lp:
            for r in read_csv(p):
                txt = (r.get("Comment Text") or r.get("Comment text") or "").strip()
                if txt:
                    col.add_comment(NAME, txt,
                                    iso_date(r.get("Comment Create Timestamp")
                                             or r.get("Timestamp") or ""))
            consumed.add(key)
            continue

        # ---- Google Photos EXIF sidecars -> aggregated photo places -------
        # <IMG>.jpg.json sidecars carry photoTakenTime + geoData; never the image.
        # Aggregate by ~1 km cell so a day of shots in one area becomes one pin.
        if sfx == ".json" and ("google photos" in lp or "/photos from " in lp):
            data = read_json(p) or {}
            geo = data.get("geoData") or {}
            lat, lng = geo.get("latitude"), geo.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) \
                    and (lat, lng) != (0.0, 0.0):
                cell = (round(lat, 2), round(lng, 2))
                ts = _dig(data, "photoTakenTime", "timestamp")
                rec = photos.setdefault(cell, {"lat": lat, "lng": lng, "n": 0,
                                               "date": iso_date(str(ts))})
                rec["n"] += 1
            consumed.add(key)
            continue

        # ---- Mail mbox / Fit / Drive / Keep / Play (excluded by design) ----
        # Personal email, health data, raw files and app libraries never enter a
        # brain (see docs) — consumed + flagged skipped so coverage stays honest.
        if sfx == ".mbox" or any(seg in ("fit", "drive", "keep", "google play store",
                                         "google pay", "mail")
                                 for seg in (s.lower() for s in p.parts)):
            consumed.add(key)
            col.skipped_keys.add(key)
            continue

        # ---- YouTube subscriptions.csv -> interests ---------------------
        if sfx == ".csv" and "subscription" in lp:
            for r in read_csv(p):
                ch = r.get("Channel Title") or r.get("Channel title") or r.get("Title") or ""
                if ch.strip():
                    col.add_interest(NAME, ch.strip())
                    yc += 1
            consumed.add(key)
            continue

        # ---- YouTube playlists.csv -> interests -------------------------
        if sfx == ".csv" and "playlist" in lp and p.name.lower() == "playlists.csv":
            for r in read_csv(p):
                t = (r.get("Playlist Title (Original)") or r.get("Playlist Title")
                     or r.get("Title") or "").strip()
                if t:
                    col.add_interest(NAME, t)
                    yc += 1
            consumed.add(key)
            continue

        # ---- YouTube saved-video playlists (<name>-videos.csv) -> interests ----
        # Each Saved/<list>-videos.csv is one of your playlists (Favorites, Watch
        # later, …). Keep the playlist NAME as a single interest (not thousands of
        # video-id rows) so the saved-video lists aren't lost as uncategorized.
        if sfx == ".csv" and "playlist" in lp and p.name.lower().endswith("-videos.csv"):
            pl_name = re.sub(r"-videos$", "", p.stem, flags=re.I).strip()
            if pl_name and pl_name.lower() != "playlists":
                col.add_interest(NAME, f"YouTube playlist: {pl_name}")
                yc += 1
            consumed.add(key)
            continue

        # ---- YouTube watch-history.html -> interests (channels) ---------
        if sfx == ".html" and "watch-history" in lp:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            seen = set()
            for raw in _RE_CHANNEL.findall(text):
                ch = _html.unescape(raw).strip()
                k = nk(ch)
                if ch and k and k not in seen:
                    seen.add(k)
                    col.add_interest(NAME, ch)
                    wc += 1
                    if wc >= _WATCH_CAP:
                        break
            consumed.add(key)
            continue

        # ---- YouTube search-history.html -> searches --------------------
        if sfx == ".html" and "search-history" in lp:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for raw in _RE_QUERY.findall(text):
                q = _html.unescape(raw).strip()
                if q:
                    col.add_search(NAME, q)
                    sc += 1
                    if sc >= _SEARCH_CAP:
                        break
            consumed.add(key)
            continue

    # ---- emit aggregated Semantic Location History visits (top 200) --------
    for rec in sorted(visits.values(), key=lambda r: -r["n"])[:200]:
        note = f"{rec['n']} visit(s) recorded in Location History" if rec["n"] > 1 else ""
        col.add_place(NAME, name=rec["name"], address=rec["address"],
                      lat=rec["lat"], lng=rec["lng"], kind="visited",
                      note=note, tags=["place/visited"])
    # ---- emit aggregated Photos EXIF places (top 200 cells) ---------------
    # NOTE: keep titles digit-light — "Photo spot 2024-04-01 (3 photos)" reads
    # like a phone number to PII sweeps; the date/count go in note + frontmatter.
    for i, rec in enumerate(sorted(photos.values(), key=lambda r: -r["n"])[:200]):
        col.add_place(NAME, name=f"Photo spot {i + 1}",
                      lat=rec["lat"], lng=rec["lng"], kind="photo",
                      date=rec["date"],
                      note=f"{rec['n']} photo(s) taken here"
                           + (f" around {rec['date']}" if rec["date"] else ""),
                      tags=["place/photo"])

    if visits:
        col.note(f"[google] {sum(v['n'] for v in visits.values())} location-history "
                 f"visits → {min(len(visits), 200)} places")
    if photos:
        col.note(f"[google] {sum(v['n'] for v in photos.values())} geotagged photos "
                 f"→ {min(len(photos), 200)} photo spots (EXIF sidecars only)")
    if ac or mac:
        col.note(f"[google] My Activity: {ac} searches, {mac} ad segments")
    if pc:
        col.note(f"[google] {pc} contacts")
    if ec:
        col.note(f"[google] {ec} calendar events")
    if pl:
        col.note(f"[google] {pl} places (maps/saved)")
    if yc:
        col.note(f"[google] {yc} YouTube subscriptions/playlists")
    if wc:
        col.note(f"[google] {wc} YouTube channels (watch history)")
    if sc:
        col.note(f"[google] {sc} YouTube searches")

    return consumed
