#!/usr/bin/env python3
"""Cross-workstream contribution metrics from a binary contribution matrix.

Given which workstreams each roster member touched at least once in a period,
this computes three metrics defined in ``references/metrics.md``:

* **Breadth** (per member) — how many workstreams the member touched.
* **Flexibility** (per workstream, and a team mean) — how many distinct members
  touched a workstream. The team scalar is the mean over *all* workstreams.
* **Opportunity** (per member, and a team mean) — a member's breadth; the team
  scalar is the mean over *active* members (those with at least one contribution).

All inputs are pure data, so this module has no I/O and is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass(frozen=True)
class ContributionMatrix:
    """Who touched which workstreams during the reporting period.

    ``touched`` maps a member to the set of workstream acronyms they contributed
    to. Acronyms outside ``workstreams`` are ignored, and a member absent from
    ``touched`` is treated as having contributed to nothing.
    """

    members: List[str]
    workstreams: List[str]
    touched: Dict[str, Set[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamMetrics:
    """The full metric bundle for a team over one reporting period."""

    workstreams: List[str]
    members: List[str]
    breadth_by_member: Dict[str, int]
    flexibility_by_workstream: Dict[str, int]
    team_flexibility: float
    opportunity_by_member: Dict[str, int]
    team_opportunity: float
    active_member_count: int
    total_member_count: int


def _touched_workstreams(matrix: ContributionMatrix, member: str) -> Set[str]:
    return matrix.touched.get(member, set()) & set(matrix.workstreams)


def breadth(matrix: ContributionMatrix, member: str) -> int:
    """Return how many canonical workstreams ``member`` touched.

    Raises ``ValueError`` if ``member`` is not part of the matrix roster.
    """
    if member not in matrix.members:
        raise ValueError(f"member not in matrix roster: {member!r}")
    return len(_touched_workstreams(matrix, member))


def breadth_by_member(matrix: ContributionMatrix) -> Dict[str, int]:
    """Return breadth for every member, in roster order."""
    return {member: len(_touched_workstreams(matrix, member)) for member in matrix.members}


def flexibility_vector(matrix: ContributionMatrix) -> Dict[str, int]:
    """Return distinct-contributor counts per workstream, in canonical order.

    Every workstream is present, including those with zero contributors.
    """
    counts = {workstream: 0 for workstream in matrix.workstreams}
    for member in matrix.members:
        for workstream in _touched_workstreams(matrix, member):
            counts[workstream] += 1
    return counts


def total_contributions(matrix: ContributionMatrix) -> int:
    """Return the number of 1s in the matrix (sum of per-member breadth)."""
    return sum(breadth_by_member(matrix).values())


def team_flexibility(matrix: ContributionMatrix) -> float:
    """Return the mean distinct-contributor count over all workstreams."""
    if not matrix.workstreams:
        return 0.0
    return total_contributions(matrix) / len(matrix.workstreams)


def active_members(matrix: ContributionMatrix) -> List[str]:
    """Return members with at least one contribution, in roster order."""
    return [member for member, count in breadth_by_member(matrix).items() if count > 0]


def team_opportunity(matrix: ContributionMatrix) -> float:
    """Return the mean breadth over active members (0.0 when none are active)."""
    active = active_members(matrix)
    if not active:
        return 0.0
    return total_contributions(matrix) / len(active)


def compute_team_metrics(matrix: ContributionMatrix) -> TeamMetrics:
    """Compute the full metric bundle for a reporting period."""
    per_member_breadth = breadth_by_member(matrix)
    return TeamMetrics(
        workstreams=list(matrix.workstreams),
        members=list(matrix.members),
        breadth_by_member=per_member_breadth,
        flexibility_by_workstream=flexibility_vector(matrix),
        team_flexibility=team_flexibility(matrix),
        opportunity_by_member=dict(per_member_breadth),
        team_opportunity=team_opportunity(matrix),
        active_member_count=len(active_members(matrix)),
        total_member_count=len(matrix.members),
    )
