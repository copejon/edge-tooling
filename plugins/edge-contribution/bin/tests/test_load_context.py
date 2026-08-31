"""Tests for load_context.py — parsing the edge-context team roster markdown.

Covers happy-path parsing, failure inputs (malformed rows, missing Rover link,
missing file, no table), and the boundary/anti-cheat cases around the Eng+QE
role filter, whose titles are a substring trap ("Manager, Engineering" and
"Product Security Engineer" contain "Engineer" but must be excluded).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import load_context  # noqa: E402

WELL_FORMED_ROSTER = """# Team Roster

## OpenShift Edge

| Name | GitHub | Role | Location |
|------|--------|------|----------|
| [Jon Cope](https://rover.redhat.com/people/profile/jcope) | copejon | Senior Software Engineer | Texas |
| [Doug Hensel](https://rover.redhat.com/people/profile/dhensel) | dhensel-rh | Senior Software Quality Engineer | North Carolina |
| [Chad Scribner](https://rover.redhat.com/people/profile/cscribne) | brandisher | Manager, Engineering | Germany |
"""

INCLUDED_ROLES = [
    "Software Engineer",
    "Associate Software Engineer",
    "Senior Software Engineer",
    "Principal Software Engineer",
    "Senior Software Quality Engineer",
    "Principal Software Quality Engineer",
    "Associate Software Quality Engineer",
]
EXCLUDED_ROLES = [
    "Senior Manager, Engineering",
    "Manager, Engineering",
    "Associate Manager, Engineering",
    "Principal Product Security Engineer",
    "Principal Product Manager - Technical",
    "Project Manager - Technical",
]


def _write_roster(directory, markdown):
    people_dir = os.path.join(directory, "people")
    os.makedirs(people_dir, exist_ok=True)
    path = os.path.join(people_dir, "team-roster.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    return path


class TestParseRosterHappyPath(unittest.TestCase):
    def test_parses_every_data_row(self):
        members = load_context.parse_roster(WELL_FORMED_ROSTER)
        assert len(members) == 3

    def test_extracts_all_fields_for_a_member(self):
        members = load_context.parse_roster(WELL_FORMED_ROSTER)
        jon = members[0]
        assert jon.name == "Jon Cope"
        assert jon.github == "copejon"
        assert jon.role == "Senior Software Engineer"
        assert jon.kerberos == "jcope"

    def test_derives_jira_username_from_kerberos(self):
        members = load_context.parse_roster(WELL_FORMED_ROSTER)
        assert members[0].jira_username == "jcope@redhat.com"
        assert members[1].kerberos == "dhensel"
        assert members[1].jira_username == "dhensel@redhat.com"


class TestParseRosterFailureInputs(unittest.TestCase):
    def test_row_missing_rover_link_raises(self):
        markdown = WELL_FORMED_ROSTER.replace(
            "[Jon Cope](https://rover.redhat.com/people/profile/jcope)", "Jon Cope"
        )
        with self.assertRaises(load_context.ContextParseError):
            load_context.parse_roster(markdown)

    def test_row_with_wrong_column_count_raises(self):
        markdown = WELL_FORMED_ROSTER + "| [X](https://rover.redhat.com/people/profile/x) | gh |\n"
        with self.assertRaises(load_context.ContextParseError):
            load_context.parse_roster(markdown)

    def test_markdown_without_a_roster_table_raises(self):
        with self.assertRaises(load_context.ContextParseError):
            load_context.parse_roster("# Team Roster\n\nNo table here.\n")

    def test_load_roster_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(load_context.ContextParseError):
                load_context.load_roster(directory)


class TestRoleFilterEdgeCases(unittest.TestCase):
    def test_engineering_and_qe_titles_are_included(self):
        for role in INCLUDED_ROLES:
            assert load_context.is_engineering_or_qe(role) is True, role

    def test_manager_pm_and_security_titles_are_excluded(self):
        for role in EXCLUDED_ROLES:
            assert load_context.is_engineering_or_qe(role) is False, role

    def test_filter_is_case_insensitive(self):
        assert load_context.is_engineering_or_qe("SENIOR SOFTWARE ENGINEER") is True

    def test_load_roster_keeps_only_contributors(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_roster(directory, WELL_FORMED_ROSTER)
            members = load_context.load_roster(directory)
            names = [member.name for member in members]
            assert "Jon Cope" in names
            assert "Doug Hensel" in names
            assert "Chad Scribner" not in names  # Manager, Engineering

    def test_whitespace_padding_in_cells_is_tolerated(self):
        padded = WELL_FORMED_ROSTER.replace("| copejon |", "|   copejon   |")
        members = load_context.parse_roster(padded)
        assert members[0].github == "copejon"


if __name__ == "__main__":
    unittest.main()
