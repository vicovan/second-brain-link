#!/usr/bin/env python3
"""
mail.py - send and read email through the seller's OWN mailbox. Stdlib only (smtplib, imaplib).

No managed inboxes, no sending service, no tracking pixels, no link redirects. One real
mailbox, at a human volume, under the caps in sending.md - and every send passes
send_guard.py first, here, in this process, before a socket is opened.

The mailbox settings are in sending.md (`smtp_host`, `smtp_port`, `imap_host`, `imap_port`,
`mail_user`, `from_name`, `signature`). The password is never in the brain:

    $SBL_MAIL_PASSWORD               set for one session, or
    the macOS Keychain               service "second-brain-sales", account = mail_user
                                     (store it with `mail.py keychain-set`, which asks for it
                                     in the terminal - the password is never an argument)

For Gmail / Google Workspace use an app password (2-step verification on); for Microsoft 365
use an app password or the account's SMTP AUTH; any IMAP/SMTP host works.

    mail.py check                    log in to SMTP and IMAP, send nothing
    mail.py keychain-set             store the password in the Keychain (interactive)
    mail.py send --account KEY --contact NAME --to ADDR --subject S --body-file F
                 [--kind first|follow-up|reply] [--reply-class C] [--in-reply-to MSGID]
                 [--batch ID] [--step N] [--dry-run] [--sink HOST:PORT]
                     guard -> send -> log `sent` (message id kept for threading)
                     --dry-run   guard + build, never connects
                     --sink      deliver to a local test SMTP server instead (tests)
    mail.py read [--days 7] [--json] read replies from the people the ledger has written to
                     (BODY.PEEK: nothing is marked as read)
"""
import argparse, datetime, email.utils, getpass, imaplib, json, os, re, smtplib, ssl, subprocess, sys
from email.header import decode_header, make_header
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402
import send_guard  # noqa: E402

KEYCHAIN_SERVICE = "second-brain-sales"


def cfg():
    s = prof.sending()
    return {"smtp_host": s.get("smtp_host", ""), "smtp_port": prof.as_int(s.get("smtp_port"), 465),
            "imap_host": s.get("imap_host", ""), "imap_port": prof.as_int(s.get("imap_port"), 993),
            "user": s.get("mail_user", ""), "from_name": s.get("from_name", ""),
            "signature": s.get("signature", "").replace("\\n", "\n"), "opt_out": s.get("opt_out", "")}


def password(user):
    pw = os.environ.get("SBL_MAIL_PASSWORD")
    if pw:
        return pw
    if sys.platform == "darwin" and user:
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", user, "-w"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def _ctx():
    try:
        import certifi  # noqa: PLC0415
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:                                     # noqa: BLE001
        return ssl.create_default_context()


def smtp_open(c):
    if c["smtp_port"] == 465:
        s = smtplib.SMTP_SSL(c["smtp_host"], 465, context=_ctx(), timeout=30)
    else:
        s = smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=30)
        s.starttls(context=_ctx())
    s.login(c["user"], password(c["user"]))
    return s


def build(c, to, subject, body, in_reply_to=""):
    m = EmailMessage()
    m["From"] = email.utils.formataddr((c["from_name"], c["user"])) if c["from_name"] else c["user"]
    m["To"] = to
    m["Subject"] = subject
    m["Date"] = email.utils.formatdate(localtime=True)
    dom = c["user"].split("@", 1)[1] if "@" in c["user"] else "localhost"
    m["Message-ID"] = email.utils.make_msgid(domain=dom)
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    if c["user"]:
        m["List-Unsubscribe"] = f"<mailto:{c['user']}?subject=no%20thanks>"
    text = body.rstrip()
    if c["signature"] and c["signature"].strip() not in text:
        text += "\n\n" + c["signature"].strip()
    m.set_content(text + "\n")
    return m


