#!/usr/bin/env python3
"""
mapping.py — declarative SOURCE adapters as JSON (no Python per source).

A source mapping is a JSON file (engine/mappings/sources/<name>.json) that
declares what a hand-written adapter used to do imperatively:

  detect   — which files belong to this source (path/key signatures)
  records  — a list of rules, each: match files → locate record arrays →
             extract fields with a tiny safe selector language → emit via col.add_*

The interpreter turns a mapping into an object exposing the SAME contract the
Python adapters use (NAME, SUBJECT, detect(file_index), extract(root, file_index,
all_paths, col)), so sources/__init__.py treats it exactly like a `.py` module.

PRIVACY: mappings can ONLY push through col.add_* — they cannot bypass the
Collector's email/phone stripping, body-never-read, or quarantine. Mappings are
DATA, never code: no eval, no imports, just selectors.

Selector mini-language (string, or list-of-strings = first non-empty wins):
  "a.b"               dotted dict keys
  "a[]"               iterate a list → yields each item (flattened)
  "a[N]"              pluck list element N
  "a[].b"             pluck b from each item of list a
  "m.*.value"         any dict key under m, then .value (Instagram string_map_data)
  "a[k=v].b"          iterate a, keep items whose key `k` CONTAINS `v` (case-insensitive),
                      then .b — extracts a value by its sibling label (Facebook's
                      {label,value} shape: `label_values[label=Message].value`)
  {"const": x}        literal value
Special field forms in a rule's "fields":
  "name": "string_list_data[].value"     → one add_* per yielded value (fan-out)
  "name": ["title","caption"]            → first selector that resolves non-empty

A rule's "emit" picks the canonical Collector verb:
  person · org · post · comment · interest · reaction · search · event ·
  message_signal · place · identity · mirror · ad_segment
  (mirror/ad_segment feed the 50-mirror layer — how the platform models the owner.)

A rule may also declare "tags": [...] — semantic tags (e.g. ["person/friend"]) put
on every entity note the rule emits. They join the renderer's automatic
`source/<name>` + type tags, so all data points are colorable/filterable in the
Obsidian graph, Bases, and Dataview. Use `/`-nested tags for a clean taxonomy.
"""
import json
from pathlib import Path

from sources.common import (read_json, read_csv, walk_json_arrays, iso_date, nk,
                            norm_file, fix_mojibake)

MAPPINGS_DIR = Path(__file__).resolve().parent.parent / "mappings"


# ---------------------------------------------------------------------------
# selector resolver — returns a LIST of resolved scalar values (possibly empty)
# ---------------------------------------------------------------------------

def _resolve(obj, selector):
    """Resolve a single string selector against obj → list of scalar values."""
    if obj is None:
        return []
    cur = [obj]
    for tok in selector.split("."):
        nxt = []
        # token forms: key[N] (pluck element N) · key[] (iterate) · key (dict key) ·
        # key[field=val] (iterate, keeping only list items whose `field` contains `val`
        # — case-insensitive). The predicate unlocks Facebook's {label,value} shape:
        # `label_values[label=Message].value` extracts the value sitting next to a
        # specific label, instead of every value in the record.
        idx = None
        pred = None
        listy = tok.endswith("[]")
        if not listy and tok.endswith("]") and "[" in tok:
            base, _, rest = tok.partition("[")
            inner = rest[:-1]
            if inner.lstrip("-").isdigit():
                idx, tok = int(inner), base
            elif "=" in inner:
                f, _, val = inner.partition("=")
                pred, tok, listy = (f.strip(), val.strip()), base, True
            # else: an unrecognized bracket — leave tok as-is (it simply won't match)
        key = tok[:-2] if (listy and not pred) else tok
        if idx is not None:
            for o in cur:
                val = o.get(key) if isinstance(o, dict) else (o if key == "" else None)
                if isinstance(val, list) and -len(val) <= idx < len(val):
                    nxt.append(val[idx])
            cur = nxt
            continue
        for o in cur:
            if key == "*":
                if isinstance(o, dict):
                    nxt.extend(o.values())
                continue
            if key == "":
                val = o
            elif isinstance(o, dict):
                val = o.get(key)
            else:
                val = None
            if val is None:
                continue
            if listy:
                if isinstance(val, list):
                    if pred:
                        f, want = pred
                        nxt.extend(it for it in val if isinstance(it, dict)
                                   and want.lower() in str(it.get(f, "")).lower())
                    else:
                        nxt.extend(val)
                else:
                    nxt.append(val)
            else:
                nxt.append(val)
        cur = nxt
    # keep scalars; stringify nothing (callers decide). Drop dicts/lists at the leaf
    # unless the selector intentionally ended on a container (then stringify scalars).
    out = []
    for v in cur:
        if isinstance(v, (str, int, float)) and str(v).strip() != "":
            out.append(v)
    return out


