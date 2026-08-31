#!/usr/bin/env python3
"""Standalone Jira REST collector for cross-workstream contribution.

For a reporting window and a set of roster members, this gathers each member's
Jira activity and attributes every item to a workstream via ``workstream_map``:

* OCPEDGE **assignee** — issues assigned to the member, updated in the window.
* OCPEDGE **QA contact** — issues where the member is the QA contact (cf 10470).
* OCPEDGE **comments** — issues the member commented on within the window.
* OCPSTRAT **roles** — items where the member is the SME (cf 10475) or assignee.

Items whose component maps to no workstream (unknown, or the ``Planning``
cutline component) are kept with ``workstream=None`` so the unattributed bucket
can be reported rather than silently dropped. Every item is attributed by the
issue's components; an item with several mappable components fans out to one row
per distinct workstream.

The HTTP layer (a ``JiraClient``) is injected, keeping this collector's logic
pure and unit-testable without live network access.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from _common import (
    JiraClient,
    Transport,
    Window,
    build_default_transport,
    jira_config_from_env,
    resolve_window,
)
from workstream_map import component_to_workstream

_QA_CONTACT_FIELD = "customfield_10470"
_SME_FIELD = "customfield_10475"

_ATTRIBUTION_FIELDS = ["key", "components", "updated", "summary"]
_COMMENT_FIELDS = ["key", "components", "updated", "comment"]


@dataclass(frozen=True)
class Activity:
    """One attributed contribution by one member.

    ``workstream`` is ``None`` for items that could not be mapped (unattributed).
    """

    member: str
    workstream: Optional[str]
    kind: str
    issue_key: str
    url: str
    ts: Optional[str]


# --- JQL builders -----------------------------------------------------------


def _window_clause(window: Window) -> str:
    return f'updated >= "{window.start.isoformat()}" AND updated <= "{window.end.isoformat()}"'


def assignee_jql(member: str, window: Window) -> str:
    return f'project = OCPEDGE AND assignee = "{member}" AND {_window_clause(window)}'


def qa_contact_jql(member: str, window: Window) -> str:
    return f'project = OCPEDGE AND cf[10470] = "{member}" AND {_window_clause(window)}'


def comment_scope_jql(member: str, window: Window) -> str:
    # No JQL clause selects "commented by user", so scope to OCPEDGE issues
    # updated in the window and filter comments client-side.
    return f"project = OCPEDGE AND {_window_clause(window)}"


def ocpstrat_role_jql(member: str, window: Window) -> str:
    return (
        f'project = OCPSTRAT AND (cf[10475] = "{member}" OR assignee = "{member}") '
        f"AND {_window_clause(window)}"
    )


# --- Attribution (pure) -----------------------------------------------------


def _issue_components(issue: dict) -> List[str]:
    components = issue.get("fields", {}).get("components") or []
    return [component["name"] for component in components if component.get("name")]


def _mapped_workstreams(issue: dict) -> List[str]:
    mapped: List[str] = []
    for component_name in _issue_components(issue):
        workstream = component_to_workstream(component_name)
        if workstream and workstream not in mapped:
            mapped.append(workstream)
    return mapped


def issue_to_activities(
    issue: dict, member: str, kind: str, base_url: str, timestamp: Optional[str] = None
) -> List[Activity]:
    """Turn one issue into per-workstream activities (unattributed if unmappable)."""
    issue_key = issue.get("key", "")
    url = f"{base_url}/browse/{issue_key}"
    when = timestamp if timestamp is not None else issue.get("fields", {}).get("updated")
    workstreams = _mapped_workstreams(issue)
    if not workstreams:
        return [Activity(member, None, kind, issue_key, url, when)]
    return [Activity(member, workstream, kind, issue_key, url, when) for workstream in workstreams]


def _member_comments_in_window(issue: dict, member: str, window: Window) -> List[dict]:
    comments = (issue.get("fields", {}).get("comment") or {}).get("comments") or []
    return [
        comment
        for comment in comments
        if _is_member_comment_in_window(comment, member, window)
    ]


def _is_member_comment_in_window(comment: dict, member: str, window: Window) -> bool:
    author_email = (comment.get("author") or {}).get("emailAddress")
    created = comment.get("created")
    if author_email != member or not created:
        return False
    return window.contains_timestamp(created)


def comment_activities(issue: dict, member: str, window: Window, base_url: str) -> List[Activity]:
    """Attribute a member's in-window comments on an issue to its workstream(s)."""
    in_window = _member_comments_in_window(issue, member, window)
    if not in_window:
        return []
    latest = max(comment["created"] for comment in in_window)
    return issue_to_activities(issue, member, "comment", base_url, timestamp=latest)


