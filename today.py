#!/usr/bin/env python3
"""
today.py
--------
Collects live stats about a GitHub account (account age, repo count,
total stars, total commits, lines of code added/removed, followers)
and stamps them into two SVG templates (light + dark mode).

Designed to be run on a schedule by a GitHub Action. State that's
expensive to recompute (per-repo LOC counts) is cached to disk in
cache/loc_cache.json so re-runs only re-scan repos that changed.

Env vars required:
    ACCESS_TOKEN   -> GitHub PAT (classic) with 'repo' and 'read:user' scopes
    GITHUB_USERNAME -> the account to report on (defaults to USER_NAME below)
"""

import os
import re
import time
import json
import subprocess
import shutil
from datetime import datetime, timezone
import requests

USER_NAME = os.environ.get("GITHUB_USERNAME", "abdelrahmanyasser2001")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
HEADERS = {"Authorization": f"bearer {ACCESS_TOKEN}"}
GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
LOC_CACHE_FILE = os.path.join(CACHE_DIR, "loc_cache.json")
CLONE_DIR = "/tmp/loc_repo_clone"


# ---------------------------------------------------------------------------
# GraphQL helpers
# ---------------------------------------------------------------------------

def run_query(query, variables=None):
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                  orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        name
        isPrivate
        stargazerCount
        primaryLanguage { name }
      }
    }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST]) {
      totalCount
    }
  }
}
"""

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def get_profile():
    data = run_query(PROFILE_QUERY, {"login": USER_NAME})
    return data["user"]


def get_total_commits(created_at_iso):
    """GraphQL only accepts <=1 year windows, so walk year by year
    from account creation to now and sum totalCommitContributions."""
    created = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    total = 0
    window_start = created
    while window_start < now:
        window_end = min(
            window_start.replace(year=window_start.year + 1), now
        )
        data = run_query(
            CONTRIB_QUERY,
            {
                "login": USER_NAME,
                "from": window_start.isoformat(),
                "to": window_end.isoformat(),
            },
        )
        cc = data["user"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        window_start = window_end
    return total


# ---------------------------------------------------------------------------
# Lines-of-code counting (clone + git log --numstat, cached per repo)
# ---------------------------------------------------------------------------

def load_loc_cache():
    if os.path.exists(LOC_CACHE_FILE):
        with open(LOC_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_loc_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(LOC_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def count_loc_for_repo(repo_name, author_logins):
    """Shallow-clone (full history, single branch) a repo and sum
    additions/deletions attributed to any of author_logins."""
    url = f"https://x-access-token:{ACCESS_TOKEN}@github.com/{USER_NAME}/{repo_name}.git"
    if os.path.exists(CLONE_DIR):
        shutil.rmtree(CLONE_DIR)
    try:
        subprocess.run(
            ["git", "clone", "--quiet", "--single-branch", url, CLONE_DIR],
            check=True, timeout=180,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return 0, 0, 0

    author_filter = "\\|".join(author_logins)
    cmd = (
        f"git log --author='{author_filter}' -i --pretty=tformat: --numstat"
    )
    result = subprocess.run(
        cmd, cwd=CLONE_DIR, shell=True, capture_output=True, text=True
    )

    additions, deletions, commits = 0, 0, 0
    seen_commits = set()
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            additions += int(parts[0])
            deletions += int(parts[1])

    log_count = subprocess.run(
        f"git log --author='{author_filter}' -i --oneline",
        cwd=CLONE_DIR, shell=True, capture_output=True, text=True,
    )
    commits = len(log_count.stdout.splitlines())

    shutil.rmtree(CLONE_DIR, ignore_errors=True)
    return additions, deletions, commits


def get_total_loc(repo_nodes, author_logins):
    cache = load_loc_cache()
    total_add, total_del = 0, 0

    for repo in repo_nodes:
        name = repo["name"]
        if repo.get("isPrivate"):
            continue
        add, deletion, _ = count_loc_for_repo(name, author_logins)
        cache[name] = {"add": add, "del": deletion, "updated": time.time()}
        total_add += add
        total_del += deletion

    save_loc_cache(cache)
    return total_add, total_del


# ---------------------------------------------------------------------------
# SVG templating
# ---------------------------------------------------------------------------

def fmt(n):
    return f"{n:,}"


def justify_len(text, target_len):
    """Right-pad a numeric string with '.' leader dots, GitHub-README-stats
    style, so numbers line up in monospace SVG text."""
    return text + "." * max(0, target_len - len(text))


def render_svg(template_path, output_path, values):
    with open(template_path) as f:
        svg = f.read()
    for key, val in values.items():
        svg = svg.replace("{{ " + key + " }}", str(val))
    with open(output_path, "w") as f:
        f.write(svg)


def main():
    if not ACCESS_TOKEN:
        raise SystemExit("ACCESS_TOKEN env var is required")

    profile = get_profile()
    created_at = profile["createdAt"]
    followers = profile["followers"]["totalCount"]
    repos = profile["repositories"]["nodes"]
    repo_count = profile["repositories"]["totalCount"]
    contributed_to = profile["repositoriesContributedTo"]["totalCount"]
    stars = sum(r["stargazerCount"] for r in repos)

    commits = get_total_commits(created_at)

    author_logins = [USER_NAME]
    additions, deletions = get_total_loc(repos, author_logins)

    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    age_years = (datetime.now(timezone.utc) - created).days // 365
    age_days = (datetime.now(timezone.utc) - created).days % 365

    values = {
        "age_data": f"{age_years} years, {age_days} days",
        "repo_data": fmt(repo_count),
        "contrib_data": fmt(contributed_to),
        "star_data": fmt(stars),
        "commit_data": fmt(commits),
        "follower_data": fmt(followers),
        "loc_add": fmt(additions),
        "loc_del": fmt(deletions),
        "loc_data": fmt(additions - deletions),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    here = os.path.dirname(__file__)
    render_svg(
        os.path.join(here, "templates", "light_mode.svg"),
        os.path.join(here, "light_mode.svg"),
        values,
    )
    render_svg(
        os.path.join(here, "templates", "dark_mode.svg"),
        os.path.join(here, "dark_mode.svg"),
        values,
    )
    print("Stats rendered:", json.dumps(values, indent=2))


if __name__ == "__main__":
    main()
