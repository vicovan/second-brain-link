#!/usr/bin/env python3
"""
sales_profile.py - read the seller's profile. The profile is the only source of what may be said
and of every setting the deterministic gates enforce.

The profile lives in <sales layer>/profile/, written only by sales-onboarding:

    offer.md        what you sell, to whom, proof points, the "## Do not claim" list
    icp.md          segments, buyer and need roles, markets, signal weights, exclusions, floor
    sending.md      level, social_auto, caps, quiet hours, mailbox, signature, opt-out line
    voice.md        tone rules on top of the brain's own voice layer
    suppression.md  do-not-contact — one "- value — reason — date" line each, append-only
    materials/      deck, one-pager, case studies (the facts the claims linter reads)

Settings are the `key: value` lines inside each file's first fenced block. A list is
comma-separated. Dotted keys group: `market.Iberia: lisbon|madrid`, `weight.hiring: 3`,
`cap.email: 25`.

    python3 sales_profile.py show [offer|icp|sending]     # parsed settings as JSON
    python3 sales_profile.py check                         # what is missing before a run
"""
import json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import profile_dir  # noqa: E402

FENCE = re.compile(r"```[a-z]*\n(.*?)\n```", re.S)
KV = re.compile(r"^\s*-?\s*([A-Za-z_][\w.\-]*)\s*:\s*(.*?)\s*$")

# What the deterministic gates fall back to when a setting is absent. Conservative on purpose.
SENDING_DEFAULTS = {
    "level": "supervised", "social_auto": "off", "eu_gate": "on",
    "cap.email": "25", "cap.linkedin_invite": "10", "cap.linkedin_dm": "15", "cap.x_dm": "10",
    "cap.whatsapp": "10", "cap.form": "10", "max_sends_per_run": "25",
    "quiet_start": "08:00", "quiet_end": "18:00", "days": "MON,TUE,WED,THU,FRI",
    "timezone": "UTC", "min_social_gap_s": "90", "max_social_gap_s": "300",
    "autonomous_gated_batches": "3", "smtp_port": "465", "imap_port": "993",
    "opt_out": "Reply 'no thanks' and I won't write again.",
}
ICP_DEFAULTS = {"floor": "60", "daily_target": "10", "half_life_days": "30",
                "weight.hiring": "3", "weight.funding": "2", "weight.exec_hire": "2",
                "weight.migration": "3", "weight.expansion": "1", "weight.event": "1",
                "weight.intent": "3", "weight.news": "1", "weight.brain": "2",
                "weight.revival": "3", "weight.directory": "1", "weight.registry": "1",
                "weight.lookalike": "2"}
LEVELS = ("draft", "supervised", "autonomous")


def _read(name, pdir=None):
    p = pathlib.Path(pdir or profile_dir()) / name
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def settings(name, pdir=None):
    """The `key: value` lines of the file's first fenced block, as a dict of strings."""
    txt = _read(name if name.endswith(".md") else name + ".md", pdir)
    m = FENCE.search(txt)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if line.strip().startswith("#"):
            continue
        k = KV.match(line)
        if k and k.group(2) != "":
            out[k.group(1)] = k.group(2)
    return out


def studio_sending(pdir=None):
    """sending.json - written by Studio's Sales Agent settings (the Sending tab). Its keys win
    over sending.md's: it is the newer of the two surfaces and only ever holds known choices."""
    p = pathlib.Path(pdir or profile_dir()) / "sending.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in d.items() if k != "schema" and v not in (None, "")} \
        if isinstance(d, dict) else {}


def sending(pdir=None):
    s = dict(SENDING_DEFAULTS)
    s.update(settings("sending", pdir))
    s.update(studio_sending(pdir))
    if s.get("level") not in LEVELS:
        s["level"] = "supervised"            # unreadable or unknown -> the shipped default
    return s


def icp(pdir=None):
    s = dict(ICP_DEFAULTS)
    s.update(settings("icp", pdir))
    return s


def offer(pdir=None):
    return settings("offer", pdir)


def on(v):
    return str(v or "").strip().lower() in ("on", "true", "yes", "1", "y")


def as_list(v):
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def as_int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def markets(icp_s):
    """{name: compiled regex} from `market.<Name>: regex` keys."""
    out = {}
    for k, v in icp_s.items():
        if k.startswith("market."):
            try:
                out[k[7:]] = re.compile(v, re.I)
            except re.error:
                out[k[7:]] = re.compile(re.escape(v), re.I)
    return out


def weights(icp_s):
    return {k[7:]: float(v) for k, v in icp_s.items()
            if k.startswith("weight.") and re.match(r"^-?\d+(\.\d+)?$", str(v))}


def section(name, heading, pdir=None):
    """The bullet lines under `## <heading>` in a profile file (e.g. the do-not-claim list)."""
    txt = _read(name if name.endswith(".md") else name + ".md", pdir)
    m = re.search(r"^##\s+" + re.escape(heading) + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S | re.I)
    if not m:
        return []
    return [re.sub(r"^\s*[-*]\s+", "", l).strip() for l in m.group(1).splitlines()
            if re.match(r"^\s*[-*]\s+\S", l)]


def corpus(pdir=None):
    """Every word the seller has said about themselves: profile files + text materials.
    The claims linter accepts a number only when it appears in here."""
    d = pathlib.Path(pdir or profile_dir())
    parts = []
    for f in ("offer.md", "voice.md", "icp.md"):
        parts.append(_read(f, d))
    mat = d / "materials"
    if mat.is_dir():
        for f in sorted(mat.rglob("*")):
            if f.is_file() and f.suffix.lower() in (".md", ".markdown", ".txt"):
                try:
                    parts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    return "\n".join(parts)


def suppression(pdir=None):
    """Lower-cased do-not-contact values: emails, domains, organisation names."""
    out = []
    for line in _read("suppression.md", pdir).splitlines():
        m = re.match(r"^\s*-\s+(.+?)(?:\s+[—-]\s+.*)?$", line)
        if m:
            v = m.group(1).strip().strip("`").lower()
            if v and not v.startswith("<"):
                out.append(v)
    return out


def missing(pdir=None):
    d = pathlib.Path(pdir or profile_dir())
    gaps = []
    if not (d / "offer.md").is_file():
        gaps.append("offer.md (run sales-onboarding)")
    if not (d / "icp.md").is_file():
        gaps.append("icp.md")
    elif not markets(icp(d)):
        gaps.append("icp.md has no market.<Name> lines")
    if not (d / "sending.md").is_file():
        gaps.append("sending.md (autonomy, caps, mailbox)")
    return gaps


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "check"
    if cmd == "show":
        which = argv[1] if len(argv) > 1 else "sending"
        fn = {"sending": sending, "icp": icp, "offer": offer}.get(which)
        if not fn:
            print("show offer|icp|sending", file=sys.stderr)
            return 2
        print(json.dumps(fn(), indent=2, ensure_ascii=False))
        return 0
    gaps = missing()
    if gaps:
        print("profile incomplete:\n  - " + "\n  - ".join(gaps))
        return 1
    print(f"profile ok ({profile_dir()})  level={sending()['level']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