def resolve_field(obj, spec):
    """Resolve a field spec (str | list[str] | {const}) → list of values.
    A list spec is 'first selector that yields anything wins'."""
    if isinstance(spec, dict):
        if "const" in spec:
            return [spec["const"]]
        if "first_of" in spec:
            return resolve_field(obj, spec["first_of"])
        return []
    if isinstance(spec, list):
        for s in spec:
            got = resolve_field(obj, s)
            if got:
                return got
        return []
    return _resolve(obj, str(spec))


def _first(vals):
    """Return the first value of a resolved list, or "" when empty (safe for str())."""
    return vals[0] if vals else ""


# ---------------------------------------------------------------------------
# record location
# ---------------------------------------------------------------------------

def _auto_array(data):
    """Best-effort: a top-level list, else the first list-of-dicts under any key,
    else the single dict wrapped as one record."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return [data]
    return []


def _locate(data, mode, field_keys):
    """Find the list of record dicts in parsed JSON `data` per the rule's `locate` mode.
    Modes: walk (deep-scan arrays whose dicts carry field_keys), geojson_features
    (the top-level "features" list), dict (the doc itself as one record), or the
    default auto_array (top-level list / first list-of-dicts / single dict)."""
    if mode == "walk":
        out = []
        for arr in walk_json_arrays(data, field_keys or ("value", "name", "title")):
            out.extend(arr)
        return out
    if mode == "geojson_features":
        feats = data.get("features") if isinstance(data, dict) else None
        return feats if isinstance(feats, list) else []
    if mode == "dict":
        return [data] if isinstance(data, dict) else []
    return _auto_array(data)            # default: auto_array


# ---------------------------------------------------------------------------
# emit — call the matching col.add_* (privacy enforced inside Collector)
# ---------------------------------------------------------------------------

def _emit(col, source, kind, fields, rec, tags=None):
    """fields: {logical_name: spec}. We fan out on the PRIMARY field's list so a
    record with N handles emits N people, etc. `tags` are rule-declared semantic
    tags (e.g. ["person/friend"]) attached to every entity note this rule emits —
    they join the renderer's automatic `source/<name>` + type tags so all data
    points are filterable in the Obsidian graph/Bases/Dataview."""
    tags = list(tags or [])
    # `extra` is a rule-level dict {"Label": "selector"} — captured per record and
    # passed through to the Collector (stored only in --full, like adapters). This
    # closes the old gap where mapping sources dropped every unmodeled column.
    extra_spec = fields.get("extra") if isinstance(fields.get("extra"), dict) else None
    plain_fields = {k: v for k, v in fields.items() if k != "extra"}
    resolved = {k: resolve_field(rec, v) for k, v in plain_fields.items()}

    def g(k, i=0):
        """Pick field `k`'s i-th resolved value, falling back to its first (so a
        scalar field like company/role aligns to every fanned-out primary value)."""
        vals = resolved.get(k) or []
        return vals[i] if i < len(vals) else (vals[0] if vals else "")

    def extra_for(i=0):
        if not extra_spec:
            return None
        out = {}
        for label, sel in extra_spec.items():
            vals = resolve_field(rec, sel) or []
            v = vals[i] if i < len(vals) else (vals[0] if vals else "")
            if v:
                out[label] = str(v)
        return out or None

    if kind == "person":
        names = resolved.get("name") or resolved.get("handle") or []
        for i, _ in enumerate(names):
            nm = g("name", i) or g("handle", i)
            col.add_person(source, str(nm), company=str(g("company", i)),
                           role=str(g("role", i)), date=str(g("date", i)),
                           handle=str(g("handle", i)), url=str(g("url", i)),
                           email=str(g("email", i)), phone=str(g("phone", i)),
                           connected_on=str(g("connected_on", i)),
                           dept=str(g("dept", i)), location=str(g("location", i)),
                           extra=extra_for(i), tags=tags)
        return len(names)
    if kind == "org":
        for i, _ in enumerate(resolved.get("name") or []):
            col.add_org(source, str(g("name", i)), category=str(g("category", i) or "referenced"),
                        url=str(g("url", i)), location=str(g("location", i)),
                        industry=str(g("industry", i)), size=str(g("size", i)),
                        domain=str(g("domain", i)), about=str(g("about", i)),
                        extra=extra_for(i), tags=tags)
        return len(resolved.get("name") or [])
    if kind == "post":
        n = 0
        for i, _ in enumerate(resolved.get("text") or []):
            col.add_post(source, str(g("text", i)), date=str(g("date", i)),
                         kind=str(g("kind", i) or "post"), url=str(g("url", i)),
                         tags=tags); n += 1
        return n
    if kind == "comment":
        n = 0
        for i, _ in enumerate(resolved.get("text") or []):
            col.add_comment(source, str(g("text", i)), date=str(g("date", i))); n += 1
        return n
    if kind == "interest":
        vals = resolved.get("tag") or resolved.get("name") or []
        for i, t in enumerate(vals):
            col.add_interest(source, str(t), date=str(g("date", i)))
        return len(vals)
    if kind == "mirror":
        vals = resolved.get("text") or resolved.get("tag") or resolved.get("name") or []
        for v in vals:
            col.add_mirror_inference(source, str(v))
        return len(vals)
    if kind == "ad_segment":
        vals = resolved.get("text") or resolved.get("tag") or resolved.get("name") or []
        for v in vals:
            col.add_ad_segment(source, str(v))
        return len(vals)
    if kind == "reaction":
        # `count_of` lets a rule tally one reaction per matched record without
        # storing the records themselves (TikTok likes/favorites: the LINKS are
        # noise, the COUNT is the signal). The selector's resolved list length
        # is the tally; `kind` (usually a const) names the reaction.
        over = resolved.get("count_of") or []
        if over:
            k = str((resolved.get("kind") or ["like"])[0])
            for _ in over:
                col.add_reaction(source, k)
            return len(over)
        for k in (resolved.get("kind") or ["like"]):
            col.add_reaction(source, str(k))
        return len(resolved.get("kind") or ["like"])
    if kind == "search":
        n = 0
        qs = resolved.get("query") or resolved.get("text") or []
        for i, q in enumerate(qs):
            col.add_search(source, str(q), date=str(g("date", i))); n += 1
        return n
    if kind == "event":
        for i, _ in enumerate(resolved.get("name") or []):
            col.add_event(source, str(g("name", i)), date=str(g("date", i)),
                          kind=str(g("kind", i) or "event"),
                          location=str(g("location", i)), tags=tags)
        return len(resolved.get("name") or [])
    if kind == "message_signal":
        names = resolved.get("name") or []
        for i, _ in enumerate(names):
            d = g("date", i)
            ds = iso_date(int(d) // 1000) if str(d).isdigit() and len(str(d)) >= 12 else str(d)
            col.add_message_signal(source, str(g("name", i)), ds)
        return len(names)
    if kind == "place":
        names = resolved.get("name") or []
        for i, _ in enumerate(names):
            col.add_place(source, name=str(g("name", i)), address=str(g("address", i)),
                          lat=str(g("lat", i)), lng=str(g("lng", i)),
                          url=str(g("url", i)), kind=str(g("kind", i) or "place"),
                          note=str(g("note", i)), date=str(g("date", i)), tags=tags)
        return len(names)
    if kind == "identity":
        col.set_identity(source, name=str(_first(resolved.get("name") or [])),
                         headline=str(_first(resolved.get("headline") or [])),
                         location=str(_first(resolved.get("location") or [])),
                         industry=str(_first(resolved.get("industry") or [])),
                         about=str(_first(resolved.get("about") or [])))
        # list-valued identity enrichment (e.g. skills from a JSON export)
        skills = [str(s) for s in (resolved.get("skills") or []) if str(s).strip()]
        if skills:
            cur = col.identity.setdefault("skills", [])
            for s in skills:
                if s not in cur:
                    cur.append(s)
        return 1
    return 0


# ---------------------------------------------------------------------------
# match files to a rule
# ---------------------------------------------------------------------------

def _path_match(path, match):
    """True iff `path` satisfies every clause present in a rule's `match` block
    (path_contains / name_prefix / name_contains / suffix). All comparisons are
    case-insensitive. Returns False for an empty match block (a rule must declare
    at least one matcher to claim any file)."""
    s = str(path).lower()
    name = path.name.lower()
    if "path_contains" in match and not any(x.lower() in s for x in match["path_contains"]):
        return False
    if "name_prefix" in match and not name.startswith(tuple(x.lower() for x in
                                  ([match["name_prefix"]] if isinstance(match["name_prefix"], str)
                                   else match["name_prefix"]))):
        return False
    if "name_contains" in match and not any(x.lower() in name for x in match["name_contains"]):
        return False
    if "suffix" in match and path.suffix.lower() not in (
            [match["suffix"]] if isinstance(match["suffix"], str) else match["suffix"]):
        return False
    return "path_contains" in match or "name_prefix" in match or \
           "name_contains" in match or "suffix" in match


# ---------------------------------------------------------------------------
# the mapping object (adapter-contract compatible)
# ---------------------------------------------------------------------------

class JsonMapping:
    """A loaded JSON source mapping presented as an adapter (NAME/SUBJECT/detect/
    extract), so sources/__init__.py treats it exactly like a Python adapter
    module. All extraction goes through col.add_* — privacy stays enforced in the
    Collector; mappings are DATA, never code (no eval, no imports)."""

    def __init__(self, spec, src_path=None):
        """Wrap a parsed mapping `spec` dict (optionally remembering its source
        file `src_path`); expose name/subject and the quarantine key set."""
        self.spec = spec
        self.NAME = spec["name"]
        self.SUBJECT = spec.get("subject", "person")
        self.QUARANTINE = set(spec.get("quarantine", []))
        self._src = src_path

    def detect(self, file_index):
        """True iff this source's `detect` signature matches the engine's
        file_index (any of: a path substring, a normalized-key prefix, or an
        exact normalized key)."""
        d = self.spec.get("detect", {})
        keys = set(file_index)
        paths = [str(p).lower() for ps in file_index.values() for p in ps]
        blob = " ".join(paths) + " " + " ".join(keys)
        if "path_contains" in d and any(x.lower() in blob for x in d["path_contains"]):
            return True
        if "any_key_prefix" in d and any(k.startswith(tuple(d["any_key_prefix"])) for k in keys):
            return True
        if "any_key" in d and any(k in keys for k in d["any_key"]):
            return True
        return False

    def extract(self, root, file_index, all_paths, col):
        """Run every record rule over all matching files, emitting via col.add_*.
        Returns the set of consumed file keys as norm_file(p.name) — these MUST
        match the engine's file_index keys (using nk here was a real coverage bug),
        or files extracted from still show as unclaimed."""
        consumed = set()
        for rule in self.spec.get("records", []):
            match = rule.get("match", {})
            mode = rule.get("locate", "auto_array")
            emit = rule["emit"]
            fields = rule.get("fields", {})
            rule_tags = rule.get("tags", [])
            # top-level key of each selector — the hint `walk` mode uses to find arrays
            field_keys = tuple(
                k for spec in fields.values()
                for k in ([spec] if isinstance(spec, str) else
                          spec if isinstance(spec, list) else [])
                if isinstance(k, str) for k in [k.split(".")[0].rstrip("[]")])
            for p in all_paths:
                if p.suffix.lower() not in (".json", ".csv"):
                    continue
                if not _path_match(p, match):
                    continue
                try:
                    if p.suffix.lower() == ".csv":
                        records = read_csv(p)            # list of row-dicts
                    else:
                        records = _locate(read_json(p), mode, field_keys)
                    n = 0
                    for rec in records:
                        n += _emit(col, self.NAME, emit, fields, rec, rule_tags)
                    if n:
                        col.note(f"[{self.NAME}] {emit}: {n} from {p.name}")
                    consumed.add(norm_file(p.name))   # match the engine's file_index keys
                except Exception as e:
                    col.note(f"[{self.NAME}] skipped {p.name}: {e}")
        return consumed


def load_mappings(extra_dirs=None):
    """Load all source mappings from engine/mappings/sources/ + any extra dirs
    (later dirs win on name clash). Returns {name: JsonMapping}."""
    out = {}
    dirs = [MAPPINGS_DIR / "sources"]
    for d in (extra_dirs or []):
        dd = Path(d)
        dirs += [dd, dd / "sources"]
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                spec = json.loads(f.read_text(encoding="utf-8"))
                if "name" in spec and "records" in spec:
                    out[spec["name"]] = JsonMapping(spec, f)
            except Exception:
                continue
    return out


def load_brain_layout(extra_dirs=None):
    """Load the brain layout JSON (folders/buckets). Override dirs win."""
    paths = [MAPPINGS_DIR / "brain" / "layout.json"]
    for d in (extra_dirs or []):
        paths += [Path(d) / "brain" / "layout.json", Path(d) / "layout.json"]
    layout = None
    for p in paths:
        if p.is_file():
            try:
                layout = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return layout
