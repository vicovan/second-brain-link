---
name: "🐛 Mapping gap (real-export drift)"
about: A supported source has files/columns we don't handle yet
title: "[gap] <source>: <short description>"
labels: ["mapping-gap"]
---

## Source

<!-- linkedin / facebook / instagram / google -->

## What went wrong?

<!-- e.g. "Connections came through with 0 rows", "Foo.csv landed in
99-uncategorized", "a column wasn't picked up". -->

## PII-safe evidence

Paste the relevant section of `schema_map.md` (especially anything under
**⚠️ Adaptation needed**) and/or the mindmap outline. These are already
redacted/masked — **never paste raw cell values, names, emails, or message
bodies.**

```bash
python3 engine/scripts/profile_export.py "<your-export>" --out /tmp/sbl
```

```
<paste PII-safe schema_map.md / mindmap excerpt here>
```

## Export metadata (helps spot version/region drift)

- Platform + approximate export date:
- Region / language of the account (formats drift by locale):
