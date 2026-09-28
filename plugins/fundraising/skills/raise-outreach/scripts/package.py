#!/usr/bin/env python3
"""
package.py - one package per target per day: the fundraising twin of a job application folder.

    <fundraising layer>/outreach/<YYYY-MM-DD>/<key>/
        brief.md      who they are — every claim with its stamp, people, possible warm paths,
                      and what memory says (recalled, item ids cited)
        fit.md        the 100-point fit score with its working, and the band
        email.md      the draft + the two buttons (written by the agent, buttons by `mail`)
        review.json   the independent investor review (the agent saves the reviewer's JSON)
        gates.json    lint + review (lint_claims.py)

    python3 package.py init   KEY [--day D]
    python3 package.py fit    KEY [--comparable N --why "…"] [--timing-note "…"]
    python3 package.py mail   KEY            # write the ✉ / ✓ buttons + mailto into email.md
    python3 package.py adopt  KEY FLAT_NOTE  # MOVE an older flat draft in as email.md
    python3 package.py status KEY            # GATES: PASS | FAIL — why
    python3 package.py path   KEY            # print the package folder

Nothing here sends anything. The ✉ button opens a NEW message in the founder's own mail
app; the ✓ button types "I sent the … email" into the agent chat — the founder's own turn.
"""
import argparse, datetime, json, os, pathlib, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# the shared library: a sibling skill in the Claude packaging, the same folder in Codex's
for cand in (HERE, os.path.join(HERE, "..", "..", "raise-research", "scripts")):
    if os.path.isfile(os.path.join(cand, "ledger.py")):
        sys.path.insert(0, os.path.abspath(cand))
        LIB = os.path.abspath(cand)
        break
else:
    sys.exit("package.py: cannot find the shared scripts (ledger.py)")

import ledger as L  # noqa: E402
import founder_profile as prof  # noqa: E402
import mailto as M  # noqa: E402
from paths import render_dir, brain_layer  # noqa: E402
from lint_claims import gates_ok  # noqa: E402

TODAY = datetime.date.today().isoformat()
SAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')
BUTTON_MARK = "<!-- sbl:buttons -->"


def title_name(rec):
    return SAFE.sub("", rec["name"]).strip()


def pkg_dir(key, day=None, create=False):
    base = render_dir() / "outreach"
    if day:
        d = base / day / key
    else:
        found = sorted(base.glob(f"*/{key}"), key=lambda p: p.parent.name) if base.is_dir() else []
        d = found[-1] if found else base / TODAY / key
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def fm_block(pairs, tags):
    def v(x):
        if x is None:
            return '""'
        x = str(x)
        return '"' + x.replace('"', '\\"') + '"' if re.search(r'[:#\[\]{}&*!|>\'"%@`]', x) or x != x.strip() else x
    return "---\n" + "\n".join(f"{k}: {v(val)}" for k, val in pairs) + \
        "\ntags: [" + ", ".join(tags) + "]\n---\n\n"


def recall(tags="targeting,outreach,review"):
    mem = os.path.join(LIB, "memory.py")
    if not os.path.isfile(mem):
        return ""
    try:
        r = subprocess.run([sys.executable, mem, "recall", "--scope", "fundraising", "--tags", tags,
                            "--budget", "800"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def warm_paths(rec, limit=8):
    """10-people notes whose org/company mentions this target — NAME-ONLY, so 'possible'."""
    d = brain_layer("people")
    if d is None or not d.is_dir():
        return []
    want = L.norm_name(rec["name"])
    if len(want) < 4:
        return []
    hits = []
    for p in d.glob("*.md"):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:1500]
        except OSError:
            continue
        m = re.search(r"^(?:company|org|organization|employer):\s*(.+)$", head, re.M | re.I)
        if m and want in L.norm_name(re.sub(r"[\[\]\"]", "", m.group(1))):
            hits.append(p.stem)
            if len(hits) >= limit:
                break
    return hits


def cmd_init(a):
    recs = L.load()
    rec = L.need(recs, a.key)
    d = pkg_dir(rec["key"], a.day or TODAY, create=True)
    name = title_name(rec)
    out = [fm_block([("type", "fundraising-brief"), ("title", f"{name} brief {d.parent.name}"),
                     ("target", f"[[{name} (target)]]"), ("tier", rec.get("tier")),
                     ("fit", rec.get("fit")), ("updated", TODAY)],
                    ["fundraising", "fundraising/brief"]),
           f"# {rec['name']} — brief\n",
           f"**Why this one:** {rec.get('why') or '—'}\n",
           "## Claims\n\n| Field | Value | Stamp | Source | Checked |\n|---|---|---|---|---|"]
    for f, c in sorted(rec["claims"].items()):
        v = c.get("v")
        if isinstance(v, dict):
            v = ", ".join(f"{k} {x}" for k, x in v.items())
        out.append(f"| {f} | {str(v).replace('|', '/')} | {c.get('stamp', '⚠')} | "
                   f"{str(c.get('src') or '—').replace('|', '/')} | {c.get('at') or '—'} |")
    if rec.get("people"):
        out.append("\n## People\n")
        out += [f"- {p.get('name')}" + (f" — {p['role']}" if p.get("role") else "")
                + (f" — {p['why']}" if p.get("why") else "") for p in rec["people"]]
    if rec.get("origin_text"):
        out.append("\n## What the lists said (unverified)\n")
        out += [f"- {t}" for t in rec["origin_text"]]
    wp = warm_paths(rec)
    out.append("\n## Possible warm paths\n")
    out += ([f"- [[{p}]] — possible (name-only match on the organisation)" for p in wp]
            or ["- none found in 10-people"])
    mem = recall()
    out.append("\n## From memory\n")
    out.append(mem if mem else "- none yet")
    (d / "brief.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(json.dumps({"key": rec["key"], "package": str(d), "brief": "brief.md",
                      "warm_paths": len(wp), "memory": bool(mem)}))


