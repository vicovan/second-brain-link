#!/usr/bin/env python3
"""
send_guard.py - the one gate every outward act passes. Deterministic: no model, no network.

Every email, LinkedIn / X / WhatsApp step, contact-form submission and reply goes through
`check` first. mail.py calls it itself before it opens a socket (a second lock), and a social
or form step can only be logged as sent through `sent`, which refuses without a fresh ALLOW.

    send_guard.py check --channel email|linkedin_invite|linkedin_dm|x_dm|whatsapp|form
                        --account KEY --contact NAME [--to ADDRESS] --body-file F
                        [--kind first|follow-up|reply|connect|dm|form] [--reply-class C]
                        [--batch ID] [--step N] [--now ISO] [--json]
        prints   ALLOW
                 GATE <rule>      ask the owner (the approval card), then re-check with the
                                  approved --batch
                 ASSIST <rule>    social automation is off: prepare it, the owner presses Send
                 BLOCK <rule>     never sent; logged with the rule
        exit     0 ALLOW · 3 GATE · 4 ASSIST · 1 BLOCK

    send_guard.py sent --channel C --account KEY --contact NAME [--batch ID] [--step N]
                       [--message-id ID] [--evidence TEXT]
        log a social / form step as sent - only within 15 minutes of an ALLOW for it

The rules, in order (the first that fires decides):
  1  level `draft`                                  BLOCK
  2  recipient, domain or organisation on the do-not-contact list   BLOCK
  3  the contact unsubscribed, bounced or booked (or replied, for anything but a reply)   BLOCK
  4  email: the address is not on the account record, or is only a guessed pattern        BLOCK
  5  social: social automation is off                ASSIST;  a platform pause is on   BLOCK
  6  the channel's daily cap is reached             BLOCK
  7  outside working hours in the recipient's time zone   BLOCK (with the next window)
  8  social: less than the minimum gap since the last social action   BLOCK
  9  the message fails the claims linter (incl. the missing opt-out line)   BLOCK
 10  the very first real send, or the very first social action   GATE (always, any level)
 11  `supervised`: every send                       GATE
 12  `autonomous`: a first touch while fewer than `autonomous_gated_batches` batches were
     approved, an EU first touch while `eu_gate` is on, a reply that is not routine   GATE
A GATE is satisfied by `--batch ID` when the ledger holds `approved` for that batch (and no
`denied` after it).
"""
import argparse, datetime, hashlib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import lint_claims  # noqa: E402
import sales_profile as prof  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:                                      # pragma: no cover - Python < 3.9
    ZoneInfo = None

SOCIAL = ("linkedin_invite", "linkedin_dm", "x_dm", "whatsapp")
CHANNELS = ("email", "form") + SOCIAL
ROUTINE_REPLIES = ("meeting-ask", "info-ask", "ooo", "scheduling", "referral-thanks")
EXIT = {"ALLOW": 0, "GATE": 3, "ASSIST": 4, "BLOCK": 1}
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _now(s=None):
    if s:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def _tz(name):
    if ZoneInfo and name:
        try:
            return ZoneInfo(name)
        except Exception:                                 # noqa: BLE001
            pass
    return datetime.timezone.utc


