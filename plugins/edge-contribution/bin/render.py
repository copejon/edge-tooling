#!/usr/bin/env python3
"""Render cross-workstream contribution reports as HTML, plain text, or CSV.

Two report shapes are supported:

* **Manager** — a people x workstream heatmap (a distinct color per contributor)
  plus the Flexibility and Opportunity scores.
* **IC** — one member's breadth ("N of M") and a per-workstream activity breakdown.

Rendering is pure: it turns already-computed data structures into a string, with
no I/O, so every format is unit-testable. The manager HTML is fully
self-contained (inline styles, per-contributor color legend) — it opens in a
browser with no external assets.
"""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from typing import Dict, List

from metrics import ContributionMatrix, TeamMetrics

# Canonical order of activity kinds for IC output columns.
ACTIVITY_KINDS: List[str] = [
    "assignee",
    "qa",
    "comment",
    "ocpstrat_role",
    "pr_authored",
    "pr_reviewed",
]

_VALID_FORMATS = ("html", "text", "csv")


@dataclass(frozen=True)
class WorkstreamActivity:
    """One workstream's activity for a single member, counted by kind."""

    workstream: str
    counts: Dict[str, int] = field(default_factory=dict)

    def total(self) -> int:
        return sum(self.counts.values())


@dataclass(frozen=True)
class ICReport:
    """Personal-breadth report for a single member."""

    period_label: str
    member: str
    breadth: int
    total_workstreams: int
    activity: List[WorkstreamActivity] = field(default_factory=list)
    unattributed_count: int = 0


@dataclass(frozen=True)
class ManagerReport:
    """Team heatmap report across the full roster."""

    period_label: str
    metrics: TeamMetrics
    matrix: ContributionMatrix
    unattributed_count: int = 0


def _require_known_format(output_format: str) -> None:
    if output_format not in _VALID_FORMATS:
        raise ValueError(
            f"unknown output format {output_format!r}; expected one of {_VALID_FORMATS}"
        )


def contributor_colors(members: List[str]) -> Dict[str, str]:
    """Assign each member a distinct, deterministic color (categorical, not intensity)."""
    total = len(members)
    colors: Dict[str, str] = {}
    for index, member in enumerate(members):
        hue = round(index * 360 / total) if total else 0
        colors[member] = f"hsl({hue}, 70%, 60%)"
    return colors


# --- Manager report ---------------------------------------------------------


def render_manager(report: ManagerReport, output_format: str) -> str:
    """Render the manager heatmap + scores in the requested format."""
    _require_known_format(output_format)
    if output_format == "csv":
        return _manager_csv(report)
    if output_format == "text":
        return _manager_text(report)
    return _manager_html(report)


def _cell_is_filled(report: ManagerReport, member: str, workstream: str) -> bool:
    return workstream in report.matrix.touched.get(member, set())


def _manager_csv(report: ManagerReport) -> str:
    metrics_data = report.metrics
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["member", *metrics_data.workstreams])
    for member in metrics_data.members:
        row = [1 if _cell_is_filled(report, member, ws) else 0 for ws in metrics_data.workstreams]
        writer.writerow([member, *row])

    buffer.write("\r\n")
    writer.writerow(["metric", "value"])
    writer.writerow(["team_flexibility", round(metrics_data.team_flexibility, 4)])
    writer.writerow(["team_opportunity", round(metrics_data.team_opportunity, 4)])
    writer.writerow(["active_members", metrics_data.active_member_count])
    writer.writerow(["total_members", metrics_data.total_member_count])
    writer.writerow(["unattributed", report.unattributed_count])
    for workstream, count in metrics_data.flexibility_by_workstream.items():
        writer.writerow([f"flexibility:{workstream}", count])
    return buffer.getvalue()


def _manager_text(report: ManagerReport) -> str:
    metrics_data = report.metrics
    lines = [f"Cross-Workstream Contribution — {report.period_label}", ""]

    header = "  ".join(metrics_data.workstreams)
    name_width = max((len(m) for m in metrics_data.members), default=0)
    lines.append(f"{'':<{name_width}}  {header}")
    for member in metrics_data.members:
        marks = []
        for workstream in metrics_data.workstreams:
            filled = _cell_is_filled(report, member, workstream)
            marks.append("✓".center(len(workstream)) if filled else "·".center(len(workstream)))
        lines.append(f"{member:<{name_width}}  " + "  ".join(marks))

    lines.append("")
    lines.append("Flexibility (distinct contributors per workstream):")
    for workstream, count in metrics_data.flexibility_by_workstream.items():
        lines.append(f"  {workstream}: {count}")
    lines.append(f"  team mean: {metrics_data.team_flexibility:.2f}")

    lines.append("")
    lines.append("Opportunity (workstreams touched per member):")
    for member, count in metrics_data.opportunity_by_member.items():
        lines.append(f"  {member}: {count}")
    lines.append(
        f"  team mean over active: {metrics_data.team_opportunity:.2f} "
        f"({metrics_data.active_member_count}/{metrics_data.total_member_count} active)"
    )

    if report.unattributed_count:
        lines.append("")
        lines.append(f"Note: {report.unattributed_count} unattributed items excluded from matrix.")
    return "\n".join(lines) + "\n"


