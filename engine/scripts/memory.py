#!/usr/bin/env python3
"""memory.py - the Second Brain memory layer (sbl-memory/1). Stdlib only, no network.

SHIPPED BYTE-IDENTICAL in every plugin (job-search, fundraising, travel-planner); the plugin build
fails if the copies differ. Design: second-brain-link-docs/docs-memory/SBL-MEMORY-ARCHITECTURE.md.

Memory lives in the user's brain, in plain files they own:

    <brain>/_memory/
      <scope>.md            rendered, readable in Obsidian / Studio (brain, shared, one per agent)
      Memory.md             index      Review.md   inferred items waiting for approval
      .store/<scope>.jsonl  the source of truth: an append-only event log per scope

Sources (enforced HERE, not by asking the model):
  source user    -> active at once   (the user said it: a preference, a correction, a thumbs-down)
  source outcome -> active at once   (a verifiable result: a reply, a rejection, a rating, a failed gate)
  source agent   -> active at once by DEFAULT (the user's choice), flagged "inferred" so the
                    user can remove it; a brain whose policy is "review" (`memory.py policy review`)
                    keeps inferences pending until the user approves them

A repeated observation REINFORCES an existing item (strength up, evidence appended) instead of
adding a duplicate. The caller (the model) decides whether an observation means the same thing as
an existing item by reading `list --json` and passing `--match ID`; without it, only a normalised
exact match reinforces. Recall ranks active items by scope, tags, strength and recency, within a
token budget, and stamps `last_used`. Nothing is ever deleted automatically.

    memory.py recall  --scope S [--tags a,b] [--budget 1200] [--json]
    memory.py observe --scope S --kind K --source user|outcome|agent --text "..."
                      [--tags a,b] [--evidence "ref|quote"] [--match ID | --new] [--supersedes ID]
    memory.py list    --scope S [--status active|pending|retired|all] [--json]
    memory.py review  [--scope S]
    memory.py approve ID [--edit "text"]        memory.py reject ID --reason "..."
    memory.py approve-all [--scope S]           memory.py policy [auto|review]
    memory.py retire  ID --reason "..."         memory.py forget ID
    memory.py render  [--scope S]               memory.py sync
    memory.py import  --scope S --lessons FILE [--observations FILE] [--legacy job|fund|travel]
    memory.py stats   [--json]
Global: --brain PATH (else $SBL_BRAIN, else walk up from the cwd, else $SBL_MEMORY_HOME,
else ~/.second-brain/memory).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import sys

SCHEMA = "sbl-memory/1"
KINDS = ("preference", "rule", "fact", "lesson", "correction")
SOURCES = ("user", "outcome", "agent")
STATUSES = ("active", "pending", "retired", "forgotten")
START_STRENGTH = {"user": 3, "outcome": 2, "agent": 1}
BUMP = {"user": 3, "outcome": 1, "agent": 1}
MAX_STRENGTH = 20
SCOPE_LABEL = {
    "brain": "Second Brain",
    "shared": "About you (every agent)",
    "job-search": "Jobs Agent",
    "fundraising": "Fundraising Agent",
    "travel-planner": "Travel Agent",
}
SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")

# Never keep secrets in memory (field-policy NEVER-TYPE classes).
SECRET_RES = [
    re.compile(r"(?i)\b(pass(word|wd)?|pwd|secret|api[_ -]?key|token)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),  # IBAN-shaped
]


def _luhn_card(text: str) -> bool:
    for m in re.finditer(r"(?:\d[ -]?){13,19}", text):
        digits = [int(c) for c in re.sub(r"\D", "", m.group(0))]
        if not 13 <= len(digits) <= 19:
            continue
        total = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        if total % 10 == 0:
            return True
    return False


def looks_secret(text: str) -> bool:
    return any(r.search(text) for r in SECRET_RES) or _luhn_card(text)


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


# ------------------------------------------------------------------ where memory lives
# A brain root is recognised by the files the engine always writes at it (never by a layer
# folder name — plugins must not hardcode those; tests/run.py enforces it).
BRAIN_MARKERS = ("_STRUCTURE.md", "_GENERATED.json", "graph.json")


def _is_brain(d: pathlib.Path) -> bool:
    return (d / "_memory").is_dir() or any((d / m).is_file() for m in BRAIN_MARKERS)


def find_brain(explicit: str | None = None) -> pathlib.Path | None:
    for cand in (explicit, os.environ.get("SBL_BRAIN")):
        if cand:
            p = pathlib.Path(cand).expanduser()
            if p.is_dir():
                return p.resolve()
    here = pathlib.Path.cwd().resolve()
    for d in [here, *here.parents]:
        if _is_brain(d):
            return d
        # a plugin's hidden ledger: <brain>/.plugins/<plugin>/...
        if d.name == ".plugins" and _is_brain(d.parent):
            return d.parent
    return None


def memory_dir(brain: str | None = None) -> pathlib.Path:
    b = find_brain(brain)
    if b:
        return b / "_memory"
    home = os.environ.get("SBL_MEMORY_HOME")
    return pathlib.Path(home).expanduser() if home else pathlib.Path.home() / ".second-brain" / "memory"


class Store:
    """The event logs under <memory>/.store. All writes hold one lock."""

    def __init__(self, brain: str | None = None):
        self.dir = memory_dir(brain)
        self.store = self.dir / ".store"

    # -- locking
    def __enter__(self):
        self.store.mkdir(parents=True, exist_ok=True)
        self._lf = open(self.store / ".lock", "a+")
        try:
            import fcntl  # noqa: PLC0415  (absent on Windows: no lock, single writer assumed)

            fcntl.flock(self._lf, fcntl.LOCK_EX)
        except ImportError:
            pass
        return self

    def __exit__(self, *exc):
        try:
            import fcntl  # noqa: PLC0415

            fcntl.flock(self._lf, fcntl.LOCK_UN)
        except ImportError:
            pass
        self._lf.close()

    # -- events
    def scopes(self) -> list[str]:
        if not self.store.is_dir():
            return []
        return sorted(p.stem for p in self.store.glob("*.jsonl"))

    def append(self, scope: str, ev: dict) -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        ev = dict(ev)
        ev.setdefault("at", now())
        with open(self.store / f"{scope}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def items(self, scope: str) -> dict[str, dict]:
        """Fold a scope's events into its current items."""
        out: dict[str, dict] = {}
        p = self.store / f"{scope}.jsonl"
        if not p.is_file():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            op, iid = ev.get("op"), ev.get("id")
            if op == "add" and iid:
                it = dict(ev.get("item") or {})
                it.setdefault("id", iid)
                out[iid] = it
                continue
            if op == "used":
                for u in ev.get("ids") or []:
                    if u in out:
                        out[u]["last_used"] = ev.get("at")
                continue
            it = out.get(iid or "")
            if not it:
                continue
            if op == "reinforce":
                it["strength"] = min(MAX_STRENGTH, int(it.get("strength", 1)) + int(ev.get("bump", 1)))
                if ev.get("evidence"):
                    it.setdefault("evidence", []).append(ev["evidence"])
                    it["evidence"] = it["evidence"][-12:]
                if ev.get("text"):
                    it["text"] = ev["text"]
                for t in ev.get("tags") or []:
                    if t not in it.setdefault("tags", []):
                        it["tags"].append(t)
                it["updated"] = ev.get("at")
            elif op == "status":
                it["status"] = ev.get("status")
                if ev.get("reason"):
                    it["reason"] = ev["reason"]
                it["updated"] = ev.get("at")
            elif op == "edit":
                if ev.get("text"):
                    it["text"] = ev["text"]
                if ev.get("tags") is not None:
                    it["tags"] = ev["tags"]
                it["updated"] = ev.get("at")
        return out

    def find(self, iid: str) -> tuple[str, dict] | None:
        for sc in self.scopes():
            its = self.items(sc)
            if iid in its:
                return sc, its[iid]
        return None