# --- Orchestration (injected client) ----------------------------------------


def collect_assignee_activity(client: JiraClient, member: str, window: Window) -> List[Activity]:
    issues = client.search(assignee_jql(member, window), _ATTRIBUTION_FIELDS)
    return _flatten(
        issue_to_activities(issue, member, "assignee", client.base_url) for issue in issues
    )


def collect_qa_activity(client: JiraClient, member: str, window: Window) -> List[Activity]:
    issues = client.search(qa_contact_jql(member, window), _ATTRIBUTION_FIELDS)
    return _flatten(
        issue_to_activities(issue, member, "qa", client.base_url) for issue in issues
    )


def collect_comment_activity(client: JiraClient, member: str, window: Window) -> List[Activity]:
    issues = client.search(comment_scope_jql(member, window), _COMMENT_FIELDS)
    return _flatten(
        comment_activities(issue, member, window, client.base_url) for issue in issues
    )


def collect_ocpstrat_role_activity(
    client: JiraClient, member: str, window: Window
) -> List[Activity]:
    issues = client.search(ocpstrat_role_jql(member, window), _ATTRIBUTION_FIELDS)
    return _flatten(
        issue_to_activities(issue, member, "ocpstrat_role", client.base_url) for issue in issues
    )


def collect_member(client: JiraClient, member: str, window: Window) -> List[Activity]:
    """Collect all Jira activity for one member within the window."""
    return [
        *collect_assignee_activity(client, member, window),
        *collect_qa_activity(client, member, window),
        *collect_comment_activity(client, member, window),
        *collect_ocpstrat_role_activity(client, member, window),
    ]


def collect_roster(client: JiraClient, members: List[str], window: Window) -> List[Activity]:
    """Collect Jira activity for every member in the roster."""
    activities: List[Activity] = []
    for member in members:
        activities.extend(collect_member(client, member, window))
    return activities


def _flatten(activity_lists) -> List[Activity]:
    return [activity for activities in activity_lists for activity in activities]


def build_jira_client(
    env: Dict[str, str], transport: Optional[Transport] = None
) -> JiraClient:
    """Build a ``JiraClient`` from the environment.

    Credentials are validated first, so a missing token raises before any
    transport is constructed or any request is sent.
    """
    config = jira_config_from_env(env)
    transport = transport or build_default_transport(config)
    return JiraClient(config, transport)


# --- CLI --------------------------------------------------------------------


def _member_list_from_args(members_arg: Optional[str], members_file: Optional[str]) -> List[str]:
    if members_arg:
        return [member.strip() for member in members_arg.split(",") if member.strip()]
    if members_file:
        with open(members_file, encoding="utf-8") as handle:
            roster = json.load(handle)
        return [entry["jira_username"] for entry in roster]
    raise SystemExit("provide --members or --members-file")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Jira contribution activity.")
    parser.add_argument("--members", help="comma-separated Jira usernames")
    parser.add_argument("--members-file", help="roster.json produced by load_context.py")
    parser.add_argument("--quarter", help="reporting quarter, e.g. 2026Q2")
    parser.add_argument("--from", dest="from_date", help="window start, YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="window end, YYYY-MM-DD")
    parser.add_argument("--output", default="jira_activity.json")
    args = parser.parse_args(argv)

    window = resolve_window(args.quarter, args.from_date, args.to_date)
    members = _member_list_from_args(args.members, args.members_file)
    client = build_jira_client(os.environ)

    activities = collect_roster(client, members, window)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump([asdict(activity) for activity in activities], handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
