#!/usr/bin/env python3
"""
github.py — GitHub account-export adapter (personal subject).

A GitHub "Export account data" archive (tar.gz, extracted before ingestion)
holds sharded JSON: `user.json` / `users_000001.json`, `repositories_000001.json`,
plus issues/PR shards. We map: user → identity (name, company, location — the
location geocodes for the map), repositories → voice (`kind: repo` — name +
description are the developer's public "code voice") + language interests,
followers/following (when present) → people by handle.
"""
import re

from ..common import read_json, norm_file, iso_date

NAME = "github"
SUBJECT = "person"
QUARANTINE = {"oauthaccesses", "sshkeys", "gpgkeys", "emailaddresses"}


def detect(file_index):
    """True if the export looks like a GitHub account archive."""
    keys = set(file_index)
    if "repositories" in keys and ("schema" in keys or "user" in keys or "users" in keys):
        return True
    blob = " ".join(str(p).lower() for ps in file_index.values() for p in ps)
    return "repositories" in keys and "github" in blob


def _records(data):
    """GitHub export files are either a JSON list or a dict with one list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]
    return []


def extract(root, file_index, all_paths, col):
    """Parse a GitHub account export into the Collector. Returns consumed keys."""
    consumed = set()
    # export tooling metadata — nothing to extract, but it IS handled
    for p in file_index.get("schema", []):
        consumed.add(norm_file(p.name))

    def files(*keys):
        out = []
        for k in keys:
            for p in file_index.get(k, []):
                if p.suffix.lower() == ".json":
                    out.append(p)
                    consumed.add(norm_file(p.name))
        return out

    # user → identity
    for p in files("user", "users"):
        for u in _records(read_json(p)):
            if not isinstance(u, dict):
                continue
            col.set_identity(NAME, name=u.get("name") or u.get("login", ""),
                             headline=u.get("bio", ""),
                             location=u.get("location", ""))
            if u.get("login"):
                col.identity.setdefault("handles", set()).add(u["login"])
            if u.get("company"):
                col.add_org(NAME, u["company"].lstrip("@"), "referenced")
            break  # first record is the account owner

    # issues / pull requests → per-repo activity counts (aggregated FIRST so the
    # repo note can carry them; issue/PR text is never imported)
    activity = {}
    for kind_key, label in (("issues", "issues"), ("pullrequests", "PRs"),
                            ("pull_requests", "PRs")):
        for p in files(kind_key):
            for r in _records(read_json(p)):
                if not isinstance(r, dict):
                    continue
                repo_url = str(r.get("repository") or r.get("repository_url") or "")
                repo = repo_url.rstrip("/").rsplit("/", 1)[-1]
                if repo:
                    a = activity.setdefault(repo, {"issues": 0, "PRs": 0})
                    a[label] += 1

    # organizations → orgs (member-of)
    for p in files("organizations", "organization"):
        for o in _records(read_json(p)):
            if not isinstance(o, dict):
                continue
            nm = (o.get("name") or o.get("login") or "").strip()
            if nm:
                col.add_org(NAME, nm, "member", tags=["org/member"])

    # repositories → voice (code voice) + language interests (+ activity counts)
    n_repo = 0
    for p in files("repositories", "repository"):
        for r in _records(read_json(p)):
            if not isinstance(r, dict):
                continue
            name = (r.get("name") or str(r.get("url", "")).rsplit("/", 1)[-1]).strip()
            if not name:
                continue
            desc = (r.get("description") or "").strip()
            act = activity.pop(name, None)
            act_txt = (f" ({act['issues']} issues, {act['PRs']} PRs)"
                       if act and (act["issues"] or act["PRs"]) else "")
            col.add_post(NAME, f"{name}" + (f" — {desc}" if desc else "") + act_txt,
                         iso_date(r.get("created_at", "")), "repo", r.get("url", ""),
                         tags=["post/repo"])
            n_repo += 1
            lang = (r.get("primary_language") or r.get("language") or "").strip()
            if lang:
                col.add_interest(NAME, lang)
    # activity for repos not in the repositories shard (e.g. org repos)
    for repo, a in activity.items():
        if a["issues"] or a["PRs"]:
            col.add_interest(NAME, f"active in {repo}")

    # followers / following → people (login handles; public identifiers)
    for key, role in (("followers", "follower"), ("following", "following")):
        for p in files(key):
            for u in _records(read_json(p)):
                if isinstance(u, str):
                    # some shards are plain login/url strings
                    handle = u.rsplit("/", 1)[-1]
                    if handle:
                        col.add_person(NAME, handle, handle=handle,
                                       role=f"github {role}", tags=[f"person/{role}"])
                elif isinstance(u, dict):
                    nm = u.get("name") or u.get("login", "")
                    if nm:
                        col.add_person(NAME, nm, handle=u.get("login", ""),
                                       url=u.get("html_url", ""),
                                       role=f"github {role}", tags=[f"person/{role}"])

    # starred repos → interests
    for p in files("starredrepositories", "stars", "starred"):
        for r in _records(read_json(p)):
            nm = r.get("full_name") or r.get("name") if isinstance(r, dict) else None
            if nm:
                col.add_interest(NAME, str(nm))

    if n_repo:
        col.note(f"[github] {n_repo} repositories (code voice)")
    return consumed
