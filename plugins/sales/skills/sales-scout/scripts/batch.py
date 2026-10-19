#!/usr/bin/env python3
"""
batch.py - one send batch, made reviewable: the messages in full, and the approval card.

When send_guard.py answers GATE, the messages are collected into ONE batch so the seller decides
once, with everything in front of them. This writes the batch as a note in the sales layer (the
real text of every message, the hook's source, the blocked rows and why) and prints the
```approval fence Second Brain Studio renders above the AskUserQuestion: the consequence line
with the cap counter, the note to open, one field per recipient with its source. In a terminal
the same note is the thing to read.

    batch.py add --batch B --account KEY --contact NAME --channel email --to ADDR
                 --subject S --body-file F [--hook-source "note or URL"] [--verdict GATE|BLOCK]
                 [--rule TEXT] [--step N]
    batch.py card --batch B          write <sales layer>/batches/Batch <B>.md, print the fence
    batch.py show --batch B [--json] what is in it

Nothing here sends anything, and approving is not done here: the seller answers the card, and
the agent records that answer with `ledger.py approve|deny --batch B`.
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402
from paths import render_dir, surface_root, is_brain  # noqa: E402

SOCIAL = ("linkedin_invite", "linkedin_dm", "x_dm", "whatsapp")
LABEL = {"email": "email", "linkedin_invite": "LinkedIn invite", "linkedin_dm": "LinkedIn message",
         "x_dm": "X message", "whatsapp": "WhatsApp", "form": "contact form"}


def safe_id(b):
    b = re.sub(r"[^A-Za-z0-9._-]+", "-", str(b or "")).strip("-")
    if not b:
        raise SystemExit("--batch needs an id (letters, digits, . _ -)")
    return b[:64]


def store(b):
    d = ledger.root() / "batches"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe_id(b)}.json"


def load(b):
    try:
        return json.loads(store(b).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"batch": safe_id(b), "items": []}


def save(b, data):
    p = store(b)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def sent_today(channel):
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    return sum(1 for e in ledger.events(kind="sent") if e.get("channel") == channel
               and not e.get("dry_run") and str(e.get("ts", ""))[:10] == today)


def note_rel(b):
    """The batch note, brain-relative (what Studio opens) and layer-relative (what Obsidian links)."""
    base = render_dir()
    name = f"Batch {safe_id(b)}.md"
    pre = base.name + "/" if is_brain(base.parent) else ""
    return pre + "batches/" + name, base / "batches" / name


def card(b):
    data = load(b)
    items = data["items"]
    if not items:
        raise SystemExit(f"batch {b} is empty")
    snd = prof.sending()
    ok = [i for i in items if i.get("verdict") != "BLOCK"]
    blocked = [i for i in items if i.get("verdict") == "BLOCK"]
    rel, path = note_rel(b)
    # the note: every message in full
    L = ["---", "type: sales-batch", f"title: Batch {safe_id(b)}", "tags:", "  - sales-batch",
         f"batch: {safe_id(b)}", f"messages: {len(ok)}", f"blocked: {len(blocked)}", "---", "",
         f"# Batch {safe_id(b)} — {len(ok)} to approve" + (f", {len(blocked)} blocked" if blocked else ""), ""]
    for n, i in enumerate(ok, 1):
        acc = ledger.find(ledger.load_accounts(), i["account"]) or {}
        L += [f"## {n}. {i['contact']} · {acc.get('name') or i['account']} · {LABEL.get(i['channel'], i['channel'])}", ""]
        if i.get("to"):
            L.append(f"**To:** {i['to']}  ")
        if i.get("subject"):
            L.append(f"**Subject:** {i['subject']}  ")
        if i.get("hook_source"):
            L.append(f"**Hook from:** {i['hook_source']}  ")
        L += ["", "```text", i.get("body", "").rstrip(), "```", ""]
    if blocked:
        L += ["## Blocked — not in this batch, never sent", ""]
        L += [f"- {i['contact']} · {i['account']} · {LABEL.get(i['channel'], i['channel'])} — {i.get('rule') or 'blocked'}" for i in blocked]
        L.append("")
    L += ["---", "", "Approving sends exactly these messages, within your caps. Email cannot be unsent."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    # the card
    by_ch = {}
    for i in ok:
        by_ch[i["channel"]] = by_ch.get(i["channel"], 0) + 1
    caps = []
    for ch, n in sorted(by_ch.items()):
        key = {"email": "cap.email", "form": "cap.form"}.get(ch, "cap." + ch)
        cap = prof.as_int(snd.get(key), 10)
        done = sent_today(ch)
        caps.append(f"{LABEL.get(ch, ch)} {done} of {cap} today → {done + n} after")
    who = snd.get("mail_user") or "your mailbox"
    parts = []
    if by_ch.get("email"):
        parts.append(f"{by_ch['email']} email{'s' if by_ch['email'] != 1 else ''} from {who}")
    soc = sum(n for ch, n in by_ch.items() if ch in SOCIAL)
    if soc:
        parts.append(f"{soc} social message{'s' if soc != 1 else ''} " +
                     ("sent by the agent in your browser" if prof.on(snd.get("social_auto")) else "you send yourself"))
    if by_ch.get("form"):
        parts.append(f"{by_ch['form']} contact form{'s' if by_ch['form'] != 1 else ''}")
    consequence = "Sends " + ", ".join(parts) + ". " + " · ".join(caps) + ". Cannot be unsent."
    fields = []
    for i in ok[:20]:
        acc = ledger.find(ledger.load_accounts(), i["account"]) or {}
        fields.append({"label": f"{i['contact']} · {acc.get('name') or i['account']}",
                       "value": (i.get("subject") or i.get("body", "").strip().split("\n", 1)[0])[:200],
                       "source": i.get("hook_source") or LABEL.get(i["channel"], i["channel"])})
    never = [f"{i['contact']} — {(i.get('rule') or 'blocked')[:70]}" for i in blocked[:10]]
    fence = {"consequence": consequence[:300], "irreversible": True, "artifact": rel, "fields": fields, "never": never}
    ledger.log("batch_ready", batch=safe_id(b), messages=len(ok), blocked=len(blocked))
    return fence, rel


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("add")
    for f in ("batch", "account", "contact", "channel"):
        g.add_argument("--" + f, required=True)
    for f in ("to", "subject", "body-file", "hook-source", "rule"):
        g.add_argument("--" + f, default="")
    g.add_argument("--verdict", default="GATE", choices=("GATE", "BLOCK", "ASSIST", "ALLOW"))
    g.add_argument("--step", type=int)
    g = sub.add_parser("card"); g.add_argument("--batch", required=True)
    g = sub.add_parser("show"); g.add_argument("--batch", required=True); g.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        body = ""
        if a.body_file:
            try:
                body = re.sub(r"^---\n.*?\n---\n", "", open(a.body_file, encoding="utf-8").read(), flags=re.S).strip()
            except OSError as e:
                print(f"cannot read {a.body_file}: {e}", file=sys.stderr)
                return 1
        data = load(a.batch)
        data["items"] = [i for i in data["items"] if not (i["account"] == a.account and
                         ledger.name_key(i["contact"]) == ledger.name_key(a.contact) and i["channel"] == a.channel)]
        data["items"].append({"account": a.account, "contact": a.contact, "channel": a.channel, "to": a.to,
                              "subject": a.subject, "body": body, "hook_source": a.hook_source,
                              "verdict": a.verdict, "rule": a.rule, "step": a.step})
        save(a.batch, data)
        print(f"batch {safe_id(a.batch)}: {len(data['items'])} item(s)")
        return 0
    if a.cmd == "card":
        fence, rel = card(a.batch)
        print("```approval")
        print(json.dumps(fence, ensure_ascii=False))
        print("```")
        print(f"(the full batch: {rel})", file=sys.stderr)
        return 0
    data = load(a.batch)
    if a.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for i in data["items"]:
            print(f"{i['verdict']:<6} {i['channel']:<16} {i['contact']:<22} {i['account']}  {i.get('subject') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