def _manager_html(report: ManagerReport) -> str:
    metrics_data = report.metrics
    colors = contributor_colors(metrics_data.members)
    parts: List[str] = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>Cross-Workstream Contribution — {html.escape(report.period_label)}</title>",
        "<style>table{border-collapse:collapse}td,th{border:1px solid #ccc;"
        "padding:4px 8px;text-align:center}td.name{text-align:left}</style>",
        "</head><body>",
        f"<h1>Cross-Workstream Contribution — {html.escape(report.period_label)}</h1>",
    ]

    parts.append("<ul class='legend'>")
    for member in metrics_data.members:
        swatch = (
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"background-color:{colors[member]}'></span>"
        )
        parts.append(f"<li>{swatch} {html.escape(member)}</li>")
    parts.append("</ul>")

    parts.append("<table><thead><tr><th>Member</th>")
    for workstream in metrics_data.workstreams:
        parts.append(f"<th>{html.escape(workstream)}</th>")
    parts.append("</tr></thead><tbody>")
    for member in metrics_data.members:
        color = colors[member]
        parts.append(f"<tr><td class='name'>{html.escape(member)}</td>")
        for workstream in metrics_data.workstreams:
            if _cell_is_filled(report, member, workstream):
                parts.append(f"<td style='background-color:{color}'>&#9679;</td>")
            else:
                parts.append("<td></td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")

    parts.append("<h2>Flexibility</h2><ul>")
    for workstream, count in metrics_data.flexibility_by_workstream.items():
        parts.append(f"<li>{html.escape(workstream)}: {count}</li>")
    parts.append(f"</ul><p>Team mean: {metrics_data.team_flexibility:.2f}</p>")

    parts.append("<h2>Opportunity</h2><ul>")
    for member, count in metrics_data.opportunity_by_member.items():
        parts.append(f"<li>{html.escape(member)}: {count}</li>")
    parts.append(
        f"</ul><p>Team mean over active: {metrics_data.team_opportunity:.2f} "
        f"({metrics_data.active_member_count}/{metrics_data.total_member_count} active)</p>"
    )

    if report.unattributed_count:
        parts.append(
            f"<p><em>{report.unattributed_count} unattributed items excluded from matrix.</em></p>"
        )
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


# --- IC report --------------------------------------------------------------


def render_ic(report: ICReport, output_format: str) -> str:
    """Render a single member's breadth report in the requested format."""
    _require_known_format(output_format)
    if output_format == "csv":
        return _ic_csv(report)
    if output_format == "text":
        return _ic_text(report)
    return _ic_html(report)


def _ic_csv(report: ICReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["workstream", *ACTIVITY_KINDS, "total"])
    for activity in report.activity:
        counts = [activity.counts.get(kind, 0) for kind in ACTIVITY_KINDS]
        writer.writerow([activity.workstream, *counts, activity.total()])
    return buffer.getvalue()


def _ic_text(report: ICReport) -> str:
    lines = [
        f"Personal Contribution Breadth — {report.period_label}",
        f"Member: {report.member}",
        f"Breadth: {report.breadth} of {report.total_workstreams} workstreams",
        "",
    ]
    if not report.activity:
        lines.append("No attributed activity in this period.")
    for activity in report.activity:
        detail = ", ".join(
            f"{kind}={activity.counts[kind]}" for kind in ACTIVITY_KINDS if activity.counts.get(kind)
        )
        lines.append(f"  {activity.workstream}: {detail or 'activity present'}")
    if report.unattributed_count:
        lines.append("")
        lines.append(f"Note: {report.unattributed_count} unattributed items not shown.")
    return "\n".join(lines) + "\n"


def _ic_html(report: ICReport) -> str:
    parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>Contribution Breadth — {html.escape(report.member)}</title>",
        "</head><body>",
        f"<h1>Personal Contribution Breadth — {html.escape(report.period_label)}</h1>",
        f"<p>Member: {html.escape(report.member)}</p>",
        f"<p class='breadth'>Breadth: <strong>{report.breadth}</strong> of "
        f"{report.total_workstreams} workstreams</p>",
        "<ul>",
    ]
    for activity in report.activity:
        detail = ", ".join(
            f"{kind}={activity.counts[kind]}" for kind in ACTIVITY_KINDS if activity.counts.get(kind)
        )
        parts.append(f"<li>{html.escape(activity.workstream)}: {html.escape(detail)}</li>")
    parts.append("</ul>")
    if report.unattributed_count:
        parts.append(f"<p><em>{report.unattributed_count} unattributed items not shown.</em></p>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"