def cmd_send(a):
    c = cfg()
    try:
        body = open(a.body_file, encoding="utf-8").read()
    except OSError as e:
        print(f"BLOCK cannot read the message: {e}")
        return 1
    body = re.sub(r"^---\n.*?\n---\n", "", body, flags=re.S).strip()
    verdict, rule = send_guard.check("email", a.account, a.contact, body, a.to, a.kind,
                                     a.reply_class, a.batch, a.step)
    if verdict != "ALLOW":
        print(f"{verdict} {rule}")
        return send_guard.EXIT[verdict]
    msg = build(c, a.to, a.subject, body, a.in_reply_to)
    acc = ledger.load_accounts()
    rec = ledger.find(acc, a.account) or {}
    if a.dry_run:
        ledger.log("sent", account=rec.get("key") or a.account, contact=a.contact, channel="email",
                   batch=a.batch, step=a.step, message_id=msg["Message-ID"], subject=a.subject, dry_run=True)
        print(f"DRY RUN - would send to {a.to}: {a.subject}")
        return 0
    try:
        if a.sink:
            host, port = a.sink.rsplit(":", 1)
            with smtplib.SMTP(host, int(port), timeout=10) as s:
                s.send_message(msg)
        else:
            if not (c["smtp_host"] and c["user"]):
                print("BLOCK no mailbox configured - set smtp_host and mail_user in sending.md")
                return 1
            if not password(c["user"]):
                print("BLOCK no mailbox password - run `mail.py keychain-set` or set SBL_MAIL_PASSWORD")
                return 1
            s = smtp_open(c)
            try:
                s.send_message(msg)
            finally:
                s.quit()
    except (OSError, smtplib.SMTPException) as e:
        ledger.log("send_failed", account=rec.get("key") or a.account, contact=a.contact, channel="email",
                   error=str(e)[:300], batch=a.batch)
        print(f"FAILED {e}")
        return 1
    ledger.log("sent", account=rec.get("key") or a.account, contact=a.contact, channel="email",
               batch=a.batch, step=a.step, message_id=msg["Message-ID"], subject=a.subject,
               msg_kind=a.kind, sink=bool(a.sink))
    if rec and rec.get("stage") in ("lead", "target"):
        ledger.set_stage(acc, rec, "sequenced", "agent", "first email sent")
        ledger.save_accounts(acc)
    print(f"SENT {msg['Message-ID']} → {a.to}")
    return 0