# ------------------------------------------------------------------ policy
POLICIES = ("auto", "review")


def get_policy(brain: str | None = None) -> str:
    """How an agent's inferences are saved: "auto" (active, the default) or "review" (pending)."""
    p = Store(brain).store / "policy.json"
    try:
        v = json.loads(p.read_text(encoding="utf-8")).get("inferences")
        return v if v in POLICIES else "auto"
    except (OSError, ValueError):
        return "auto"


def set_policy(mode: str, brain: str | None = None) -> str:
    if mode not in POLICIES:
        raise ValueError(f"policy must be one of {', '.join(POLICIES)}")
    st = Store(brain)
    st.store.mkdir(parents=True, exist_ok=True)
    (st.store / "policy.json").write_text(json.dumps({"inferences": mode, "updated": now()}) + "\n", encoding="utf-8")
    return mode


def _new_id(scope: str, text: str) -> str:
    h = hashlib.sha1(f"{scope}|{text}|{now()}|{os.getpid()}".encode()).hexdigest()[:6]
    return f"m-{_dt.date.today():%Y%m%d}-{h}"


def _evidence(raw: str | None, source: str) -> dict | None:
    if not raw:
        return None
    ref, _, quote = str(raw).partition("|")
    return {"at": now(), "ref": ref.strip() or source, "quote": quote.strip()[:400]}


