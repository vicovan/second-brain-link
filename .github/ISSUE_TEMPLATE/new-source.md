---
name: "🧩 New data source"
about: Propose (or claim) support for a new platform export
title: "[source] <platform name>"
labels: ["new-source"]
---

## Which platform?

<!-- e.g. X/Twitter, GitHub, Strava, Spotify, Reddit … -->

## Export format

- [ ] CSV
- [ ] JSON
- [ ] ICS / vCard
- [ ] HTML (note: HTML is not parsed — request JSON if the platform offers it)
- [ ] Other: 

## How does a user get the export?

<!-- The settings path, e.g. Settings → Your data → Download. -->

## What's in it? (PII-safe!)

Run the profiler and paste the catalog — it's already redacted/masked, so it's
safe to share:

```bash
python3 engine/scripts/profile_export.py "<your-export>" --out /tmp/sbl
```

Paste the relevant part of `/tmp/sbl/schema_map.md` and/or the
`*_mindmap.md` outline below. **Do not paste raw rows / cell values.**

```
<paste PII-safe schema_map.md / mindmap excerpt here>
```

## Which canonical entities does it map to?

<!-- Person / Organization / Skill / Job / Activity / Interest / Identity … -->

## Are you planning to contribute the adapter?

- [ ] Yes — I'll add a JSON mapping (preferred) or run
      `python3 engine/scripts/new_source.py <name>` and open a PR
- [ ] No — just requesting
