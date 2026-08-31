#!/usr/bin/env python3
"""Aggregate collected activity into the report structures the renderers consume.

The collectors emit flat activity records (``{member, workstream, kind, ...}``).
This module turns those records into a binary contribution matrix, computes the
team metrics, and assembles the manager and IC report objects. It also tallies
unattributed items (``workstream is None``) so they can be reported separately
rather than silently dropped.

All functions are pure transforms over already-loaded data — no file or network
I/O — so the aggregation logic is fully unit-testable. The thin file-loading and
rendering wiring lives in ``main``.
"""

from __future__ import annotations

import argparse
import json
from typing import Dict, List, Optional

from metrics import ContributionMatrix, compute_team_metrics
from render import ICReport, ManagerReport, WorkstreamActivity, render_ic, render_manager
from workstream_map import workstream_acronyms


def build_contribution_matrix(
    activities: List[dict], members: List[str], workstreams: List[str]
) -> ContributionMatrix:
    """Build the binary matrix: a member touches a workstream with ≥1 activity."""
    workstream_set = set(workstreams)
    member_set = set(members)
    touched: Dict[str, set] = {member: set() for member in members}
    for activity in activities:
        member = activity.get("member")
        workstream = activity.get("workstream")
        if member in member_set and workstream in workstream_set:
            touched[member].add(workstream)
    return ContributionMatrix(
        members=list(members), workstreams=list(workstreams), touched=touched
    )


def count_unattributed(activities: List[dict], member: Optional[str] = None) -> int:
    """Count activities that could not be mapped to a workstream.

    When ``member`` is given, count only that member's unattributed items.
    """
    return sum(
        1
        for activity in activities
        if activity.get("workstream") is None
        and (member is None or activity.get("member") == member)
    )


def build_workstream_activities(
    activities: List[dict], member: str, workstreams: List[str]
) -> List[WorkstreamActivity]:
    """Summarize one member's activity per touched workstream, counted by kind."""
    workstream_set = set(workstreams)
    counts_by_workstream: Dict[str, Dict[str, int]] = {}
    for activity in activities:
        if activity.get("member") != member:
            continue
        workstream = activity.get("workstream")
        if workstream not in workstream_set:
            continue
        kind = activity.get("kind", "")
        kind_counts = counts_by_workstream.setdefault(workstream, {})
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    return [
        WorkstreamActivity(workstream, counts_by_workstream[workstream])
        for workstream in workstreams
        if workstream in counts_by_workstream
    ]


def build_manager_report(
    activities: List[dict], members: List[str], workstreams: List[str], period_label: str
) -> ManagerReport:
    """Assemble the manager heatmap + scores report."""
    matrix = build_contribution_matrix(activities, members, workstreams)
    return ManagerReport(
        period_label=period_label,
        metrics=compute_team_metrics(matrix),
        matrix=matrix,
        unattributed_count=count_unattributed(activities),
    )


def build_ic_report(
    activities: List[dict], member: str, workstreams: List[str], period_label: str
) -> ICReport:
    """Assemble the single-member breadth report."""
    matrix = build_contribution_matrix(activities, [member], workstreams)
    breadth = len(matrix.touched.get(member, set()))
    return ICReport(
        period_label=period_label,
        member=member,
        breadth=breadth,
        total_workstreams=len(workstreams),
        activity=build_workstream_activities(activities, member, workstreams),
        unattributed_count=count_unattributed(activities, member),
    )


# --- CLI --------------------------------------------------------------------


def _load_activities(paths: List[str]) -> List[dict]:
    activities: List[dict] = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            activities.extend(json.load(handle))
    return activities


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render a contribution report.")
    parser.add_argument("--view", required=True, choices=("manager", "ic"))
    parser.add_argument(
        "--activity",
        action="append",
        required=True,
        help="an activity JSON file (repeat for jira + github)",
    )
    parser.add_argument("--members-file", help="roster.json (required for the manager view)")
    parser.add_argument("--member", help="Jira username (required for the ic view)")
    parser.add_argument("--period", required=True, help="reporting period label, e.g. 2026Q2")
    parser.add_argument("--format", default="text", choices=("html", "text", "csv"))
    parser.add_argument("--output", help="write here instead of stdout")
    args = parser.parse_args(argv)

    activities = _load_activities(args.activity)
    workstreams = workstream_acronyms()

    if args.view == "manager":
        if not args.members_file:
            parser.error("--members-file is required for --view manager")
        with open(args.members_file, encoding="utf-8") as handle:
            members = [entry["jira_username"] for entry in json.load(handle)]
        rendered = render_manager(
            build_manager_report(activities, members, workstreams, args.period), args.format
        )
    else:
        if not args.member:
            parser.error("--member is required for --view ic")
        rendered = render_ic(
            build_ic_report(activities, args.member, workstreams, args.period), args.format
        )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
