#!/usr/bin/env python3
"""ledger_base.py - the one way every agent keeps records, events and rendered notes.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only,
no network, no model. Each plugin's own `ledger.py` / `learn.py` composes these pieces and
keeps its record file name (`targets.jsonl`, `accounts.jsonl`, `outcomes.jsonl`): nothing is
renamed by adopting this base.

    from ledger_base import Ledger, Writer, replace_between, lock

    L = Ledger(root, "accounts.jsonl", transitions=TRANSITIONS)
    recs = L.load()                              # list of dicts (keyed by `key`)
    L.transition(rec, "replied", by="reply")     # checks the table, appends one event
    L.save(recs)                                 # atomic replace under the plugin's lock
    L.count(["meeting", "trial"])                # how many records sit in those statuses
    L.count("to:meeting", days=7)                # how many events moved INTO a status lately
    L.table(["name", "status"], rows=recs)       # a Markdown table, never typed by a model
    L.since("2026-01-15")                        # events since a date
    L.due(today)                                 # records whose next.due has passed
    L.migrate({"target": "researched"})          # idempotent ID migration (+ .pre-migrate backup)

Three rules this file enforces for every agent:

  R6  Never destroy a hand edit. `Writer` rewrites a note only while its sha still matches the
      manifest; an edited (or foreign) note is kept and the fresh render lands beside it as
      `<name>.new.md`. Machine files (.json, .geojson) are always rewritten, atomically.
  R7  One writer per ledger. Every write goes through the plugin's `lock` file (fcntl where it
      exists); readers never block. Helpers return text to the main agent, which writes.
  R2  Numbers from scripts. `table`, `count`, `since` print what the ledger holds, verbatim,
      and `replace_between` drops that text between `<!-- name:begin -->` / `<!-- name:end -->`
      markers inside a note the model otherwise owns (the Funding Plan's ledger section).

    python3 ledger_base.py --selftest
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys

LOCK_NAME = "lock"
EVENTS = "events.jsonl"
MIGRATED = "migrated"


# ------------------------------------------------------------------ the lock (R7)
@contextlib.contextmanager
def lock(root):
    """The plugin's one lock: <root>/lock. Exclusive while held; a second writer waits."""
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / LOCK_NAME
    with open(p, "a+", encoding="utf-8") as fh:
        try:
            import fcntl  # noqa: PLC0415
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            fcntl = None  # type: ignore[assignment]  # Windows: the single-writer rule still holds
        try:
            yield
        finally:
            try:
                if fcntl:
                    fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                pass


# ------------------------------------------------------------------ JSONL
def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    print(f"warning: unreadable ledger line skipped: {line[:80]}", file=sys.stderr)
    except OSError:
        pass
    return out