def _best_stamp(c):
    return (c or {}).get("stamp", "📋")


def score(rec, rs, comparable=0, comp_why=""):
    """[(dimension, points, max, evidence)] — the mechanical part of the rubric."""
    v = {f: (rec.get("verdicts") or {}).get(f, {}) for f in prof.FILTERS}
    rows = []
    th, st = v["thesis"].get("v"), _best_stamp(rec["claims"].get("thesis"))
    k = {"pass": 1.0 if st == "✅" else 0.7, "unknown": 0.4, "fail": 0.0}.get(th, 0.4)
    rows.append(("Thesis match", round(30 * k), 30, f"{th or 'unknown'} {st} — {v['thesis'].get('why', '')}"))
    lo, hi = L.cash_range(rec)
    floor = float(rs.get("min_net_cash") or 0)
    if lo is not None and lo >= floor:
        pts, ev = 20, f"from {int(lo):,} ≥ floor"
    elif hi is not None and hi >= floor:
        pts, ev = 12, f"up to {int(hi):,} — low end unknown"
    elif hi is not None:
        pts, ev = 0, f"up to {int(hi):,} < floor"
    else:
        pts, ev = 6, "cheque unknown"
    rows.append(("Cheque & stage", pts, 20, ev))
    g = v["geo"].get("v")
    rows.append(("Geography & eligibility", {"pass": 15, "conditional": 10, "unknown": 6}.get(g, 0), 15,
                 f"{g or 'unknown'} — {v['geo'].get('why', '')}"))
    cp = rec["claims"].get("cold_path") or {}
    cpv = str(cp.get("v") or "").lower()
    if cp and "warm" in cpv and not re.search(r"form|@|email|typeform|tally", cpv):
        pts, ev = 2, "warm intro only"
    elif cp:
        pts, ev = (10 if cp.get("stamp") == "✅" else 6), f"{cp.get('v')} {cp.get('stamp')}"
    else:
        pts, ev = 0, "no cold path found"
    rows.append(("Access", pts, 10, ev))
    rows.append(("Comparable deals", max(0, min(15, comparable)), 15, comp_why or "not assessed yet"))
    dl, yc = L.deadline_of(rec)
    if dl is None:
        open_v = str((rec["claims"].get("status_open") or {}).get("v") or "")
        pts, ev = (10, "rolling / open") if ("rolling" in open_v or rec["kind"] != "program") else (6, "no date")
    else:
        days = (dl - datetime.date.today()).days
        pts = 0 if days < 0 else 3 if days < 7 else 8
        ev = f"deadline {dl} ({days} days){'' if yc else ' — year ⚠'}"
    rows.append(("Timing", pts, 10, ev))
    return rows


def band(total, rec):
    hook = any(c.get("stamp") == "✅" for f, c in rec["claims"].items() if f in ("thesis", "notes", "portfolio_signal"))
    if total >= 75:
        return "prepare"
    if total >= 60:
        return "prepare" if hook else "prepare-if-hook"
    return "park"


