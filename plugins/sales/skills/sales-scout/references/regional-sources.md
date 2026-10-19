# Regional source packs — what actually carries each market

Global aggregators see US and EU tech and little else. Each market needs its own pack, and the
coverage gate wants **three sources per market** before a market may be called thin. Start from
the pack, then add what the seller knows (`icp.md` notes).

These are kinds of sources with examples of where to look; verify each page before relying on
it, and record what worked in memory (`observe --source outcome --tags sources,<market>`).

| Market | Hiring | News and funding | Directories and events | Registries |
|---|---|---|---|---|
| DACH | LinkedIn public search; company boards (Personio, SmartRecruiters are common) | regional startup press; funding round-ups | IHK member search; trade-fair exhibitor lists; accelerator portfolios | Handelsregister announcements |
| UK | LinkedIn public search; company boards | UK startup and business press; funding round-ups | accelerator portfolios; sector association member lists; event exhibitor lists | Companies House (open API: incorporations, officers) |
| Nordics | LinkedIn public search; company boards (Teamtailor is common) | Nordic startup press | accelerator portfolios; event exhibitor lists | national business registers (open data in several countries) |
| US | LinkedIn public search; Greenhouse / Lever / Ashby boards | startup and business press; funding round-ups | YC company directory; accelerator portfolios; conference exhibitor lists | state business registries (varies) |
| EU (other) | LinkedIn public search; company boards | national startup press | accelerator portfolios; trade-fair exhibitor lists | national registers; the EU business-register portal |
| UAE / GCC | LinkedIn public search; the companies' own boards; regional job boards | regional business and startup press; free-zone news pages | free-zone company directories; chamber of commerce directories; large regional tech-event exhibitor lists | free-zone and economic-department registers where public |

A market missing here: build its pack from (1) the jobs boards people in that market actually
use, (2) its startup and business press, (3) its chambers, free zones and trade fairs, (4) its open
company register — and write the pack into `icp.md` notes so the next run starts from it.