def _dec(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:                                     # noqa: BLE001
        return v or ""


def _text(m):
    if m.is_multipart():
        for part in m.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    return part.get_content()
                except Exception:                         # noqa: BLE001
                    return (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        return ""
    try:
        return m.get_content()
    except Exception:                                     # noqa: BLE001
        return (m.get_payload(decode=True) or b"").decode("utf-8", "replace")


def cmd_read(a):
    """Replies from people the ledger has written to. The seller's own mailbox, read in place."""
    import email as _email  # noqa: PLC0415
    from email import policy  # noqa: PLC0415
    c = cfg()
    if not (c["imap_host"] and c["user"] and password(c["user"])):
        print("no IMAP mailbox configured (imap_host + mail_user in sending.md, and a password)", file=sys.stderr)
        return 1
    acc = ledger.load_accounts()
    written = {}
    for e in ledger.events(kind="sent"):
        if e.get("channel") != "email" or e.get("dry_run"):
            continue
        rec = acc.get(e.get("account") or "", {})
        for ct in rec.get("contacts") or []:
            if ledger.name_key(ct.get("name")) == ledger.name_key(e.get("contact")) and ct.get("email"):
                written[ct["email"].lower()] = (rec["key"], ct["name"])
    if not written:
        print("[]")
        return 0
    since = (datetime.date.today() - datetime.timedelta(days=a.days)).strftime("%d-%b-%Y")
    out = []
    M = imaplib.IMAP4_SSL(c["imap_host"], c["imap_port"], ssl_context=_ctx())
    try:
        M.login(c["user"], password(c["user"]))
        M.select("INBOX", readonly=True)
        for addr, (akey, cname) in written.items():
            typ, data = M.search(None, "SINCE", since, "FROM", f'"{addr}"')
            if typ != "OK":
                continue
            for num in (data[0] or b"").split()[-20:]:
                typ, msgd = M.fetch(num, "(BODY.PEEK[])")
                if typ != "OK" or not msgd or not isinstance(msgd[0], tuple):
                    continue
                m = _email.message_from_bytes(msgd[0][1], policy=policy.default)
                out.append({"account": akey, "contact": cname, "from": addr,
                            "subject": _dec(m.get("Subject")), "date": m.get("Date", ""),
                            "message_id": m.get("Message-ID", ""), "in_reply_to": m.get("In-Reply-To", ""),
                            "text": _text(m)[:4000]})
    finally:
        try:
            M.logout()
        except Exception:                                 # noqa: BLE001
            pass
    seen = {e.get("message_id") for e in ledger.events(kind="reply_read")}
    fresh = [r for r in out if r["message_id"] not in seen]
    print(json.dumps(fresh if not a.all else out, indent=2, ensure_ascii=False))
    print(f"{len(fresh)} new replies ({len(out)} in the window)", file=sys.stderr)
    return 0


def cmd_check():
    c = cfg()
    if not c["user"]:
        print("no mail_user in sending.md")
        return 1
    if not password(c["user"]):
        print("no password - run `mail.py keychain-set` or set SBL_MAIL_PASSWORD")
        return 1
    ok = True
    if c["smtp_host"]:
        try:
            s = smtp_open(c)
            s.quit()
            print(f"SMTP ok  {c['smtp_host']}:{c['smtp_port']} as {c['user']}")
        except (OSError, smtplib.SMTPException) as e:
            ok = False
            print(f"SMTP failed: {e}")
    if c["imap_host"]:
        try:
            M = imaplib.IMAP4_SSL(c["imap_host"], c["imap_port"], ssl_context=_ctx())
            M.login(c["user"], password(c["user"]))
            M.logout()
            print(f"IMAP ok  {c['imap_host']}:{c['imap_port']}")
        except (OSError, imaplib.IMAP4.error) as e:
            ok = False
            print(f"IMAP failed: {e}")
    print("nothing was sent")
    return 0 if ok else 1


def cmd_keychain_set():
    c = cfg()
    if sys.platform != "darwin":
        print("the Keychain is macOS only - set SBL_MAIL_PASSWORD for the session instead")
        return 1
    if not c["user"]:
        print("set mail_user in sending.md first")
        return 1
    if not sys.stdin.isatty():
        print("run this in a terminal (in Claude Code: `! python3 …/mail.py keychain-set`) - it asks for the password")
        return 1
    pw = getpass.getpass(f"App password for {c['user']} (stored in the macOS Keychain): ")
    if not pw:
        return 1
    # -w is given the value on stdin through `security -i`, so it never appears in a process list
    q = pw.replace("\\", "\\\\").replace('"', '\\"')
    cmd = f'add-generic-password -U -s "{KEYCHAIN_SERVICE}" -a "{c["user"]}" -w "{q}"\n'
    r = subprocess.run(["security", "-i"], input=cmd, text=True, capture_output=True)
    print("stored" if r.returncode == 0 else f"failed: {r.stderr.strip()}")
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("keychain-set")
    g = sub.add_parser("send")
    for f in ("account", "contact", "to", "subject", "body-file"):
        g.add_argument("--" + f, required=True)
    g.add_argument("--kind", default="first"); g.add_argument("--reply-class", default="")
    g.add_argument("--in-reply-to", default=""); g.add_argument("--batch", default="")
    g.add_argument("--step", type=int); g.add_argument("--dry-run", action="store_true")
    g.add_argument("--sink", default="")
    g = sub.add_parser("read"); g.add_argument("--days", type=int, default=7)
    g.add_argument("--all", action="store_true"); g.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return cmd_check()
    if a.cmd == "keychain-set":
        return cmd_keychain_set()
    if a.cmd == "send":
        return cmd_send(a)
    return cmd_read(a)


if __name__ == "__main__":
    sys.exit(main())
