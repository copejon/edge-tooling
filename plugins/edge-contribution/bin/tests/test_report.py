"""Tests for report.py — aggregate collected activity into report structures.

Covers happy-path matrix/report construction, failure inputs (activity for an
unknown member or an unknown workstream is ignored, never counted), and
boundary/anti-cheat cases: unattributed items counted but kept out of the
matrix, duplicate contributions counted once for breadth but summed per kind for
the IC breakdown, and a member with no activity yielding breadth 0.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import report  # noqa: E402

SIX = ["SNO", "TNA", "TNF", "LVMS", "USHIFT", "TOPO"]


def _activity(member, workstream, kind="assignee"):
    return {"member": member, "workstream": workstream, "kind": kind}


class TestBuildContributionMatrix(unittest.TestCase):
    def test_touched_sets_reflect_activity(self):
        activities = [
            _activity("alice", "SNO"),
            _activity("alice", "TNA"),
            _activity("bob", "SNO"),
        ]
        matrix = report.build_contribution_matrix(activities, ["alice", "bob"], SIX)
        assert matrix.touched["alice"] == {"SNO", "TNA"}
        assert matrix.touched["bob"] == {"SNO"}

    def test_activity_for_unknown_member_is_ignored(self):
        activities = [_activity("stranger", "SNO")]
        matrix = report.build_contribution_matrix(activities, ["alice"], SIX)
        assert matrix.touched["alice"] == set()

    def test_activity_for_unknown_workstream_is_ignored(self):
        activities = [_activity("alice", "BOGUS")]
        matrix = report.build_contribution_matrix(activities, ["alice"], SIX)
        assert matrix.touched["alice"] == set()

    def test_unattributed_activity_is_not_in_matrix(self):
        activities = [_activity("alice", None)]
        matrix = report.build_contribution_matrix(activities, ["alice"], SIX)
        assert matrix.touched["alice"] == set()


class TestCountUnattributed(unittest.TestCase):
    def test_counts_only_none_workstream(self):
        activities = [_activity("alice", None), _activity("alice", "SNO"), _activity("bob", None)]
        assert report.count_unattributed(activities) == 2

    def test_scoped_to_member(self):
        activities = [_activity("alice", None), _activity("bob", None)]
        assert report.count_unattributed(activities, member="alice") == 1


class TestBuildManagerReport(unittest.TestCase):
    def test_report_bundles_metrics_and_unattributed(self):
        activities = [
            _activity("alice", "SNO"),
            _activity("alice", "TNA"),
            _activity("bob", "SNO"),
            _activity("bob", None),
        ]
        result = report.build_manager_report(activities, ["alice", "bob"], SIX, "2026Q2")
        assert result.metrics.breadth_by_member == {"alice": 2, "bob": 1}
        assert result.metrics.flexibility_by_workstream["SNO"] == 2
        assert result.unattributed_count == 1
        assert result.period_label == "2026Q2"


class TestBuildICReport(unittest.TestCase):
    def test_breadth_and_per_kind_breakdown(self):
        activities = [
            _activity("alice", "SNO", "assignee"),
            _activity("alice", "SNO", "pr_authored"),
            _activity("alice", "TNA", "comment"),
            _activity("bob", "SNO", "assignee"),
        ]
        result = report.build_ic_report(activities, "alice", SIX, "2026Q2")
        assert result.breadth == 2
        assert result.total_workstreams == 6
        by_workstream = {activity.workstream: activity.counts for activity in result.activity}
        assert by_workstream["SNO"] == {"assignee": 1, "pr_authored": 1}
        assert by_workstream["TNA"] == {"comment": 1}

    def test_duplicate_contributions_count_once_for_breadth_but_sum_per_kind(self):
        activities = [
            _activity("alice", "SNO", "comment"),
            _activity("alice", "SNO", "comment"),
        ]
        result = report.build_ic_report(activities, "alice", SIX, "2026Q2")
        assert result.breadth == 1
        assert result.activity[0].counts == {"comment": 2}

    def test_member_with_no_activity_has_zero_breadth(self):
        result = report.build_ic_report([], "alice", SIX, "2026Q2")
        assert result.breadth == 0
        assert result.activity == []

    def test_workstreams_appear_in_canonical_order(self):
        activities = [_activity("alice", "TOPO"), _activity("alice", "SNO")]
        result = report.build_ic_report(activities, "alice", SIX, "2026Q2")
        assert [activity.workstream for activity in result.activity] == ["SNO", "TOPO"]


if __name__ == "__main__":
    unittest.main()
