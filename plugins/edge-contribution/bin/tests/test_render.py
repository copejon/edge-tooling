"""Tests for render.py — html / text / csv renderers for both report types.

Covers happy-path structure per format, failure inputs (unknown format, empty
roster), and boundary/anti-cheat cases: single-column matrix, all-zero matrix,
the unattributed footnote, distinct per-contributor colors, and the CSV
round-trip (including a member name containing a comma).
"""

import csv
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import metrics  # noqa: E402
import render  # noqa: E402

SIX = ["SNO", "TNA", "TNF", "LVMS", "USHIFT", "TOPO"]


def _manager_report(members, touched, workstreams=None, unattributed=0, period="2026Q2"):
    matrix = metrics.ContributionMatrix(
        members=members, workstreams=list(workstreams or SIX), touched=touched
    )
    return render.ManagerReport(
        period_label=period,
        metrics=metrics.compute_team_metrics(matrix),
        matrix=matrix,
        unattributed_count=unattributed,
    )


def _parse_csv_matrix(csv_text):
    section = []
    for line in csv_text.splitlines():
        if line.strip() == "":
            break
        section.append(line)
    rows = list(csv.reader(io.StringIO("\n".join(section))))
    header, data = rows[0], rows[1:]
    workstreams = header[1:]
    members = [row[0] for row in data]
    touched = {
        row[0]: {ws for ws, value in zip(workstreams, row[1:]) if value == "1"} for row in data
    }
    return members, workstreams, touched


class TestContributorColors(unittest.TestCase):
    def test_each_contributor_gets_a_distinct_color(self):
        members = ["alice", "bob", "carol", "dave"]
        colors = render.contributor_colors(members)
        assert set(colors.keys()) == set(members)
        assert len(set(colors.values())) == len(members)

    def test_colors_are_deterministic(self):
        members = ["alice", "bob"]
        assert render.contributor_colors(members) == render.contributor_colors(members)


class TestManagerHappyPath(unittest.TestCase):
    def setUp(self):
        self.report = _manager_report(
            members=["alice", "bob", "carol"],
            touched={"alice": {"SNO", "TNA"}, "bob": {"SNO"}, "carol": set()},
        )

    def test_html_contains_heatmap_scores_and_member_colors(self):
        html = render.render_manager(self.report, "html")
        assert "<table" in html
        for member in ["alice", "bob", "carol"]:
            assert member in html
        assert "Flexibility" in html
        assert "Opportunity" in html
        for color in render.contributor_colors(self.report.metrics.members).values():
            assert color in html

    def test_text_grid_uses_check_and_dot(self):
        text = render.render_manager(self.report, "text")
        assert "✓" in text  # a filled cell exists (alice/SNO)
        assert "·" in text  # an empty cell exists (carol/TOPO)
        assert "Flexibility" in text
        assert "Opportunity" in text

    def test_csv_matrix_round_trips(self):
        csv_text = render.render_manager(self.report, "csv")
        members, workstreams, touched = _parse_csv_matrix(csv_text)
        assert members == self.report.metrics.members
        assert workstreams == SIX
        assert touched == self.report.matrix.touched


class TestManagerFailureInputs(unittest.TestCase):
    def test_unknown_format_raises(self):
        report = _manager_report(members=["alice"], touched={"alice": {"SNO"}})
        with self.assertRaises(ValueError):
            render.render_manager(report, "pdf")

    def test_empty_roster_renders_without_crashing(self):
        report = _manager_report(members=[], touched={})
        for output_format in ("html", "text", "csv"):
            rendered = render.render_manager(report, output_format)
            assert isinstance(rendered, str)
            assert rendered != ""


class TestManagerEdgeCases(unittest.TestCase):
    def test_single_workstream_column(self):
        report = _manager_report(
            members=["alice"], touched={"alice": {"SNO"}}, workstreams=["SNO"]
        )
        _members, workstreams, _touched = _parse_csv_matrix(render.render_manager(report, "csv"))
        assert workstreams == ["SNO"]

    def test_all_zero_matrix_has_no_filled_cells_in_text(self):
        report = _manager_report(members=["alice", "bob"], touched={"alice": set(), "bob": set()})
        text = render.render_manager(report, "text")
        assert "✓" not in text

    def test_member_name_with_comma_is_csv_quoted(self):
        report = _manager_report(
            members=["Cope, Jon"], touched={"Cope, Jon": {"SNO"}}
        )
        members, _workstreams, touched = _parse_csv_matrix(render.render_manager(report, "csv"))
        assert members == ["Cope, Jon"]
        assert touched["Cope, Jon"] == {"SNO"}

    def test_unattributed_footnote_only_when_present(self):
        without = _manager_report(members=["alice"], touched={"alice": {"SNO"}}, unattributed=0)
        with_note = _manager_report(members=["alice"], touched={"alice": {"SNO"}}, unattributed=3)
        assert "unattributed" not in render.render_manager(without, "text").lower()
        assert "unattributed" in render.render_manager(with_note, "text").lower()


class TestICReport(unittest.TestCase):
    def _ic_report(self, breadth=2, activity=None, period="2026Q2"):
        activity = activity if activity is not None else [
            render.WorkstreamActivity("SNO", {"assignee": 3, "pr_authored": 2}),
            render.WorkstreamActivity("TNA", {"pr_reviewed": 1}),
        ]
        return render.ICReport(
            period_label=period,
            member="jcope@redhat.com",
            breadth=breadth,
            total_workstreams=6,
            activity=activity,
        )

    def test_text_shows_breadth_of_total_and_workstreams(self):
        text = render.render_ic(self._ic_report(), "text")
        assert "2 of 6" in text or "2/6" in text
        assert "SNO" in text
        assert "TNA" in text

    def test_html_contains_breadth_and_member(self):
        html = render.render_ic(self._ic_report(), "html")
        assert "jcope@redhat.com" in html
        assert "6" in html

    def test_csv_has_one_row_per_workstream(self):
        csv_text = render.render_ic(self._ic_report(), "csv")
        rows = list(csv.reader(io.StringIO(csv_text)))
        data_rows = [row for row in rows[1:] if row]
        assert len(data_rows) == 2

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            render.render_ic(self._ic_report(), "pdf")

    def test_zero_breadth_still_renders(self):
        text = render.render_ic(self._ic_report(breadth=0, activity=[]), "text")
        assert "0 of 6" in text or "0/6" in text


if __name__ == "__main__":
    unittest.main()
