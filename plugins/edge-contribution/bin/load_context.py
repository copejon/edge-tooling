#!/usr/bin/env python3
"""Load the OpenShift Edge roster from the edge-context repository.

Parses ``people/team-roster.md`` (a GitHub-flavored markdown table) into typed
``Member`` records and filters the roster down to engineering and QE roles, which
are the contributors this plugin measures. Workstreams come from
``workstream_map`` — this module does not parse workstream markdown.

Run standalone to emit the filtered roster as JSON:

    python3 load_context.py --edge-context ../edge-context [--output roster.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional

ROSTER_RELATIVE_PATH = os.path.join("people", "team-roster.md")

_NAME_LINK_PATTERN = re.compile(r"^\[(?P<name>.+?)\]\((?P<url>[^)]+)\)$")
_EXPECTED_COLUMN_COUNT = 4


class ContextParseError(Exception):
    """Raised when edge-context data cannot be read or parsed as expected."""


@dataclass(frozen=True)
class Member:
    """A roster member and the identities used to attribute their activity."""

    name: str
    github: str
    role: str
    location: str
    kerberos: str
    jira_username: str


def is_engineering_or_qe(role: str) -> bool:
    """Return whether a role title is a software engineering or QE contributor.

    Managers, product managers, and product security roles are excluded even
    though their titles contain the word "Engineer"/"Engineering"; the filter
    keys on the full phrases "software engineer" and "software quality engineer".
    """
    normalized = role.lower()
    return "software engineer" in normalized or "software quality engineer" in normalized


def _split_table_row(line: str) -> List[str]:
    cells = line.split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def _is_separator_row(cells: List[str]) -> bool:
    return bool(cells) and all(set(cell) <= set("-: ") and "-" in cell for cell in cells)


def _is_header_row(cells: List[str]) -> bool:
    lowered = [cell.lower() for cell in cells]
    return "name" in lowered and "github" in lowered and "role" in lowered


def _kerberos_from_rover_url(url: str) -> str:
    kerberos = url.rstrip("/").rsplit("/", 1)[-1].strip()
    if not kerberos or "/" in kerberos or "." in kerberos:
        raise ContextParseError(f"cannot derive kerberos id from profile URL: {url!r}")
    return kerberos


def _member_from_cells(cells: List[str]) -> Member:
    if len(cells) != _EXPECTED_COLUMN_COUNT:
        raise ContextParseError(
            f"roster row has {len(cells)} columns, expected {_EXPECTED_COLUMN_COUNT}: {cells!r}"
        )
    name_match = _NAME_LINK_PATTERN.match(cells[0])
    if name_match is None:
        raise ContextParseError(f"roster name cell is not a Rover profile link: {cells[0]!r}")
    kerberos = _kerberos_from_rover_url(name_match.group("url"))
    return Member(
        name=name_match.group("name").strip(),
        github=cells[1],
        role=cells[2],
        location=cells[3],
        kerberos=kerberos,
        jira_username=f"{kerberos}@redhat.com",
    )


def parse_roster(markdown: str) -> List[Member]:
    """Parse every member row from the roster markdown table (unfiltered).

    Raises ``ContextParseError`` if no roster table is present or if a data row
    is malformed (wrong column count or a name cell without a Rover link) — bad
    rows are surfaced, never silently skipped.
    """
    lines = markdown.splitlines()
    header_index = _find_header_index(lines)
    if header_index is None:
        raise ContextParseError("no roster table (Name | GitHub | Role | ...) found in markdown")

    separator = _split_table_row(lines[header_index + 1]) if header_index + 1 < len(lines) else []
    if not _is_separator_row(separator):
        raise ContextParseError("roster header is not followed by a table separator row")

    members: List[Member] = []
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        members.append(_member_from_cells(_split_table_row(line)))
    if not members:
        raise ContextParseError("roster table has a header but no member rows")
    return members


def _find_header_index(lines: List[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if line.strip().startswith("|") and _is_header_row(_split_table_row(line)):
            return index
    return None


def filter_contributors(members: List[Member]) -> List[Member]:
    """Keep only engineering and QE members (see ``is_engineering_or_qe``)."""
    return [member for member in members if is_engineering_or_qe(member.role)]


def load_roster(edge_context_dir: str) -> List[Member]:
    """Read and parse the roster file, returning only Eng/QE contributors."""
    path = os.path.join(edge_context_dir, ROSTER_RELATIVE_PATH)
    try:
        with open(path, encoding="utf-8") as handle:
            markdown = handle.read()
    except OSError as error:
        raise ContextParseError(f"cannot read roster file at {path}: {error}") from error
    return filter_contributors(parse_roster(markdown))


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the Eng/QE roster from edge-context")
    parser.add_argument("--edge-context", required=True, help="path to an edge-context checkout")
    parser.add_argument("--output", help="write roster JSON here (default: stdout)")
    args = parser.parse_args()

    try:
        members = load_roster(args.edge_context)
    except ContextParseError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    payload = json.dumps([asdict(member) for member in members], indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    else:
        print(payload)


if __name__ == "__main__":
    main()