# ------------------------------------------------------------------ the operations
def observe(
    scope: str,
    kind: str,
    source: str,
    text: str,
    tags: list[str] | None = None,
    evidence: str | None = None,
    match: str | None = None,
    new: bool = False,
    supersedes: str | None = None,
    brain: str | None = None,
) -> dict:
    """Record one observation under the tier rules. Returns {action, id, status}."""
    scope = scope.strip().lower()
    if not SCOPE_RE.match(scope):
        raise ValueError(f"bad scope {scope!r}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        raise ValueError("empty text")
    if looks_secret(text):
        raise ValueError("refused: that looks like a secret (password, key, card or account number) - memory never stores those")
    tags = sorted({t.strip().lower() for t in (tags or []) if t and t.strip()})
    ev = _evidence(evidence, source)
    agent_status = "pending" if get_policy(brain) == "review" else "active"
    with Store(brain) as st:
        items = st.items(scope)
        target = None
        if match:
            target = items.get(match)
            if not target:
                raise ValueError(f"no item {match} in scope {scope}")
        elif not new:
            n = norm(text)
            target = next(
                (i for i in items.values() if i.get("status") in ("active", "pending") and norm(i.get("text", "")) == n),
                None,
            )
        if target:
            upd = {"op": "reinforce", "id": target["id"], "bump": BUMP[source], "tags": tags}
            if ev:
                upd["evidence"] = ev
            # the user's own wording wins
            if source == "user" and norm(text) != norm(target.get("text", "")):
                upd["text"] = text
            st.append(scope, upd)
            # a user or an outcome confirming a pending inference promotes it (so does a repeat
            # inference when the brain's policy is "auto")
            if target.get("status") == "pending" and (source in ("user", "outcome") or agent_status == "active"):
                st.append(scope, {"op": "status", "id": target["id"], "status": "active", "reason": f"confirmed by {source}"})
            promoted = target.get("status") == "pending" and (source in ("user", "outcome") or agent_status == "active")
            res = {"action": "reinforced", "id": target["id"], "status": "active" if promoted else target.get("status")}
        else:
            status = "active" if source in ("user", "outcome") else agent_status
            iid = _new_id(scope, text)
            item = {
                "schema": SCHEMA,
                "id": iid,
                "scope": scope,
                "kind": kind,
                "text": text,
                "tags": tags,
                "source": source,
                "status": status,
                "strength": START_STRENGTH[source],
                "evidence": [ev] if ev else [],
                "created": now(),
                "updated": now(),
                "last_used": None,
                "supersedes": supersedes,
                "reason": None,
            }
            st.append(scope, {"op": "add", "id": iid, "item": item})
            res = {"action": "added", "id": iid, "status": status}
        if supersedes:
            old = st.find(supersedes)
            if old and old[1].get("status") != "retired":
                if source == "user":
                    st.append(old[0], {"op": "status", "id": supersedes, "status": "retired", "reason": f"superseded by {res['id']}"})
                # an inference may not retire anything by itself - it goes to review with the new item
    render(brain=brain, scopes=[scope])
    return res


def approve_all(scope: str | None = None, brain: str | None = None) -> int:
    """Approve every pending item (in one scope, or all) — e.g. after switching to "auto"."""
    n = 0
    touched = set()
    with Store(brain) as st:
        for sc in ([scope] if scope else st.scopes()):
            for it in st.items(sc).values():
                if it.get("status") == "pending":
                    st.append(sc, {"op": "status", "id": it["id"], "status": "active", "reason": "approved by the user"})
                    n += 1
                    touched.add(sc)
    if touched:
        render(brain=brain, scopes=sorted(touched))
    return n


def set_status(iid: str, status: str, reason: str | None = None, edit: str | None = None, brain: str | None = None) -> dict:
    with Store(brain) as st:
        hit = st.find(iid)
        if not hit:
            raise ValueError(f"no memory item {iid}")
        scope, it = hit
        if edit:
            if looks_secret(edit):
                raise ValueError("refused: that looks like a secret")
            st.append(scope, {"op": "edit", "id": iid, "text": re.sub(r"\s+", " ", edit).strip()})
        st.append(scope, {"op": "status", "id": iid, "status": status, "reason": reason})
    render(brain=brain, scopes=[scope])
    return {"id": iid, "scope": scope, "status": status}


def _rank(it: dict, scope_weight: float, want: set[str], today: _dt.datetime) -> float:
    tags = set(it.get("tags") or [])
    tag_w = 1.0 if (want and tags & want) else (0.6 if not tags or not want else 0.35)
    last = _parse_ts(it.get("last_used")) or _parse_ts(it.get("updated")) or _parse_ts(it.get("created"))
    age = (today - last).days if last else 999
    rec = 1.0 if age <= 30 else max(0.5, 1.0 - (age - 30) / 180)
    base = float(it.get("strength", 1)) * tag_w * scope_weight * rec
    if it.get("source") == "user" or it.get("kind") == "correction":
        base += 100  # never cut before anything else
    return base


def recall_scopes(scope: str) -> list[tuple[str, float]]:
    if scope == "brain":
        return [("brain", 1.0), ("shared", 0.9)]
    if scope == "shared":
        return [("shared", 1.0)]
    return [(scope, 1.0), ("shared", 0.9), ("brain", 0.6)]


def recall(scope: str, tags: list[str] | None = None, budget: int = 1200, stamp: bool = True, brain: str | None = None) -> list[dict]:
    want = {t.strip().lower() for t in (tags or []) if t.strip()}
    today = _dt.datetime.now(_dt.timezone.utc)
    ranked = []
    with Store(brain) as st:
        for sc, w in recall_scopes(scope):
            for it in st.items(sc).values():
                if it.get("status") == "active":
                    ranked.append((_rank(it, w, want, today), sc, it))
        ranked.sort(key=lambda x: -x[0])
        chosen, used = [], 0
        cap = max(200, int(budget)) * 4
        for _, sc, it in ranked:
            line = recall_line(it)
            if used + len(line) > cap and chosen:
                break
            chosen.append(it)
            used += len(line) + 1
            if len(chosen) >= 40:
                break
        if stamp and chosen:
            by_scope: dict[str, list[str]] = {}
            for it in chosen:
                by_scope.setdefault(it.get("scope") or scope, []).append(it["id"])
            for sc, ids in by_scope.items():
                st.append(sc, {"op": "used", "ids": ids})
    return chosen


def recall_line(it: dict) -> str:
    return f"[{it['id']}] {it.get('kind', 'rule')} · {it.get('scope', '')} · {it.get('text', '')}"


# ------------------------------------------------------------------ rendering (the notes the user reads)
def _front(pairs: list[tuple[str, str]], tags: list[str]) -> str:
    out = ["---"] + [f"{k}: {v}" for k, v in pairs] + ["tags: [" + ", ".join(tags) + "]", "---", ""]
    return "\n".join(out) + "\n"


def _item_line(it: dict) -> str:
    tags = ", ".join(it.get("tags") or [])
    meta = f"{it.get('kind')} · {it.get('source')} · strength {it.get('strength', 1)}" + (f" · {tags}" if tags else "")
    return f"- {it.get('text', '')} — `{it['id']}` · {meta}"


def render(brain: str | None = None, scopes: list[str] | None = None) -> pathlib.Path:
    st = Store(brain)
    d = st.dir
    d.mkdir(parents=True, exist_ok=True)
    all_scopes = sorted(set(st.scopes()) | set(scopes or []))
    counts = {}
    pending_all = []
    for sc in all_scopes:
        items = st.items(sc)
        act = sorted((i for i in items.values() if i.get("status") == "active"), key=lambda i: -int(i.get("strength", 1)))
        pen = [i for i in items.values() if i.get("status") == "pending"]
        ret = sorted((i for i in items.values() if i.get("status") == "retired"), key=lambda i: i.get("updated") or "", reverse=True)[:20]
        pending_all += pen
        counts[sc] = (len(act), len(pen))
        label = SCOPE_LABEL.get(sc, sc)
        body = [
            f"# Memory — {label}\n",
            "What this agent remembers and uses at the start of every run. Edit a line to reword it,"
            " delete a line to retire it — `memory.py sync` picks the change up. Lines marked *agent* were"
            " inferred by the agent — remove any you disagree with.\n",
        ]
        groups = [("Preferences & rules", ("preference", "rule", "correction", "fact")), ("Lessons from outcomes", ("lesson",))]
        for title, kinds in groups:
            rows = [i for i in act if i.get("kind") in kinds]
            body.append(f"\n## {title}\n")
            body.append("\n".join(_item_line(i) for i in rows) + "\n" if rows else "_Nothing yet._\n")
        body.append(f"\n## Waiting for your review ({len(pen)})\n")
        body.append("See [[Review]].\n" if pen else "_Nothing waiting._\n")
        if ret:
            body.append("\n## Retired (latest)\n")
            body.append("\n".join(f"- ~~{i.get('text', '')}~~ — `{i['id']}`" + (f" · {i.get('reason')}" if i.get("reason") else "") for i in ret) + "\n")
        (d / f"{sc}.md").write_text(
            _front([("type", "memory"), ("scope", sc), ("title", f"Memory — {label}"), ("updated", now())], ["memory"]) + "".join(body),
            encoding="utf-8",
        )
    # Review
    rv = [
        "# Review — inferences waiting for approval\n",
        "Only used when this brain is set to review-first (`memory.py policy review`); by default an agent's inferences are"
        " saved and used at once, flagged as inferred. Approve or reject here, or in any agent chat: *approve m-…, reject m-… — wrong company*.\n",
    ]
    if not pending_all:
        rv.append("\n_Nothing waiting for review._\n")
    for it in sorted(pending_all, key=lambda i: (i.get("scope", ""), i.get("created") or "")):
        ev = (it.get("evidence") or [{}])[-1] or {}
        rv.append(f"\n### {SCOPE_LABEL.get(it.get('scope', ''), it.get('scope', ''))} — `{it['id']}`\n\n{it.get('text', '')}\n")
        if ev.get("quote") or ev.get("ref"):
            rv.append(f"\n> Evidence ({ev.get('ref', '')}): {ev.get('quote', '')}\n")
    (d / "Review.md").write_text(_front([("type", "memory"), ("title", "Review"), ("updated", now())], ["memory", "review"]) + "".join(rv), encoding="utf-8")
    # Index
    ix = ["# Memory\n", "What your Second Brain and its agents have learned — plain notes you can read, edit and delete.\n\n",
          "| Memory | Active | Waiting for review |\n|---|---|---|\n"]
    for sc in all_scopes:
        a, p = counts.get(sc, (0, 0))
        ix.append(f"| [[{sc}|{SCOPE_LABEL.get(sc, sc)}]] | {a} | {p} |\n")
    ix.append("\nItems an agent inferred are marked *agent* — remove any you disagree with. Review-first mode: `memory.py policy review` (or the Memory manager).\n")
    (d / "Memory.md").write_text(_front([("type", "memory"), ("title", "Memory"), ("updated", now())], ["memory"]) + "".join(ix), encoding="utf-8")
    return d


LINE_RE = re.compile(r"^- (?P<text>.+?) — `(?P<id>m-[0-9]{8}-[0-9a-f]{6})`")


def sync(brain: str | None = None) -> dict:
    """Pick up hand edits in the rendered notes: a reworded line edits the item; an active item
    whose line was removed is retired ('removed by hand'). Never deletes."""
    st = Store(brain)
    edited = retired = 0
    with st:
        for sc in st.scopes():
            p = st.dir / f"{sc}.md"
            if not p.is_file():
                continue
            seen = {}
            for line in p.read_text(encoding="utf-8").splitlines():
                m = LINE_RE.match(line.strip())
                if m:
                    seen[m.group("id")] = m.group("text").strip()
            for iid, it in st.items(sc).items():
                if it.get("status") != "active":
                    continue
                if iid not in seen:
                    st.append(sc, {"op": "status", "id": iid, "status": "retired", "reason": "removed by hand"})
                    retired += 1
                elif norm(seen[iid]) != norm(it.get("text", "")) and not looks_secret(seen[iid]):
                    st.append(sc, {"op": "edit", "id": iid, "text": seen[iid]})
                    edited += 1
    render(brain=brain)
    return {"edited": edited, "retired": retired}


# ------------------------------------------------------------------ importing the legacy lessons
def import_legacy(scope: str, lessons: str | None, observations: str | None, legacy: str, brain: str | None = None) -> dict:
    added = 0
    if lessons and pathlib.Path(lessons).is_file():
        txt = pathlib.Path(lessons).read_text(encoding="utf-8")
        section = ""
        for raw in txt.splitlines():
            line = raw.strip()
            if line.startswith("#"):
                section = line.lower()
                continue
            if not line.startswith("- "):
                continue
            body = line[2:].strip()
            body = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[—-]\s*", "", body)  # fundraising "- date — text"
            tag = None
            mt = re.match(r"^\[(\w+)\]\s*(.+)$", body)
            if mt:
                tag, body = mt.group(1).lower(), mt.group(2)
            if len(body) < 8 or "statistic" in section:
                continue
            promoted = legacy == "job" and "rule" in section
            try:
                observe(scope, "rule" if promoted else "lesson", "outcome" if promoted else "agent", body,
                        tags=[tag] if tag else [], evidence=f"imported|{pathlib.Path(lessons).name}", brain=brain)
                added += 1
            except ValueError:
                continue
    if observations and pathlib.Path(observations).is_file():
        for line in pathlib.Path(observations).read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = str(o.get("text") or "").strip()
            if len(text) < 8:
                continue
            try:
                observe(scope, "lesson", "agent", text, tags=[o["tag"]] if o.get("tag") else [],
                        evidence=f"imported|observations {o.get('date', '')}", brain=brain)
                added += 1
            except ValueError:
                continue
    return {"scope": scope, "imported": added}


def stats(brain: str | None = None) -> dict:
    st = Store(brain)
    out = {"dir": str(st.dir), "scopes": {}}
    for sc in st.scopes():
        by = {}
        for it in st.items(sc).values():
            by[it.get("status")] = by.get(it.get("status"), 0) + 1
        out["scopes"][sc] = by
    return out


# ------------------------------------------------------------------ CLI
def _tags(s: str | None) -> list[str]:
    return [t for t in (s or "").split(",") if t.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="memory.py", description="Second Brain memory (sbl-memory/1)")
    ap.add_argument("--brain", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recall"); r.add_argument("--scope", required=True); r.add_argument("--tags"); r.add_argument("--budget", type=int, default=1200); r.add_argument("--json", action="store_true")
    o = sub.add_parser("observe")
    o.add_argument("--scope", required=True); o.add_argument("--kind", required=True, choices=KINDS); o.add_argument("--source", required=True, choices=SOURCES)
    o.add_argument("--text", required=True); o.add_argument("--tags"); o.add_argument("--evidence"); o.add_argument("--supersedes")
    g = o.add_mutually_exclusive_group(); g.add_argument("--match"); g.add_argument("--new", action="store_true")
    li = sub.add_parser("list"); li.add_argument("--scope", required=True); li.add_argument("--status", default="active", choices=("active", "pending", "retired", "all")); li.add_argument("--json", action="store_true")
    rv = sub.add_parser("review"); rv.add_argument("--scope")
    a = sub.add_parser("approve"); a.add_argument("id"); a.add_argument("--edit")
    rj = sub.add_parser("reject"); rj.add_argument("id"); rj.add_argument("--reason", required=True)
    rt = sub.add_parser("retire"); rt.add_argument("id"); rt.add_argument("--reason", required=True)
    fg = sub.add_parser("forget"); fg.add_argument("id")
    rn = sub.add_parser("render"); rn.add_argument("--scope")
    sub.add_parser("sync")
    im = sub.add_parser("import"); im.add_argument("--scope", required=True); im.add_argument("--lessons"); im.add_argument("--observations"); im.add_argument("--legacy", default="job", choices=("job", "fund", "travel"))
    sp = sub.add_parser("stats"); sp.add_argument("--json", action="store_true")
    aa = sub.add_parser("approve-all"); aa.add_argument("--scope")
    po = sub.add_parser("policy"); po.add_argument("mode", nargs="?", choices=POLICIES)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "recall":
            items = recall(args.scope, _tags(args.tags), args.budget, brain=args.brain)
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=1))
            elif not items:
                print("(memory is empty for this scope — nothing to apply yet)")
            else:
                print(f"=== MEMORY ({args.scope}) — apply these; say which ones changed what you did ===")
                for it in items:
                    print(recall_line(it))
        elif args.cmd == "observe":
            res = observe(args.scope, args.kind, args.source, args.text, _tags(args.tags), args.evidence, args.match, args.new, args.supersedes, brain=args.brain)
            where = "used from now on" if res["status"] == "active" else "waiting for the user's review (this brain's policy is review-first)"
            print(f"{res['action']} {res['id']} — {where}")
        elif args.cmd == "list":
            items = [i for i in Store(args.brain).items(args.scope).values() if args.status == "all" or i.get("status") == args.status]
            if args.json:
                print(json.dumps(items, ensure_ascii=False, indent=1))
            else:
                for it in items:
                    print(f"{recall_line(it)}  [{it.get('status')} · strength {it.get('strength')}]")
        elif args.cmd == "review":
            st = Store(args.brain)
            n = 0
            for sc in ([args.scope] if args.scope else st.scopes()):
                for it in st.items(sc).values():
                    if it.get("status") == "pending":
                        n += 1
                        ev = (it.get("evidence") or [{}])[-1] or {}
                        print(f"{it['id']}  [{sc}] {it.get('text')}" + (f"\n    evidence: {ev.get('quote')}" if ev.get("quote") else ""))
            if not n:
                print("Nothing waiting for review.")
        elif args.cmd == "approve":
            print(json.dumps(set_status(args.id, "active", "approved by the user", args.edit, brain=args.brain)))
        elif args.cmd == "reject":
            print(json.dumps(set_status(args.id, "retired", "rejected: " + args.reason, brain=args.brain)))
        elif args.cmd == "retire":
            print(json.dumps(set_status(args.id, "retired", args.reason, brain=args.brain)))
        elif args.cmd == "forget":
            print(json.dumps(set_status(args.id, "forgotten", "forgotten on request", brain=args.brain)))
        elif args.cmd == "render":
            print(render(brain=args.brain, scopes=[args.scope] if args.scope else None))
        elif args.cmd == "sync":
            print(json.dumps(sync(brain=args.brain)))
        elif args.cmd == "import":
            print(json.dumps(import_legacy(args.scope, args.lessons, args.observations, args.legacy, brain=args.brain)))
        elif args.cmd == "approve-all":
            print(f"approved {approve_all(args.scope, brain=args.brain)} pending item(s)")
        elif args.cmd == "policy":
            if args.mode:
                set_policy(args.mode, brain=args.brain)
            mode = get_policy(brain=args.brain)
            print(f"inferences: {mode} — " + ("saved and used at once (flagged as inferred; remove any you disagree with)" if mode == "auto"
                  else "saved as pending; used only after the user approves them"))
        elif args.cmd == "stats":
            s = stats(brain=args.brain)
            print(json.dumps(s, indent=1) if args.json else "\n".join(f"{k}: {v}" for k, v in s["scopes"].items()) or "no memory yet")
    except ValueError as e:
        print(f"memory.py: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