def write_jsonl(path, rows):
    """Atomic: the whole file is written beside and renamed over. Call it under `lock`."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def append_jsonl(path, row):
    """One line, appended under the lock, flushed before the lock is released."""
    path = pathlib.Path(path)
    with lock(path.parent):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def now_iso():
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _day(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ the ledger
class Ledger:
    """Records + events + transitions for ONE plugin, parameterised by file name."""

    def __init__(self, root, record_file, key="key", status="status", transitions=None,
                 events_file=EVENTS, event_key="key", ts_field="at"):
        self.root = pathlib.Path(root)
        self.record_file = self.root / record_file
        self.key, self.status = key, status
        self.transitions = transitions or {}
        self.events_file = self.root / events_file
        self.event_key = event_key
        self.ts_field = ts_field          # "ts" for a ledger whose events already use that name

    # records
    def load(self):
        return read_jsonl(self.record_file)

    def by_key(self, recs=None):
        return {r.get(self.key): r for r in (recs if recs is not None else self.load()) if r.get(self.key)}

    def save(self, recs):
        with lock(self.root):
            write_jsonl(self.record_file, recs)

    # events
    def event(self, key, frm, to, by="agent", note="", **extra):
        e = {self.event_key: key, "from": frm, "to": to, "by": by, "at": now_iso()}
        if self.ts_field != "at":
            e[self.ts_field] = e["at"]
        if note:
            e["note"] = note
        e.update({k: v for k, v in extra.items() if v not in (None, "")})
        append_jsonl(self.events_file, e)
        return e

    def events(self, key=None, since=None, days=None):
        evs = read_jsonl(self.events_file)
        if key is not None:
            evs = [e for e in evs if e.get(self.event_key) == key]
        cut = None
        if days is not None:
            cut = (_dt.date.today() - _dt.timedelta(days=int(days))).isoformat()
        if since:
            cut = max(cut or "", str(since)[:10])
        if cut:
            evs = [e for e in evs if str(e.get("at") or e.get("ts") or "")[:10] >= cut]
        return evs

    def transition(self, rec, to, by="agent", note="", reason="", strict=True):
        """Move a record; the table decides. Returns the event, or raises ValueError."""
        frm = rec.get(self.status)
        if self.transitions and strict:
            if to not in self.transitions and to not in {t for v in self.transitions.values() for t in v}:
                raise ValueError(f"unknown status {to!r}")
            if frm is not None and to not in self.transitions.get(frm, set()) and to != frm:
                raise ValueError(f"{frm} -> {to} is not a move this ledger allows")
        rec[self.status] = to
        rec["updated"] = now_iso()
        rec.setdefault("history", []).append({"from": frm, "to": to, "at": rec["updated"], "by": by})
        return self.event(rec.get(self.key), frm, to, by, note, reason=reason)

    # numbers (R2)
    def count(self, what, days=None, recs=None):
        """`count(["a","b"])` = records in those statuses · `count("to:a")` = events into a status
        (optionally within N days) · `count("events:kind")` = events whose `kind` matches."""
        if isinstance(what, str) and what.startswith("to:"):
            tos = set(what[3:].split("|"))
            return sum(1 for e in self.events(days=days) if e.get("to") in tos)
        if isinstance(what, str) and what.startswith("events:"):
            kinds = set(what[7:].split("|"))
            return sum(1 for e in self.events(days=days) if e.get("kind") in kinds)
        sts = {what} if isinstance(what, str) else set(what)
        rows = recs if recs is not None else self.load()
        if days is not None:
            cut = (_dt.date.today() - _dt.timedelta(days=int(days))).isoformat()
            rows = [r for r in rows if str(r.get("updated") or "")[:10] >= cut]
        return sum(1 for r in rows if r.get(self.status) in sts)

    def since(self, date, recs=None):
        """What changed since a date: events grouped by key, newest first."""
        out = {}
        for e in self.events(since=date):
            out.setdefault(e.get(self.event_key), []).append(e)
        return out

    def due(self, today=None, recs=None, field="next"):
        """Records whose `<field>.due` is today or past, oldest first."""
        today = today or _dt.date.today().isoformat()
        rows = recs if recs is not None else self.load()
        out = []
        for r in rows:
            nx = r.get(field) or {}
            d = str(nx.get("due") or "")[:10] if isinstance(nx, dict) else ""
            if d and d <= today:
                out.append(r)
        return sorted(out, key=lambda r: (str((r.get(field) or {}).get("due")), str(r.get(self.key))))

    def migrate(self, mapping, by="migration", note="status id migration"):
        """Rewrite old status IDs to new ones, idempotently. A backup `<record file>.pre-migrate` is
        kept beside the ledger (written once, never overwritten); one `migrated` event per record
        changed. Events already written keep their old IDs - they are history."""
        recs = self.load()
        changed = []
        with lock(self.root):
            bak = self.record_file.with_name(self.record_file.name + ".pre-migrate")
            for r in recs:
                st = r.get(self.status)
                if st in mapping and mapping[st] != st:
                    r[self.status] = mapping[st]
                    r.setdefault("history", []).append({"from": st, "to": mapping[st], "at": now_iso(), "by": by})
                    changed.append((r.get(self.key), st, mapping[st]))
            if changed:
                if not bak.exists() and self.record_file.exists():
                    shutil.copy2(self.record_file, bak)
                write_jsonl(self.record_file, recs)
        for key, frm, to in changed:
            e = {self.event_key: key, "from": frm, "to": to, "by": by, "at": now_iso(), "note": note, "kind": MIGRATED}
            if self.ts_field != "at":
                e[self.ts_field] = e["at"]
            append_jsonl(self.events_file, e)
        return {"changed": len(changed), "backup": str(bak) if changed else ""}

    # tables (R2)
    @staticmethod
    def table(fields, rows, labels=None, sort=None, empty="_nothing yet_"):
        """A Markdown table: `fields` are record keys (dotted paths allowed), `labels` the header."""
        labels = labels or [f.split(".")[-1].replace("_", " ").title() for f in fields]
        if sort:
            rows = sorted(rows, key=sort)
        if not rows:
            return empty + "\n"
        out = ["| " + " | ".join(labels) + " |", "|" + "---|" * len(fields)]
        for r in rows:
            cells = []
            for f in fields:
                v = r
                for part in f.split("."):
                    v = v.get(part) if isinstance(v, dict) else None
                cells.append(cell(v))
            out.append("| " + " | ".join(cells) + " |")
        return "\n".join(out) + "\n"


def cell(v):
    """One table cell: no pipes, no newlines, lists joined, None blank."""
    if v is None:
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        v = ", ".join(f"{k} {x}" for k, x in v.items())
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


# ------------------------------------------------------------------ markers (R2)
def replace_between(text, name, body, heading=None):
    """Put `body` between `<!-- name:begin -->` and `<!-- name:end -->`. Missing markers: appended at
    the end (under `heading` when given). The rest of the note is never touched."""
    b, e = f"<!-- {name}:begin -->", f"<!-- {name}:end -->"
    body = body.rstrip("\n")
    block = f"{b}\n{body}\n{e}" if body else f"{b}\n{e}"
    pat = re.compile(re.escape(b) + r".*?" + re.escape(e), re.S)
    if pat.search(text):
        return pat.sub(lambda m: block, text, count=1)
    tail = (f"\n## {heading}\n\n" if heading else "\n") + block + "\n"
    return text.rstrip("\n") + "\n" + tail


def between(text, name):
    m = re.search(rf"<!-- {re.escape(name)}:begin -->\n?(.*?)\n?<!-- {re.escape(name)}:end -->", text, re.S)
    return m.group(1) if m else None


# ------------------------------------------------------------------ frontmatter aliases
def add_alias(text, alias):
    """Add `alias` to the note's `aliases:` list (Obsidian resolves [[Old title]] to it)."""
    alias = str(alias).strip()
    if not alias:
        return text
    m = re.match(r"\A\ufeff?---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return f"---\naliases:\n  - {json.dumps(alias, ensure_ascii=False)}\n---\n" + text
    fm = m.group(1)
    if re.search(r"^aliases:", fm, re.M):
        if re.search(r"^\s*-\s*\"?" + re.escape(alias) + r"\"?\s*$", fm, re.M) or f"[{alias}]" in fm or json.dumps(alias, ensure_ascii=False) in fm:
            return text
        inline = re.search(r"^aliases:\s*\[(.*?)\]\s*$", fm, re.M)
        if inline:
            items = [x.strip() for x in inline.group(1).split(",") if x.strip()]
            items.append(json.dumps(alias, ensure_ascii=False))
            fm = fm[:inline.start()] + "aliases: [" + ", ".join(items) + "]" + fm[inline.end():]
        else:
            fm = re.sub(r"^(aliases:\s*\n(?:\s*-\s*.*\n?)*)", lambda mm: mm.group(1).rstrip("\n") + f"\n  - {json.dumps(alias, ensure_ascii=False)}\n", fm, count=1, flags=re.M)
    else:
        fm = fm + f"\naliases:\n  - {json.dumps(alias, ensure_ascii=False)}"
    return text[:m.start(1)] + fm + text[m.end(1):]


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ the writer (R6)
class Writer:
    """Writes a rendered layer and remembers what it wrote in a manifest. A note the user edited
    (sha differs from the manifest) or one the renderer never wrote (not in the manifest) is kept;
    the fresh text lands beside it as `<name>.new.md` and the path is listed in `kept`."""

    def __init__(self, root, manifest_path, quiet=True):
        self.root = pathlib.Path(root)
        self.manifest_path = pathlib.Path(manifest_path)
        self.quiet = quiet
        self.old = self.read_manifest(self.manifest_path)
        self.man = {}
        self.wrote, self.same = 0, 0
        self.kept, self.new_beside = [], []

    @staticmethod
    def read_manifest(path):
        try:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return dict(data["files"])
        if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
            return dict(data)   # an older flat manifest {rel: sha}
        return {}

    def _say(self, msg):
        if not self.quiet:
            print(msg, file=sys.stderr)

    @staticmethod
    def _atomic(p, body):
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, p)

    def text(self, rel, body, machine=False):
        """Returns 'written' | 'same' | 'kept'."""
        rel = str(rel)
        p = self.root / rel
        digest = sha(body)
        is_note = rel.endswith(".md") and not machine
        if p.is_file():
            try:
                cur = p.read_text(encoding="utf-8")
            except OSError:
                cur = None
            if cur == body:
                self.man[rel] = digest
                self.same += 1
                return "same"
            if is_note and (rel not in self.old or sha(cur or "") != self.old[rel]):
                # R6: the user's (or a foreign) note - never overwritten
                self.kept.append(rel)
                self.man[rel] = self.old.get(rel, sha(cur or ""))
                beside = p.with_name(p.stem + ".new.md")
                try:
                    if not (beside.is_file() and beside.read_text(encoding="utf-8") == body):
                        self._atomic(beside, body)
                        self.new_beside.append(str(beside.relative_to(self.root)))
                except OSError:
                    pass
                self._say(f"  = {rel} (kept yours; fresh copy beside as {beside.name})")
                return "kept"
        self._atomic(p, body)
        self.man[rel] = digest
        self.wrote += 1
        self._say(f"  + {rel}")
        return "written"

    def binary(self, rel, src):
        rel = str(rel)
        p = self.root / rel
        try:
            data = pathlib.Path(src).read_bytes()
        except OSError:
            return "missing"
        self.man[rel] = hashlib.sha256(data).hexdigest()
        if p.is_file() and p.stat().st_size == len(data):
            self.same += 1
            return "same"
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)
        self.wrote += 1
        self._say(f"  + {rel}")
        return "written"

    def finish(self, extra=None):
        """Write the manifest. Returns the paths the previous render produced and this one did not
        (left in place - nothing is deleted)."""
        gone = sorted(k for k in self.old if k not in self.man)
        data = {"schema": 1, "generated": _dt.date.today().isoformat(), "files": self.man}
        if extra:
            data.update(extra)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic(self.manifest_path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        return gone

    def migrate_layout(self, moves, dry_run=False):
        """Standard-layout moves THROUGH the manifest: (old_rel, new_rel, alias_title). A file still
        matching its manifest sha is moved, gets `aliases: [old title]`, and the manifest follows.
        A user-edited file stays where it is and is listed under `left`. Nothing is deleted;
        an existing destination is never overwritten."""
        done, left, skipped = [], [], []
        for old_rel, new_rel, alias in moves:
            src, dst = self.root / old_rel, self.root / new_rel
            if not src.is_file():
                continue
            if dst.exists():
                skipped.append((old_rel, new_rel, "destination exists"))
                continue
            try:
                cur = src.read_text(encoding="utf-8")
            except OSError:
                skipped.append((old_rel, new_rel, "unreadable"))
                continue
            known = self.old.get(old_rel)
            if old_rel.endswith(".md") and (known is None or sha(cur) != known):
                left.append(old_rel)
                continue
            if dry_run:
                done.append((old_rel, new_rel))
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            body = add_alias(cur, alias) if (alias and old_rel.endswith(".md")) else cur
            self._atomic(dst, body)
            os.remove(src)
            self.old.pop(old_rel, None)
            self.old[new_rel] = sha(body)
            done.append((old_rel, new_rel))
        if done and not dry_run:
            data = {"schema": 1, "generated": _dt.date.today().isoformat(), "files": self.old}
            self._atomic(self.manifest_path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        return {"moved": done, "left": left, "skipped": skipped}


# ------------------------------------------------------------------ selftest
def _selftest():
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d) / "state"
        T = {"lead": {"researched", "out"}, "researched": {"sequenced"}, "sequenced": {"replied"}, "replied": set(), "out": set()}
        L = Ledger(root, "accounts.jsonl", transitions=T)
        recs = [{"key": "acme", "name": "Acme", "status": "lead", "next": {"due": (_dt.date.today() - _dt.timedelta(days=400)).isoformat(), "action": "call"}},
                {"key": "globex", "name": "Globex", "status": "lead"}]
        L.save(recs)
        assert [r["key"] for r in L.load()] == ["acme", "globex"]
        L.transition(recs[0], "researched", by="agent")
        try:
            L.transition(recs[0], "replied")
            raise AssertionError("illegal move accepted")
        except ValueError:
            pass
        L.save(recs)
        assert L.count("researched") == 1 and L.count("to:researched") == 1 and L.count("to:researched", days=1) == 1
        assert L.due()[0]["key"] == "acme"
        assert "| Acme | researched |" in L.table(["name", "status"], recs)
        assert L.since((_dt.date.today() - _dt.timedelta(days=1)).isoformat())["acme"][0]["to"] == "researched"
        r1 = L.migrate({"lead": "new_lead"})
        r2 = L.migrate({"lead": "new_lead"})
        assert r1["changed"] == 1 and r2["changed"] == 0 and (root / "accounts.jsonl.pre-migrate").is_file()
        assert sum(1 for e in L.events() if e.get("kind") == MIGRATED) == 1
        # markers
        t = replace_between("# Plan\n\n## Ledger\n\n<!-- ledger:begin -->\nold\n<!-- ledger:end -->\n\nmine", "ledger", "| a |\n")
        assert "old" not in t and "| a |" in t and t.endswith("mine")
        t2 = replace_between("# Plan\n", "ledger", "x", heading="Ledger")
        assert "## Ledger" in t2 and between(t2, "ledger") == "x"
        # aliases
        a = add_alias("---\ntype: x\n---\nbody", "Old name")
        assert "aliases:\n  - \"Old name\"" in a and add_alias(a, "Old name") == a
        a2 = add_alias("---\ntype: x\naliases: [\"A\"]\n---\n", "B")
        assert 'aliases: ["A", "B"]' in a2
        assert add_alias("no frontmatter", "T").startswith("---\naliases:")
        # the writer
        layer = pathlib.Path(d) / "layer"
        W = Writer(layer, root / "_GEN.json")
        assert W.text("A.md", "one\n") == "written" and W.text("p.json", "{}\n", machine=True) == "written"
        W.finish()
        (layer / "A.md").write_text("edited\n", encoding="utf-8")
        (layer / "B.md").write_text("foreign\n", encoding="utf-8")
        W = Writer(layer, root / "_GEN.json")
        assert W.text("A.md", "two\n") == "kept" and (layer / "A.new.md").read_text() == "two\n"
        assert W.text("B.md", "render\n") == "kept" and (layer / "B.new.md").is_file()
        assert W.text("p.json", "{\"a\":1}\n", machine=True) == "written"
        assert (layer / "A.md").read_text() == "edited\n"
        gone = W.finish()
        assert gone == [] and W.kept == ["A.md", "B.md"]
        # layout moves through the manifest
        W = Writer(layer, root / "_GEN.json")
        W.text("C.md", "---\ntype: c\n---\nc\n")
        W.finish()
        W = Writer(layer, root / "_GEN.json")
        rep = W.migrate_layout([("C.md", "sub/C new.md", "C"), ("A.md", "sub/A.md", "A")])
        assert rep["moved"] == [("C.md", "sub/C new.md")] and rep["left"] == ["A.md"]
        moved = (layer / "sub/C new.md").read_text()
        assert "aliases:\n  - \"C\"" in moved and not (layer / "C.md").exists()
        man = Writer.read_manifest(root / "_GEN.json")
        assert "sub/C new.md" in man and "C.md" not in man
    print("ledger_base: selftest ok")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(_selftest())
    print(__doc__.split("\n\n")[0])
    sys.exit(2)
