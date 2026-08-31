#!/usr/bin/env python3
"""Standalone GitHub collector for cross-workstream contribution.

For a reporting window and a set of roster members, this gathers each member's
pull-request activity via the ``gh`` CLI and attributes every PR to a workstream:

* **pr_authored** — PRs the member opened in ``openshift``/``openshift-eng``.
* **pr_reviewed** — PRs the member reviewed in the same orgs.

Attribution parses referenced Jira keys from the PR title and body, then resolves
each key to a workstream via a Jira lookup (the resolver is injected). A PR that
references no mappable workstream is kept with ``workstream=None`` so it lands in
the unattributed bucket rather than being dropped.

Both impure edges — the ``gh`` command runner and the Jira resolver — are
injected, so this collector's logic is fully unit-testable without a subprocess
or network access.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

from _common import (
    CollectorError,
    JiraAuthError,
    JiraClient,
    Window,
    jira_config_from_env,
    resolve_window,
)
from workstream_map import component_to_workstream

# A resolver maps a Jira key to a workstream acronym, or None if unmappable.
WorkstreamResolver = Callable[[str], Optional[str]]

_OWNERS = ("openshift", "openshift-eng")
_PR_JSON_FIELDS = "number,title,body,repository,url,createdAt"
_SEARCH_LIMIT = "1000"

_JIRA_KEY_PATTERN = re.compile(
    r"\b(?:OCPEDGE|USHIFT|OCPBUGS|OCPSTRAT|MGMT|ETCD|RHEL|CNV)-\d+\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandResult:
    """The outcome of running an external command."""

    returncode: int
    stdout: str
    stderr: str


# A runner takes an argv list and returns its CommandResult.
CommandRunner = Callable[[List[str]], CommandResult]


@dataclass(frozen=True)
class GithubActivity:
    """One attributed pull-request contribution by one member."""

    member: str
    workstream: Optional[str]
    kind: str
    repo: str
    pr_url: str
    ts: Optional[str]
    source_key: Optional[str]


def extract_jira_keys(text: str) -> List[str]:
    """Return the distinct known-project Jira keys referenced in ``text``.

    Matching is case-insensitive; keys are normalized to upper case and returned
    in first-seen order.
    """
    keys: List[str] = []
    for match in _JIRA_KEY_PATTERN.finditer(text or ""):
        key = match.group(0).upper()
        if key not in keys:
            keys.append(key)
    return keys


# --- Attribution (pure) -----------------------------------------------------


def _pr_repo(pr: dict) -> str:
    repository = pr.get("repository") or {}
    return repository.get("nameWithOwner") or repository.get("name") or ""


def pr_to_activities(
    pr: dict, member: str, kind: str, resolve_workstream: WorkstreamResolver
) -> List[GithubActivity]:
    """Turn one PR into per-workstream activities (unattributed if unmappable)."""
    text = f"{pr.get('title', '')}\n{pr.get('body') or ''}"
    keys = extract_jira_keys(text)
    repo = _pr_repo(pr)
    url = pr.get("url", "")
    timestamp = pr.get("createdAt")

    attributions = _attribute_keys(keys, resolve_workstream)
    if not attributions:
        source_key = keys[0] if keys else None
        return [GithubActivity(member, None, kind, repo, url, timestamp, source_key)]
    return [
        GithubActivity(member, workstream, kind, repo, url, timestamp, key)
        for workstream, key in attributions
    ]


def _attribute_keys(
    keys: List[str], resolve_workstream: WorkstreamResolver
) -> List[tuple]:
    attributions: List[tuple] = []
    seen: set = set()
    for key in keys:
        workstream = resolve_workstream(key)
        if workstream and workstream not in seen:
            seen.add(workstream)
            attributions.append((workstream, key))
    return attributions


# --- Search commands --------------------------------------------------------


def _window_range(window: Window) -> str:
    return f"{window.start.isoformat()}..{window.end.isoformat()}"


def _base_search_command() -> List[str]:
    command = ["gh", "search", "prs"]
    for owner in _OWNERS:
        command.extend(["--owner", owner])
    return command


def authored_search_command(handle: str, window: Window) -> List[str]:
    return [
        *_base_search_command(),
        "--author",
        handle,
        "--created",
        _window_range(window),
        "--json",
        _PR_JSON_FIELDS,
        "--limit",
        _SEARCH_LIMIT,
    ]


def reviewed_search_command(handle: str, window: Window) -> List[str]:
    # The precise signal is a review's submittedAt; the `gh search` fallback
    # approximates it with the PR's --updated window (see references).
    return [
        *_base_search_command(),
        "--reviewed-by",
        handle,
        "--updated",
        _window_range(window),
        "--json",
        _PR_JSON_FIELDS,
        "--limit",
        _SEARCH_LIMIT,
    ]


# --- Orchestration (injected runner + resolver) -----------------------------


def _run_gh_json(runner: CommandRunner, command: List[str]) -> list:
    result = runner(command)
    if result.returncode != 0:
        raise CollectorError(f"gh exited {result.returncode}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise CollectorError(f"malformed JSON from gh: {error}") from error


def collect_authored_activity(
    runner: CommandRunner,
    resolve_workstream: WorkstreamResolver,
    member: str,
    handle: str,
    window: Window,
) -> List[GithubActivity]:
    prs = _run_gh_json(runner, authored_search_command(handle, window))
    return _flatten(
        pr_to_activities(pr, member, "pr_authored", resolve_workstream) for pr in prs
    )


def collect_reviewed_activity(
    runner: CommandRunner,
    resolve_workstream: WorkstreamResolver,
    member: str,
    handle: str,
    window: Window,
) -> List[GithubActivity]:
    prs = _run_gh_json(runner, reviewed_search_command(handle, window))
    return _flatten(
        pr_to_activities(pr, member, "pr_reviewed", resolve_workstream) for pr in prs
    )


def collect_member_github(
    runner: CommandRunner,
    resolve_workstream: WorkstreamResolver,
    member: str,
    handle: str,
    window: Window,
) -> List[GithubActivity]:
    """Collect authored and reviewed PR activity for one member."""
    return [
        *collect_authored_activity(runner, resolve_workstream, member, handle, window),
        *collect_reviewed_activity(runner, resolve_workstream, member, handle, window),
    ]


def _flatten(activity_lists) -> List[GithubActivity]:
    return [activity for activities in activity_lists for activity in activities]


def make_jira_workstream_resolver(client: JiraClient) -> WorkstreamResolver:
    """Return a cached resolver from Jira key to workstream via issue components.

    A missing or unreadable issue resolves to ``None`` (unattributed), but an
    authentication failure is propagated so a global credential problem is not
    silently masked.
    """
    cache: dict = {}

    def resolve(key: str) -> Optional[str]:
        if key in cache:
            return cache[key]
        cache[key] = _resolve_uncached(client, key)
        return cache[key]

    return resolve


def _resolve_uncached(client: JiraClient, key: str) -> Optional[str]:
    try:
        issue = client.get_issue(key, ["components"])
    except JiraAuthError:
        raise
    except CollectorError:
        return None
    for component in issue.get("fields", {}).get("components") or []:
        workstream = component_to_workstream(component.get("name"))
        if workstream:
            return workstream
    return None


# --- CLI --------------------------------------------------------------------


def build_default_runner() -> CommandRunner:
    """Build the production runner backed by ``subprocess``."""
    import subprocess

    def runner(command: List[str]) -> CommandResult:
        completed = subprocess.run(command, capture_output=True, text=True)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    return runner


def main(argv: Optional[List[str]] = None) -> int:
    import os

    from _common import JiraClient, build_default_transport

    parser = argparse.ArgumentParser(description="Collect GitHub PR contribution activity.")
    parser.add_argument(
        "--members-file",
        required=True,
        help="roster.json produced by load_context.py (needs github + jira_username)",
    )
    parser.add_argument("--quarter", help="reporting quarter, e.g. 2026Q2")
    parser.add_argument("--from", dest="from_date", help="window start, YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="window end, YYYY-MM-DD")
    parser.add_argument("--output", default="github_activity.json")
    args = parser.parse_args(argv)

    window = resolve_window(args.quarter, args.from_date, args.to_date)
    with open(args.members_file, encoding="utf-8") as handle:
        roster = json.load(handle)

    config = jira_config_from_env(os.environ)
    client = JiraClient(config, build_default_transport(config))
    resolve_workstream = make_jira_workstream_resolver(client)
    runner = build_default_runner()

    activities: List[GithubActivity] = []
    for member in roster:
        activities.extend(
            collect_member_github(
                runner,
                resolve_workstream,
                member["jira_username"],
                member["github"],
                window,
            )
        )

    with open(args.output, "w", encoding="utf-8") as output:
        json.dump([asdict(activity) for activity in activities], output, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
