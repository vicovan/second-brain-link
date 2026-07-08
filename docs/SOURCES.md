# Supported sources — export & import guide

> **24 sources.** Everything runs 100% locally — zero network calls. Message, chat
> and email **text is never read** (only who + when — a per-person frequency signal);
> sensitive files (passwords, logins, payment data) are **quarantined**, never imported.
> Details: the [privacy model](https://secondbrainlink.com/privacy-model).

## At a glance

| Source | Kind | What the brain gets | Privacy class | Export |
|---|---|---|---|---|
| LinkedIn | personal | identity, connections, career, voice, mirror, search | msgs signal-only | 🟡 24 h |
| Facebook | personal | friends, voice, interests, check-ins → map, mirror, events | msgs signal-only | 🟢 |
| Instagram | personal | follows, voice, topics, places, story activity | msgs signal-only | 🟢 |
| Google Takeout | personal | contacts, calendar, places+visits+photo spots → map, searches, YouTube taste | mail/health/files excluded by design | 🟢 |
| X / Twitter | personal | tweets+note-tweets (voice), follows, lists, like counts | DMs quarantined | 🟡 24–48 h |
| WhatsApp | personal | contact graph + frequency | **text never read** | 🟢 per chat |
| GitHub | personal | repos (code voice), languages, orgs, dev network | — | 🟡 hours |
| YouTube | personal | watch/search taste graph, subscriptions, comments | — | 🟢 |
| Strava | personal | activities, training spots → map, clubs, athletes | routes reduced to start points | 🟢 |
| Reddit | personal | posts/comments (candid voice), subreddits, friends | PMs signal-only | 🟢 2–30 d |
| Spotify | personal | listening taste, playlists, algorithmic inferences | — | 🟢 up to 30 d |
| TikTok | personal | follows, searches, hashtags, comments, like counts | DM text never selected | 🟡 days |
| LinkedIn Company | company | org, employees+departments, followers, posts, page analytics | — | 🟡 per report |
| Google Workspace | company | employees+org units, calendars+attendees, drives, groups | audit logs quarantined | 🟡 admin |
| Slack | company | members, channels+membership, decisions signal | **text never read** | 🟡 admin |
| Notion | company | wiki pages (institutional voice), databases | — | 🟢 |
| Confluence | company | pages + authors (who-knows-what) | — | 🟢 space admin |
| Jira | company | projects, ownership, components, comment-author signal | ticket prose never imported | 🟢 |
| Salesforce | company | accounts, contacts, deals, campaigns, case signal | subjects never read | 🟢 |
| HubSpot | company | companies, contacts, deals, ticket signal, owners | subjects never read | 🟡 per object |
| Zendesk | company | customer orgs, requesters, ticket volume signal | subjects/bodies never read | 🟡 gated |
| Email (mbox) | company | people + relationship signal from headers | **headers only** | 🟢 |
| Microsoft 365 | company | people + signal from Purview results | **headers only** | 🟡 compliance |
| Microsoft Teams | company | people, teams/channels, message signal | **content never read** | 🟡 compliance |

## Importing — the same three ways for every source

1. **Folder drop (CLI).** Unzip into `data/<personal|company>/<your-name>/<source>/`
   (source folder names as in this doc, lowercase), then:
   ```bash
   python3 engine/scripts/build_vault.py data -o vault
   ```
2. **The Agent Skill.** Tell Claude Code / Codex: *"build my second brain from
   ~/Downloads/my-export.zip"* — it detects the source(s), profiles, builds, verifies.
3. **Second Brain Studio.** Sources side → pick the connector tile → upload the
   `.zip` → **Reseed**.

Afterwards: open `vault/` in Obsidian (start at `Home.md`), check `_COVERAGE.md`
(every file: mapped / skipped-by-design / quarantined), and run goals:
```bash
python3 engine/scripts/analyze.py vault/<your>-brain --goals jobsearch,personalization
# company brains:                                    --goals onboarding,whoknows
```

### What to expect in the vault

- **Personal brain** — layers rooted on `00-me/`: `10-people/`, `15-organizations/`,
  `20-reputation/`, `30-voice/`, `40-career/`, `50-mirror/`, `60-learning/`,
  `70-services/`, `80-search/`, `85-places/`, `90-synthesis/`.
- **Company brain** — same layer keys, **company-named folders** rooted on `00-org/`:
  `20-brand/`, `30-content/`, `40-pipeline/` (one note per deal/campaign),
  `50-market-view/`, `60-knowledge/` (meetings + events), `70-support/`,
  `80-signals/`, `85-locations/`. A mixed export builds two sibling vaults plus a
  `_correlations/` brain linking people across them.
- **`_notes/` is yours.** The engine never writes, updates or deletes anything in it
  — keep your own notes there and they survive every rebuild and refresh.
  Full field-by-field reference: [`ENTITY-MAP.md`](ENTITY-MAP.md).

### Updating with a newer archive (`--refresh`)

Exports are snapshots — when you download a fresh one, **don't rebuild over your
edits**. Drop the new archive into the same `data/...` folder and run:
```bash
python3 engine/scripts/build_vault.py data -o vault --refresh
```
Unedited engine notes are updated in place; **notes you edited are kept** (the fresh
version lands beside them as `<name>.new.md`); stale unedited notes are removed;
everything you created yourself — any folder, plus all of `_notes/` — is untouched.
The run is summarized in `_UPDATE_REPORT.md`. In Studio, **Reseed → Update** does
exactly this (choose **Rebuild from scratch** to start clean; the desktop app moves
the old brain to the Trash first). Re-run `analyze.py` after a refresh — goal
workspaces aren't part of the manifest.

---

## Personal sources

### LinkedIn
**You get:** identity + full career history, every connection (merged across sources),
recommendations & endorsements, your posts/comments (voice), job applications &
saved-job intent, LinkedIn's inferences about you (50-mirror), search history.
Messages become per-person frequency/recency signal — never the text.
**Download:** linkedin.com → Me → Settings & Privacy → Data privacy → *Get a copy of
your data* → choose the **larger data archive** (everything). A partial archive
arrives in ~10 minutes; the full one within 24 h — use the second email's link.
**Import:** folder `linkedin` — unzip the CSVs straight in.

### Facebook
**You get:** friends/followers/requests → people, posts/comments/reactions → voice,
liked pages & saved items → interests, check-ins & cities → map places, ad-interests
and off-Meta activity → the algorithmic mirror, events **with your RSVP**, notes &
page reviews → voice, marketplace listings.
**Download:** accountscenter.facebook.com → Your information and permissions →
*Download your information* → Facebook profile → **Format: JSON**, media quality low,
range All time. Ready within hours.
**Import:** folder `facebook`.

### Instagram
**You get:** followers/following, posts & comments (voice), topics & liked/saved
content → interests, last-known location + photo EXIF places → map, story
interactions (polls/quizzes/likes) as activity counts.
**Download:** same Accounts Center flow, choose the Instagram profile, **JSON**.
**Import:** folder `instagram`.

### Google Takeout
**You get:** contacts → people, calendar → events, Maps saved/reviewed/labeled places
+ **Semantic Location History visits** + **photo-spot pins from EXIF sidecars** → the
map layer, Search & Ads My-Activity → search history + mirror, YouTube
subscriptions/watch/search/likes/comments, Chrome bookmarks → interests.
Raw GPS pings (Records.json), Gmail, Fit, Drive, Keep are **excluded by design** and
reported honestly as `skipped` in `_COVERAGE.md`.
**Download:** takeout.google.com → Deselect all → select **Contacts, Calendar, Maps
(your places), Saved, Location History/Timeline, My Activity, Chrome, YouTube,
Google Photos** → Export once. Large exports arrive as several `Takeout N` zips over
hours—days; drop them all in together.
**Import:** folder `google`.

### X / Twitter
**You get:** tweets + long-form note-tweets → voice (retweets excluded), following/
followers → people, lists → interests, like counts. DMs and the imported address
book are quarantined/skipped — never read.
**Download:** x.com → Settings → Your account → *Download an archive of your data* →
re-verify → wait **24–48 h** for the email → download the ZIP.
**Import:** folder `x` — unzip so the `data/*.js` files are inside.

### WhatsApp
**You get:** who you actually talk to, how often, how recently (relationship
strength). **Message text is never read** — the parser stops at `sender:`.
**Download:** per chat: open chat → ⋮ → More → **Export chat → Without media** →
save the `.txt`. Repeat for the chats that matter.
**Import:** folder `whatsapp` — drop the exported `.txt` files in.

### GitHub
**You get:** repos with descriptions + issue/PR activity counts → code voice,
languages & starred repos → interests, followers/following → dev network,
org memberships.
**Download:** github.com → Settings → Account → *Export account data* → Start export
→ email link (hours) → **extract the tar.gz first**.
**Import:** folder `github`.

### YouTube (standalone slice)
**You get:** watch history → channel taste graph, search history, subscriptions,
playlists (incl. per-playlist video titles), your comments → voice. JSON and HTML
history formats both parse.
**Download:** takeout.google.com → Deselect all → **YouTube and YouTube Music** only
→ in options keep history/subscriptions/playlists/comments, untick videos.
**Import:** folder `youtube`. (Inside a full Takeout, the `google` source handles it.)

### Strava
**You get:** activities → events + sport interests, each activity's **start point
only** → training-spot map pins (never full routes), clubs, follower/following
athletes, profile city (geocoded).
**Download:** strava.com → Settings → My Account → *Download or Delete Your Account*
→ **Download Request** → email ZIP.
**Import:** folder `strava`.

### Reddit
**You get:** posts & comments (often your most candid voice), subscribed subreddits
& multireddits → interests, friends → people, saved posts, search history. Private
messages become sender + date signal — subject/body never selected.
**Download:** reddit.com/settings/data-request → full GDPR export → email link
(typically <48 h, up to 30 days).
**Import:** folder `reddit`.

### Spotify
**You get:** listening history → artist taste graph, followed artists, playlists +
their tracks' artists, Spotify's **Inferences** about you → 50-mirror, Marquee ad
segments, search queries. Userdata/payment files are quarantined.
**Download:** spotify.com/account → Security & privacy → *Download your data* →
tick **Extended streaming history** (the default alone is thin) → email links
(account ~5 days, extended up to 30). Drop both zips' contents together.
**Import:** folder `spotify`.

### TikTok
**You get:** following → people, searches, favorite hashtags → interests, your
comments → voice, like/favorite counts. DM text sits in the same file but no rule
ever selects it.
**Download:** app → Profile → ☰ → Settings → Account → *Download your data* →
**Format: JSON (machine-readable)** → ready in days (download within 4 days).
**Import:** folder `tiktok`.

---

## Company sources (admin roles usually required)

### LinkedIn Company Page
**You get:** the org profile (HQ geocoded), employees **with departments** → org
structure, followers, page posts → company voice, follower/visitor analytics →
the company's algorithmic mirror.
**Download:** Page admin → Analytics / Settings → export the employee list,
followers, posts and analytics reports (per-report CSVs — no single ZIP).
**Import:** folder `linkedin_company`.

### Google Workspace
**You get:** users **with Org Units** → employees + department structure, shared
calendars **with attendees** → meetings, shared drives → projects, groups → teams.
Login/admin audit logs are quarantined.
**Download:** admin.google.com → Directory → Users → **Download users** (CSV);
calendars/drives via org Takeout or Vault.
**Import:** folder `google_workspace`.

### Slack
**You get:** members → people, channels **with topics + membership** (`channel/…`
tags feed the who-knows-what map), per-person message frequency. **Message text is
never read.**
**Download:** workspace ADMIN → `<workspace>.slack.com/services/export` → Export
(public channels; all paid tiers). Private channels/DMs need an Enterprise-Grid
compliance export.
**Import:** folder `slack`.

### Notion
**You get:** every wiki page → institutional voice notes with **breadcrumb context**
("Projects / Roadmap — …") and intra-wiki references, database rows → interests.
**Download:** workspace owner → Settings → **Export all workspace content** →
**Markdown & CSV**, include subpages → email link (large spaces take hours).
**Import:** folder `notion`.

### Confluence
**You get:** pages → voice **with authors** (who wrote what — expertise signal),
space → org, body excerpts.
**Download:** space admin → Space settings → *Export space* → **XML** (full
fidelity; HTML also parses) → ZIP.
**Import:** folder `confluence`.

### Jira
**You get:** projects → orgs, assignees/reporters → people with `project/…`
ownership tags, components & labels → the technology map, comment **authors** →
who-answers-what signal. Ticket prose is never imported.
**Download:** Issue navigator → filter the project(s) → Export → **CSV (all
fields)**; repeat per 1000-row page if large.
**Import:** folder `jira`.

### Salesforce
**You get:** accounts → customer orgs (geocoded), contacts/leads → people joined to
accounts, opportunities → **deal timeline**, campaigns + members, tasks & cases →
per-contact interaction signal, users → your own team. Subjects never read.
**Download:** Setup → *Data Export Service* → Export Now (or schedule) → email →
**link expires in 48 h** → CSV ZIP(s).
**Import:** folder `salesforce`.

### HubSpot
**You get:** companies (geocoded), contacts, deals → timeline, tickets → per-contact
support signal, deal/ticket owners → your own team.
**Download:** per object: Contacts / Companies / Deals / Tickets list → Export →
CSV, all properties. Keep the `hubspot-…` filenames.
**Import:** folder `hubspot`.

### Zendesk
**You get:** customer orgs, requesters → people at their org, ticket volume +
per-requester signal. Subjects/descriptions never read.
**Download:** Admin Center → Account → *Requests to export data* (Zendesk support
must enable it once) → JSON/CSV → email.
**Import:** folder `zendesk`.

### Email (mbox)
**You get:** every correspondent's display name → people + relationship
strength/recency. **Headers only — subjects and bodies are never accessed.**
**Download:** Gmail: Takeout → Mail → MBOX (or Google Vault org-wide). Outlook PST:
convert first — `readpst -o out/ archive.pst` → drop the `.mbox`.
**Import:** folder `email`. *(A personal Takeout that happens to contain Mail is
deliberately NOT treated as a company mail import — place the mbox here on purpose.)*

### Microsoft 365
**You get:** same as Email, from Purview eDiscovery results (`.eml` + results CSV).
**Download:** Purview compliance portal → eDiscovery → Content search → Export
results (needs the eDiscovery Manager role).
**Import:** folder `microsoft365`.

### Microsoft Teams
**You get:** senders → people, teams & channels → orgs with membership tags,
message frequency signal. **Content columns are never read.**
**Download:** Purview eDiscovery message report (CSV/JSON) for the teams in scope.
**Import:** folder `teams`.

---

## Not supported by design

Personal email inboxes (as a *personal* source), health & wearables, message/chat
**content**, financial data, and raw file/media dumps. A brain is *who you are and
what you care about* — not your inbox or your heart-rate log. See the source
catalog in the docs repo for the reasoning, and `_COVERAGE.md` in every build for
the honest per-file account (mapped / skipped-by-design / quarantined).