def _hm(s, default):
    m = re.match(r"^(\d{1,2}):(\d\d)$", str(s or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else default


def _ts(e):
    try:
        return _now(e.get("ts"))
    except (TypeError, ValueError):
        return None


def contact_of(acc_rec, name):
    for c in (acc_rec or {}).get("contacts") or []:
        if ledger.name_key(c.get("name")) == ledger.name_key(name):
            return c
    return None


def is_eu(c, a):
    tz = (c or {}).get("tz") or (a or {}).get("tz") or ""
    reg = ((c or {}).get("region") or (a or {}).get("region") or "").lower()
    return reg in ("eu", "eea", "uk") or tz.startswith("Europe/")


def approved(batch, evs):
    if not batch:
        return False
    state = None
    for e in evs:
        if e.get("batch") == batch and e.get("kind") in ("approved", "denied"):
            state = e["kind"]
    return state == "approved"


def check(channel, account, contact, body, to="", kind="first", reply_class="", batch="",
          step=None, now=None, pdir=None, log=True):
    now = now or _now()
    snd = prof.sending(pdir)
    level = snd["level"]
    acc = ledger.load_accounts()
    a = ledger.find(acc, account) or {}
    akey = a.get("key") or account
    c = contact_of(a, contact)
    evs = ledger.events()

    def done(verdict, rule):
        sha = hashlib.sha256((body or "").encode("utf-8")).hexdigest()[:16]
        if log:
            ledger.log("guard", account=akey, contact=contact, channel=channel, verdict=verdict, rule=rule,
                       batch=batch, step=step, sha=sha, msg_kind=kind)
            if verdict == "BLOCK":
                ledger.log("send_blocked", account=akey, contact=contact, channel=channel, rule=rule, batch=batch)
            elif verdict == "GATE":
                ledger.log("gated", account=akey, contact=contact, channel=channel, rule=rule, batch=batch)
        return verdict, rule

    if channel not in CHANNELS:
        return done("BLOCK", f"unknown channel {channel}")
    if level == "draft":
        return done("BLOCK", "level is draft - nothing is sent")
    if not a:
        return done("BLOCK", "no such account in the ledger - research it first")
    if not c:
        return done("BLOCK", "this contact is not on the account record")

    # 2 do-not-contact
    supp = prof.suppression(pdir)
    to_l = (to or "").lower().strip()
    dom = to_l.split("@", 1)[1] if "@" in to_l else ""
    hay = {to_l, dom, (a.get("domain") or "").lower(), ledger.name_key(a.get("name")),
           ledger.name_key(contact)}
    for s in supp:
        if s in hay or ledger.name_key(s) in hay:
            return done("BLOCK", "on the do-not-contact list")

    # 3 stop events for this contact
    mine = [e for e in evs if e.get("account") == akey and ledger.name_key(e.get("contact")) == ledger.name_key(contact)]
    kinds = {e.get("kind") for e in mine}
    if kinds & {"unsubscribed", "bounced"}:
        return done("BLOCK", "the contact unsubscribed or the address bounced")
    if kind != "reply" and kinds & {"replied", "meeting_booked", "stopped"}:
        return done("BLOCK", "stop-on-reply: this contact replied, booked or was stopped - answer, do not sequence")

    # 4 the address itself
    if channel == "email":
        if not to_l:
            return done("BLOCK", "no address")
        if (c.get("email") or "").lower() != to_l:
            return done("BLOCK", "the address is not on the account record - record where it was published first")
        if c.get("email_source") not in ("brain", "public-page", "reply"):
            return done("BLOCK", "only a guessed address - a guess is never sent")

    # 5 social automation
    if channel in SOCIAL:
        until = snd.get("social_paused_until") or ""
        if until and until >= now.date().isoformat():
            return done("BLOCK", f"social steps paused until {until} after a platform warning")
        if not prof.on(snd.get("social_auto")):
            return done("ASSIST", "social automation is off - prepare it, the owner presses Send")

    # 6 caps (counted in the sender's day)
    stz = _tz(snd.get("timezone"))
    today = now.astimezone(stz).date()
    cap_key = {"email": "cap.email", "form": "cap.form"}.get(channel, "cap." + channel)
    cap = prof.as_int(snd.get(cap_key), 10)
    sent_today = sum(1 for e in evs if e.get("kind") == "sent" and e.get("channel") == channel
                     and not e.get("dry_run") and _ts(e) and _ts(e).astimezone(stz).date() == today)
    if sent_today >= cap:
        return done("BLOCK", f"daily cap reached ({sent_today} of {cap} {channel} today)")
    if batch:
        in_batch = sum(1 for e in evs if e.get("kind") == "sent" and e.get("batch") == batch and not e.get("dry_run"))
        if in_batch >= prof.as_int(snd.get("max_sends_per_run"), 25):
            return done("BLOCK", "max_sends_per_run reached for this batch")

    # 7 working hours, recipient time
    rtz = _tz(c.get("tz") or a.get("tz") or snd.get("timezone"))
    local = now.astimezone(rtz)
    days = [d.strip().upper()[:3] for d in str(snd.get("days")).split(",") if d.strip()]
    h0, h1 = _hm(snd.get("quiet_start"), (8, 0)), _hm(snd.get("quiet_end"), (18, 0))
    hm = (local.hour, local.minute)
    if DAYS[local.weekday()] not in days or not (h0 <= hm < h1):
        return done("BLOCK", f"outside working hours for the recipient ({local.strftime('%a %H:%M')} {rtz}) - "
                             f"next window {days[0] if days else 'MON'} {h0[0]:02d}:{h0[1]:02d}")

    # 8 social spacing
    if channel in SOCIAL:
        last = max((_ts(e) for e in evs if e.get("kind") == "sent" and e.get("channel") in SOCIAL
                    and not e.get("dry_run") and _ts(e)), default=None)
        gap = prof.as_int(snd.get("min_social_gap_s"), 90)
        if last and (now - last).total_seconds() < gap:
            wait = int(gap - (now - last).total_seconds())
            return done("BLOCK", f"spacing - wait {wait}s before the next social action")

    # 9 the message
    first = kind in ("first", "connect", "form")
    r = lint_claims.lint(body or "", channel, pdir, first_touch=first)
    if not r["ok"]:
        return done("BLOCK", "claims linter: " + "; ".join(r["red"]))

    # 10-12 gates
    real_sent = [e for e in evs if e.get("kind") == "sent" and not e.get("dry_run")]
    ok_batch = approved(batch, evs)
    rules = []
    if not real_sent:
        rules.append("the first real send needs the owner's OK")
    if channel in SOCIAL and not any(e.get("channel") in SOCIAL for e in real_sent):
        rules.append("the first real social action needs the owner's OK")
    if level == "supervised":
        rules.append("supervised - every send is approved")
    elif level == "autonomous":
        never_sent = not any(e.get("kind") == "sent" for e in mine)
        n_approved = len({e.get("batch") for e in evs if e.get("kind") == "approved"})
        if never_sent and kind != "reply" and n_approved < prof.as_int(snd.get("autonomous_gated_batches"), 3):
            rules.append("first touches stay gated for the first batches")
        if never_sent and kind != "reply" and prof.on(snd.get("eu_gate")) and is_eu(c, a):
            rules.append("EU recipient - first touch is always approved")
        if kind == "reply" and (reply_class or "").lower() not in ROUTINE_REPLIES:
            rules.append("not a routine reply - pricing, legal and objections are yours")
    if rules and not ok_batch:
        return done("GATE", "; ".join(rules))
    return done("ALLOW", "approved batch " + batch if rules else "within your settings")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "sent"):
        g = sub.add_parser(name)
        g.add_argument("--channel", required=True); g.add_argument("--account", required=True)
        g.add_argument("--contact", required=True); g.add_argument("--batch", default="")
        g.add_argument("--step", type=int); g.add_argument("--now")
    g = sub.choices["check"]
    g.add_argument("--to", default=""); g.add_argument("--body-file", required=True)
    g.add_argument("--kind", default="first"); g.add_argument("--reply-class", default="")
    g.add_argument("--json", action="store_true")
    g = sub.choices["sent"]
    g.add_argument("--message-id", default=""); g.add_argument("--evidence", default="")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        try:
            body = open(a.body_file, encoding="utf-8").read()
        except OSError as e:
            print(f"BLOCK cannot read the message: {e}")
            return 1
        v, rule = check(a.channel, a.account, a.contact, body, a.to, a.kind, a.reply_class,
                        a.batch, a.step, _now(a.now) if a.now else None)
        print(json.dumps({"verdict": v, "rule": rule}) if a.json else f"{v} {rule}")
        return EXIT[v]
    # sent: only after a fresh ALLOW for exactly this act
    now = _now(a.now) if a.now else _now()
    acc = ledger.load_accounts()
    rec = ledger.find(acc, a.account) or {}
    akey = rec.get("key") or a.account
    ok = [e for e in ledger.events(account=akey, kind="guard")
          if e.get("verdict") == "ALLOW" and e.get("channel") == a.channel
          and ledger.name_key(e.get("contact")) == ledger.name_key(a.contact)
          and _ts(e) and 0 <= (now - _ts(e)).total_seconds() <= 900]
    if not ok:
        print("REFUSED - no ALLOW from send_guard.py check for this step in the last 15 minutes")
        return 1
    ledger.log("sent", account=akey, contact=a.contact, channel=a.channel, batch=a.batch, step=a.step,
               message_id=a.message_id, evidence=a.evidence[:500], ts=now.replace(microsecond=0).isoformat())
    if rec and rec.get("stage") in ("lead", "target"):
        ledger.set_stage(acc, rec, "sequenced", "agent", "first step sent")
        ledger.save_accounts(acc)
    print(f"sent logged: {a.channel} → {a.contact} @ {rec.get('name') or a.account}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