def cmd_fit(a):
    recs = L.load()
    rec = L.need(recs, a.key)
    d = pkg_dir(rec["key"], a.day, create=True)
    rows = score(rec, prof.round_settings(), a.comparable or 0, a.why or "")
    total = sum(r[1] for r in rows)
    b = band(total, rec)
    fp = d / "fit.md"
    keep = ""
    if fp.is_file():  # the agent's judgement lines survive a re-score
        m = re.search(r"^## Objections to pre-empt\s*$(.*)", fp.read_text(encoding="utf-8"), re.M | re.S)
        keep = m.group(1).strip() if m else ""
    name = title_name(rec)
    out = [fm_block([("type", "fundraising-fit"), ("title", f"{name} fit {d.parent.name}"),
                     ("target", f"[[{name} (target)]]"), ("score", total), ("band", b), ("updated", TODAY)],
                    ["fundraising", "fundraising/fit"]),
           f"# {rec['name']} — fit {total}/100 · **{b}**\n",
           "| Dimension | Points | Max | Evidence |\n|---|---|---|---|"]
    out += [f"| {n} | {p} | {m} | {str(e).replace('|', '/')} |" for n, p, m, e in rows]
    out.append("\nBands: ≥ 75 prepare · 60–74 prepare only with a ✅ hook · < 60 park.\n")
    out.append("## Objections to pre-empt\n\n" + (keep or "- (the agent writes up to three here)"))
    fp.write_text("\n".join(out) + "\n", encoding="utf-8")
    with L.Lock():
        recs = L.load()
        r = recs[rec["key"]]
        r["fit"] = max(1, min(10, round(total / 10)))
        r["fit_score"] = total
        r["updated"] = TODAY
        L.save(recs)
    print(json.dumps({"key": rec["key"], "score": total, "band": b, "fit": round(total / 10)}))


def split_fm(text):
    """(frontmatter lines, body) — body without the button block or an old mailto footer."""
    fm_lines, body = [], text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            fm_lines = text[4:end].split("\n")
            body = text[end + 4:].lstrip("-").lstrip("\n")
    body = body.split(BUTTON_MARK)[0]
    body = re.split(r"\n---\n\s*(?:\[Open in mail\]|Send through the fund's form)", body)[0]
    return fm_lines, body.strip() + "\n"


def cmd_mail(a):
    recs = L.load()
    rec = L.need(recs, a.key)
    d = pkg_dir(rec["key"], a.day)
    ep = d / "email.md"
    if not ep.is_file():
        sys.exit(f"no email.md in {d} — draft it first")
    text = ep.read_text(encoding="utf-8")
    fm_lines, body = split_fm(text)
    fm = prof.frontmatter("---\n" + "\n".join(fm_lines) + "\n---\n") if fm_lines else {}
    to = str(fm.get("to") or "").strip()
    subject = str(fm.get("subject") or "").strip()
    url, fallback = M.build(to, subject, body)
    ask = "sbl-ask:" + M.quote(f"I sent the {rec['name']} email", safe="")
    lines = [BUTTON_MARK, "", "---", ""]
    if to:
        lines.append(f"[✉ Open in Mail — pre-filled]({url})   ·   [✓ I sent it]({ask})")
        if fallback:
            lines.append("\n> [!note] Long email — the button fills the recipient and subject; copy the body above.")
    else:
        cold = str((rec["claims"].get("cold_path") or {}).get("v") or rec.get("url") or "")
        lines.append(f"No email address — send through the fund's own path: {cold}   ·   [✓ I sent it]({ask})")
    keep = [l for l in fm_lines if not l.startswith("mailto:")]
    if to:
        keep.append(f'mailto: "{url}"')
    fm_text = ("---\n" + "\n".join(keep) + "\n---\n\n") if fm_lines else ""
    ep.write_text(fm_text + body + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"key": rec["key"], "email": str(ep), "mailto": bool(to), "fallback": fallback,
                      "length": len(url)}))


def cmd_adopt(a):
    recs = L.load()
    rec = L.need(recs, a.key)
    src = pathlib.Path(a.flat_note)
    if not src.is_file():
        sys.exit(f"no such note: {src}")
    day = a.day or (src.parent.name if re.fullmatch(r"\d{4}-\d{2}-\d{2}", src.parent.name) else TODAY)
    d = pkg_dir(rec["key"], day, create=True)
    dst = d / "email.md"
    if dst.exists():
        sys.exit(f"refused: {dst} already exists")
    shutil.move(str(src), str(dst))           # a move, never copy + delete
    old_gates = src.parent / f"{rec['key']}.gates.json"
    if old_gates.is_file() and not (d / "gates.json").exists():
        shutil.move(str(old_gates), str(d / "gates.json"))
    print(json.dumps({"key": rec["key"], "moved": str(src), "to": str(dst)}))


def cmd_status(a):
    d = pkg_dir(a.key, a.day)
    ok, why = gates_ok(d)
    print("GATES:", "PASS" if ok else "FAIL — " + why)
    sys.exit(0 if ok else 1)


def cmd_path(a):
    print(pkg_dir(a.key, a.day))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, f in (("init", cmd_init), ("fit", cmd_fit), ("mail", cmd_mail), ("status", cmd_status),
                 ("path", cmd_path)):
        g = sub.add_parser(n); g.add_argument("key"); g.add_argument("--day"); g.set_defaults(f=f)
        if n == "fit":
            g.add_argument("--comparable", type=int, default=0)
            g.add_argument("--why", default="")
    g = sub.add_parser("adopt"); g.add_argument("key"); g.add_argument("flat_note")
    g.add_argument("--day"); g.set_defaults(f=cmd_adopt)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
