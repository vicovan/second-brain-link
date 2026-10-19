#!/usr/bin/env python3
"""
warm_rank.py - the leads the brain already holds. Deterministic, no network, no model.

Cloud sales tools start every customer on a bought list. This starts on the people and deals
the user's own exports already resolved:

    revival   a deal in the pipeline layer that was lost or stalled, at an account where a
              contact still holds a real tie
    warm      a decision-maker the brain marks warm
    dormant   a decision-maker gone quiet, but strong (strength >= 3)
    intro     an account where someone in ANOTHER brain (the _correlations/ brain beside a
              multi-entity build) knows a person there - the ask goes to that connector

The decision-maker rule is the same one analyze.py's `bd` goal uses (DM_ROLE_SIGNALS below is
copied from engine/scripts/analyze.py - keep the two in step).

    python3 warm_rank.py [--brain PATH] [--min-strength 3] [--out leads-brain.json]

Output rows are account records ready for `ledger.py upsert` (and for scout.py merge, which
reads them as one more source). A common name is matched by name only - the engine's identity
resolution is name-only today - so a tie found only through a name match is marked
`tie: possible` and never drives a send on its own.
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import brain_at_cwd, layer, correlations_dir  # noqa: E402

DM_ROLE_SIGNALS = ("founder", "co-founder", "ceo", "cto", "coo", "cfo", "cmo",
                   "cpo", "chief", "vp", "vice president", "head of", "head ",
                   "owner", "managing director", "director", "president", "partner")
LOST = re.compile(r"closed[\s_-]*lost|\blost\b|stalled|no decision|on hold|churn", re.I)
WON = re.compile(r"closed[\s_-]*won|\bwon\b", re.I)
LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def frontmatter(path):
    """Top-level scalar keys of a note's YAML frontmatter (lists are skipped)."""
    try:
        txt = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not txt.startswith("---"):
        return {}
    end = txt.find("\n---", 3)
    out = {}
    for line in txt[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def unlink(v):
    m = LINK.search(v or "")
    return (m.group(1) if m else (v or "")).strip()


def is_dm(role):
    r = (role or "").lower()
    return any(s in r for s in DM_ROLE_SIGNALS)


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def own_org(brain):
    """The brain's own organisations, never a lead: the org's own name, the person's employer, and
    every company where the identity note lists a current role ("(2025 – Present)")."""
    names = set()
    root = pathlib.Path(brain) / layer(brain, "root")
    for n in ("organization.md", "identity.md"):
        fm = frontmatter(root / n)
        for k in ("title", "name", "company", "current_company"):
            if fm.get(k):
                names.add(unlink(fm[k]).lower())
        try:
            body = (root / n).read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        for m in re.finditer(r"^- \*\*[^*]*\*\*\s+[—-]\s+\[\[([^\]|]+)[^\]]*\]\][^\n]*?\bPresent\)", body, re.M):
            names.add(m.group(1).strip().lower())
    return names


def people(brain):
    d = pathlib.Path(brain) / layer(brain, "people")
    out = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        fm = frontmatter(f)
        if fm.get("type") not in ("person", None, ""):
            continue
        name = fm.get("title") or f.stem
        out.append({"name": name, "note": f"{layer(brain, 'people')}/{f.stem}",
                    "company": unlink(fm.get("company")), "role": fm.get("role", ""),
                    "status": (fm.get("status") or "").lower(), "strength": _int(fm.get("strength")),
                    "last_contact": fm.get("last_contact", ""), "url": fm.get("url", ""),
                    "email": fm.get("email", ""), "relationship": fm.get("relationship", "")})
    return out


def deals(brain):
    d = pathlib.Path(brain) / layer(brain, "career")
    out = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        fm = frontmatter(f)
        if fm.get("type") != "deal" or (fm.get("kind") or "deal") != "deal":
            continue
        title = fm.get("title") or f.stem
        acct = unlink(fm.get("account"))
        if not acct:
            m = re.search(r"\(([^)]+)\)", title)
            acct = m.group(1) if m else ""
        stage = title.rsplit(" — ", 1)[1] if " — " in title else ""
        out.append({"title": title, "note": f"{layer(brain, 'career')}/{f.stem}", "account": acct,
                    "stage": stage, "date": fm.get("date", ""), "value": fm.get("value", "")})
    return out


def correlated(brain):
    """People who appear in 2+ brains: {name_key: [brain ids]} from the _correlations brain."""
    c = correlations_dir(brain)
    out = {}
    if not c or not (c / "people").is_dir():
        return out
    for f in c.glob("people/*.md"):
        head = f.read_text(encoding="utf-8", errors="replace").split("\n---", 1)[0]
        m = re.search(r"^appears_in:\s*\n((?:\s+-\s+.+\n?)+)", head, re.M)
        ids = re.findall(r"^\s+-\s+(\S+)\s*$", m.group(1), re.M) if m else []
        out[re.sub(r"[^a-z0-9]+", "", f.stem.lower())] = ids
    return out


def recency(last, today):
    try:
        days = (today - datetime.date.fromisoformat(str(last)[:10])).days
    except ValueError:
        return 0.3
    return max(0.1, 0.5 ** (days / 365.0))


def rank(brain, min_strength=3, today=None):
    today = today or datetime.date.today()
    mine = own_org(brain)
    ppl = [p for p in people(brain) if p["company"] and p["company"].lower() not in mine
           and p["relationship"] != "employee"]
    by_co = {}
    for p in ppl:
        by_co.setdefault(p["company"].lower(), []).append(p)
    names = {}
    for p in ppl:
        k = re.sub(r"[^a-z0-9]+", "", p["name"].lower())
        names[k] = names.get(k, 0) + 1
    corr = correlated(brain)
    accounts = {}

    def acct(name):
        k = name.lower()
        if k not in accounts:
            accounts[k] = {"name": name, "sources": ["brain"], "signals": [], "contacts": [],
                           "origin": None, "markets": []}
        return accounts[k]

    def contact(p, why):
        k = re.sub(r"[^a-z0-9]+", "", p["name"].lower())
        c = {"name": p["name"], "role": p["role"], "person_note": p["note"],
             "tie_strength": p["strength"], "last_contact": p["last_contact"],
             "profile_url": p["url"], "channels": [], "tie": "possible" if names.get(k, 0) > 1 else "brain",
             "why": why}
        if p["email"] and EMAIL.match(p["email"]):
            c["email"], c["email_source"] = p["email"], "brain"
            c["channels"].append("email")
        if "linkedin.com/in/" in (p["url"] or ""):
            c["channels"].append("linkedin")
        return c

    # 1. revival - lost or stalled deals with a contact still there
    for d in deals(brain):
        if not d["account"] or WON.search(d["stage"]) or not LOST.search(d["stage"] or "") \
                or d["account"].lower() in mine:
            continue
        a = acct(d["account"])
        a["origin"] = "revival"
        a.setdefault("deal_history", []).append(d["note"])
        a["signals"].append({"kind": "revival", "what": f"{d['stage'] or 'lost'} deal: {d['title']}",
                             "url": d["note"], "seen": d["date"], "source": "brain"})
        for p in sorted(by_co.get(d["account"].lower(), []), key=lambda p: -p["strength"]):
            a["contacts"].append(contact(p, "was on the account when the deal stalled"))
    # 2./3. warm and dormant-but-strong decision-makers
    for p in ppl:
        if not is_dm(p["role"]):
            continue
        if p["status"] == "warm":
            origin, why = "warm", "warm decision-maker"
        elif p["status"] == "dormant" and p["strength"] >= min_strength:
            origin, why = "dormant", "dormant but strong tie"
        else:
            continue
        a = acct(p["company"])
        if not a["origin"]:
            a["origin"] = origin
        if not any(c["name"] == p["name"] for c in a["contacts"]):
            a["contacts"].append(contact(p, why))
        a["signals"].append({"kind": "brain", "what": f"{why}: {p['name']} ({p['role']}, tie {p['strength']}/5)",
                             "url": p["note"], "seen": p["last_contact"], "source": "brain"})
    # 4. intro - a person also known in another brain (the connector is the other brain's owner)
    for p in ppl:
        k = re.sub(r"[^a-z0-9]+", "", p["name"].lower())
        if k in corr and len(corr[k]) > 1 and is_dm(p["role"]):
            a = acct(p["company"])
            if not a["origin"]:
                a["origin"] = "intro"
            for c in a["contacts"]:
                if c["name"] == p["name"]:
                    c["tie_via"] = "+".join(corr[k])
            if not any(c["name"] == p["name"] for c in a["contacts"]):
                c = contact(p, "known in another of your brains")
                c["tie_via"] = "+".join(corr[k])
                a["contacts"].append(c)
    rows = []
    for a in accounts.values():
        if not a["origin"]:
            continue
        # the buying team worth naming: decision-makers first, strongest tie first, at most six
        a["contacts"].sort(key=lambda c: (not is_dm(c.get("role")), -(c.get("tie_strength") or 0)))
        a["contacts"] = a["contacts"][:6]
        best = max((c.get("tie_strength") or 0) for c in a["contacts"]) if a["contacts"] else 0
        last = max((c.get("last_contact") or "" for c in a["contacts"]), default="")
        a["warmth"] = round(min(1.0, best / 5.0) * recency(last, today), 3) if best else 0.0
        rows.append(a)
    order = {"revival": 0, "warm": 1, "intro": 2, "dormant": 3}
    rows.sort(key=lambda a: (order.get(a["origin"], 9), -a["warmth"], a["name"].lower()))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--brain")
    ap.add_argument("--min-strength", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    brain = pathlib.Path(a.brain) if a.brain else brain_at_cwd()
    if not brain:
        print("not inside a brain - pass --brain", file=sys.stderr)
        return 1
    rows = rank(brain, a.min_strength)
    payload = {"source": "brain", "markets": [], "rows": rows}
    txt = json.dumps(payload, indent=2, ensure_ascii=False)
    if a.out:
        pathlib.Path(a.out).write_text(txt, encoding="utf-8")
    else:
        print(txt)
    by = {}
    for r in rows:
        by[r["origin"]] = by.get(r["origin"], 0) + 1
    print(f"brain leads: {len(rows)} accounts " + " · ".join(f"{k} {v}" for k, v in sorted(by.items())),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
