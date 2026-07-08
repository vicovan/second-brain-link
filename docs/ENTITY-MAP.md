# Entity Map — every brain entity, every source, every field

> The complete reference for what a Second Brain Link vault contains: each note
> type's frontmatter fields, which of the 24 sources fills them, how content
> routes into folders per subject (personal vs company), and how incremental
> updates (`--refresh`) treat every file. Companion: [`SOURCES.md`](SOURCES.md)
> (export/download + import steps per source). Kept in sync with
> `engine/scripts/sources/common.py` (the Collector — the single canonical model)
> and `engine/mappings/brain/layout.json` (the folder layout variants).

Sources legend — personal: `linkedin, facebook, instagram, google, x, whatsapp,
github, youtube, strava, reddit, spotify, tiktok` · company: `linkedin_company,
google_workspace, slack, notion, confluence, jira, salesforce, hubspot, zendesk,
email, microsoft365, teams`.

---

## 1. Vault layout per subject (layer key → folder)

| Key | Personal | Company | Holds |
|---|---|---|---|
| root | `00-me/` | `00-org/` | identity note (+ company: `data-handling.md`) |
| people | `10-people/` | `10-people/` | one note per person, merged across sources |
| orgs | `15-organizations/` | `15-organizations/` | companies/departments/teams/channels (`_mentions/` = thin one-offs) |
| reputation | `20-reputation/` | `20-brand/` | recommendations/endorsements · reviews/brand |
| voice | `30-voice/` | `30-content/` | posts (one note each), comments/reactions/interests/saved aggregates |
| career | `40-career/` | `40-pipeline/` | applications/prefs/saved-jobs · **one note per deal/campaign** |
| mirror | `50-mirror/` | `50-market-view/` | algorithmic inferences + ad/audience segments |
| learning | `60-learning/` | `60-knowledge/` | events.md, meetings.md (company), coaching |
| services | `70-services/` | `70-support/` | service/ticket counts |
| search | `80-search/` | `80-signals/` | search-log.md (source+date per query) |
| places | `85-places/` | `85-locations/` | one note per place (lat/lng → map) |
| synthesis | `90-synthesis/` | `90-synthesis/` | derived brains (+ analyze's `95-goals/`) |
| notes | `_notes/` | `_notes/` | **YOURS — the engine never writes/updates/deletes here** |
| — | `99-uncategorized/`, `_quarantine/` | same | harvested leftovers · never-imported sensitive files |

Layout source of truth: `layout.json → variants` (builder resolves via
`VaultWriter.L(key)`; no folder name is hardcoded — a test guards this).

## 2. Entities and their fields

### person (`10-people/<Name>.md`) — merged by `nk(name)` across all sources
| Field | Meaning | Filled by |
|---|---|---|
| title/aliases | display name (filename == title) | all people-emitting sources |
| company · role | employer/title — **first non-empty wins; conflicts preserved** | linkedin, linkedin_company, google_workspace, slack, salesforce, hubspot, zendesk, google(contacts) |
| alt_company · alt_role (+ `## Also reported` body) | conflicting claims from later sources, with the source named | any two disagreeing sources |
| dept | department/org-unit, as `"[[Dept]]"` link (+ `dept/<slug>` tag) | linkedin_company (Department), google_workspace (Org Unit) |
| connected_on | when the connection was made (no longer overloaded onto `created`) | linkedin |
| created | first-seen/build date | engine |
| relationship | company brains only: employee/customer/vendor/correspondent/contact | derived from sources+tags |
| status · strength · first_contact · last_contact | personal brains: warm/dormant/cold + 1–5 message-frequency strength (signal only, never content) | whatsapp, slack, linkedin, email, microsoft365, teams, reddit(PMs), salesforce/hubspot/zendesk (interaction signal) |
| url | public profile link (identity key, not PII) | linkedin, x, github, facebook, instagram |
| handles | usernames across networks | x, github, tiktok, reddit, instagram |
| location + lat/lng | city (offline-geocoded) | github, strava, salesforce/hubspot (via account city) |
| email · phone · extra | **`--full` owner mode only** — default builds never store them | adapters pass through; Collector decides |
| tags | `source/<name>` + semantic (`person/friend`, `person/customer`, `channel/<slug>`…) | all |

### organization (`15-organizations/<Name>.md`)
| Field | Filled by |
|---|---|
| category (self/customer/department/channel/group/project/club/member/…) | emitting adapter |
| industry · size · domain | salesforce, hubspot, linkedin_company |
| about (self-description; e.g. Slack topic+purpose) | slack, notion(db), confluence(space) |
| location + lat/lng (HQ, geocoded) | linkedin_company, salesforce, hubspot |
| url · known_contacts · alt_industry/alt_location · tags | various |
| body: "People here" reverse index | derived from people records |

### post (`<voice>/posts/<date>-<hash8>.md`) — one note per post, content-addressed filename
kind: post/tweet/note-tweet/share/repost/media/page/note/review/listing/repo ·
fields: text (strip_pii'd), created, source, url, tags. Filled by: linkedin,
facebook, instagram, x, github(repos), reddit, tiktok(comments→comments.md),
notion/confluence (pages, company).

### deal (`40-pipeline/<Name>.md`, company only) — one note per deal/campaign
kind: deal/campaign · fields: date, value, sources. Filled by: salesforce
(Opportunities+Campaigns), hubspot (Deals). Personal builds keep these in events.md.

### event / meeting (`<learning>/events.md` + company `meetings.md`)
Canonical record via `add_event`: name, date, kind (event/meeting/deal/campaign/
activity), location, description, attendees (wikilinks, cap 15), RSVP tags
(`event/going|interested`), url, value. Filled by: google(ics), google_workspace
(calendars→meetings), linkedin(events), facebook(invitations+RSVPs), strava
(activities), salesforce/hubspot (deals→pipeline).

### place (`<places>/<Name>.md`) — one note per place, numeric suffix on collisions
fields: address, lat, lng, `location: "lat,lng"` (Obsidian Map View), url, kind
(saved/reviewed/labeled/check-in/visited/photo/activity), lists, note (your
review), created, sources. Filled by: google (Maps saved/reviews/labeled,
Semantic Location History visits, Photos EXIF spots), facebook (check-ins),
instagram (locations/media EXIF), strava (GPX start points).

### aggregates (all carry frontmatter: type/tags/sources/totals)
- `interests.md` — grouped BY SOURCE, counts, cap 500 (+ "and N more"); interest_meta keeps sources+first date. Filled by: every source.
- `reactions.md` — per-kind counts with source attribution (likes, story polls, favorites…).
- `comments.md` — dated, source-tagged lines (owner's words, strip_pii'd).
- `search-log.md` — per-query `— source · date`, cap 500. Filled by: linkedin, google (My Activity + YouTube), youtube, reddit, spotify, tiktok.
- `saved.md`, `preferences.md`, `saved-jobs.md`, `reusable-answers.md`, `applications.md` (career), recommendations/endorsements (reputation).
- mirror: `inferences.md` + `ad-profile.md` (caps 500) — linkedin, facebook, spotify, instagram, google(Ads), linkedin_company (page analytics → company market view).

### identity (`00-me/identity.md` / `00-org/organization.md`)
name, headline, location (+lat/lng), industry, about, positions (title/company/
start/end **+ description**), skills, education, certifications, languages,
handles. Mappings can set name/headline/location/industry/about/skills.

### message signal (never a note — woven into people)
`{n, first, last, by-source}` per person; idempotent on (source, party, ts) so
re-imported archives can't inflate strength. **Bodies are never read** — this is
the entire representation of every chat/inbox in the vault.

## 3. Generated artifacts (brain root)
`Home.md` (MOC, subject-aware layer legend) · `CLAUDE.md`/`AGENTS.md` (agent
guide) · `_STRUCTURE.md` (per-subject role map) · `_SUMMARY.md` · `_COVERAGE.md`
(mapped/skipped-by-design/quarantined/uncategorized per file) · `_BUILD_REPORT.md`
· `_GENERATED.json` (**the manifest: every engine-generated file + sha256**) ·
after analyze: `Dashboard.md`, `_DATA_POINTS.md`, `_GRAPH.md`, `95-goals/`,
`copilot-prompts/` · after refresh: `_UPDATE_REPORT.md`.

## 4. Update semantics (`--refresh` vs `--rebuild`)
File classes and what an update does:
| Class | How identified | On `--refresh` |
|---|---|---|
| generated, unedited | in old manifest, on-disk sha matches | overwritten with the fresh version |
| generated, USER-EDITED | in old manifest, sha differs | **kept**; fresh copy beside as `<name>.new.md`; listed in `_UPDATE_REPORT.md` |
| generated, stale, unedited | in old manifest, absent from new build | **deleted** (regenerable) |
| generated, stale, edited | ditto but sha differs | kept + reported |
| user-created (any folder) | never in a manifest | untouched, always |
| `_notes/**` | the user space | untouched, always (only the README stub is engine-owned) |
| `_correlations/` | fully derived | regenerated wholesale |
Filenames are stable across rebuilds (content-addressed posts, deterministic
people/place suffixes) so the same datum maps to the same file. Studio reseed
offers **Update** (default, `--refresh`) and **Rebuild from scratch** (desktop:
old brain → OS Trash). Analyze outputs are never in the manifest — re-run
`analyze.py` after a refresh.

## 5. Extension contract (keep this map complete)
A new source/field must register at every hop, or it silently disappears:
1. **Collector verb** (`sources/common.py`) — add/extend the canonical record.
2. **Adapter/mapping** — pass the field (mappings support `extra: {…}` capture).
3. **Renderer** (`build_vault.py`) — frontmatter + body, via `self.L(key)` folders.
4. **analyze read-back** (`read_people` / `scan_layer` / `_read_places`).
5. **Studio** — `TYPE_LABEL`/colors if a new note type.
6. **This document + SOURCES.md** — the row for it.
Tests must cover: extraction, render, privacy sweep, refresh stability.
