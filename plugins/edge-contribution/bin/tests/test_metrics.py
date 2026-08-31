"""Tests for metrics.py — breadth, flexibility, and opportunity from a binary matrix.

Covers a hand-computed happy-path matrix, failure inputs (empty roster, unknown
member), and boundary/anti-cheat cases: all-zero matrix, zero-contributor
workstreams still present in the vector, full breadth, and the single-active-member
identity between team opportunity and that member's breadth.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import metrics  # noqa: E402

SIX = ["SNO", "TNA", "TNF", "LVMS", "USHIFT", "TOPO"]


def _matrix(members, touched):
    return metrics.ContributionMatrix(members=members, workstreams=list(SIX), touched=touched)


class TestMetricsHappyPath(unittest.TestCase):
    def setUp(self):
        # alice touches 3 workstreams, bob 1, carol none.
        self.matrix = _matrix(
            members=["alice", "bob", "carol"],
            touched={"alice": {"SNO", "TNA", "TNF"}, "bob": {"SNO"}, "carol": set()},
        )

    def test_breadth_per_member(self):
        assert metrics.breadth(self.matrix, "alice") == 3
        assert metrics.breadth(self.matrix, "bob") == 1
        assert metrics.breadth(self.matrix, "carol") == 0

    def test_flexibility_vector_counts_distinct_contributors(self):
        vector = metrics.flexibility_vector(self.matrix)
        assert vector == {"SNO": 2, "TNA": 1, "TNF": 1, "LVMS": 0, "USHIFT": 0, "TOPO": 0}

    def test_total_contributions_is_sum_of_ones(self):
        assert metrics.total_contributions(self.matrix) == 4

    def test_team_flexibility_is_mean_over_all_six_workstreams(self):
        assert metrics.team_flexibility(self.matrix) == 4 / 6

    def test_team_opportunity_is_mean_over_active_members(self):
        # 4 ones across 2 active members (carol is inactive).
        assert metrics.team_opportunity(self.matrix) == 2.0

    def test_active_members_excludes_zero_contribution_members(self):
        assert metrics.active_members(self.matrix) == ["alice", "bob"]

    def test_compute_team_metrics_bundles_everything(self):
        result = metrics.compute_team_metrics(self.matrix)
        assert result.active_member_count == 2
        assert result.total_member_count == 3
        assert result.team_flexibility == 4 / 6
        assert result.team_opportunity == 2.0
        assert result.breadth_by_member == {"alice": 3, "bob": 1, "carol": 0}


class TestMetricsFailureInputs(unittest.TestCase):
    def test_empty_roster_does_not_divide_by_zero(self):
        empty = _matrix(members=[], touched={})
        result = metrics.compute_team_metrics(empty)
        assert result.team_opportunity == 0.0
        assert result.team_flexibility == 0.0
        assert result.active_member_count == 0

    def test_breadth_for_unknown_member_raises(self):
        matrix = _matrix(members=["alice"], touched={"alice": {"SNO"}})
        with self.assertRaises(ValueError):
            metrics.breadth(matrix, "nobody")


class TestMetricsEdgeCases(unittest.TestCase):
    def test_all_zero_matrix_guards_opportunity_and_zeros_flexibility(self):
        matrix = _matrix(members=["alice", "bob"], touched={"alice": set(), "bob": set()})
        result = metrics.compute_team_metrics(matrix)
        assert result.team_opportunity == 0.0
        assert result.team_flexibility == 0.0
        assert set(result.flexibility_by_workstream.values()) == {0}

    def test_zero_contributor_workstream_is_present_in_vector(self):
        matrix = _matrix(members=["alice"], touched={"alice": {"SNO"}})
        vector = metrics.flexibility_vector(matrix)
        assert "TOPO" in vector
        assert vector["TOPO"] == 0
        assert list(vector.keys()) == SIX

    def test_member_active_in_all_six_has_breadth_six(self):
        matrix = _matrix(members=["alice"], touched={"alice": set(SIX)})
        assert metrics.breadth(matrix, "alice") == 6

    def test_single_active_member_opportunity_equals_their_breadth(self):
        matrix = _matrix(members=["alice"], touched={"alice": {"SNO", "TNA"}})
        assert metrics.team_opportunity(matrix) == metrics.breadth(matrix, "alice")

    def test_touched_entries_outside_canonical_workstreams_are_ignored(self):
        matrix = _matrix(members=["alice"], touched={"alice": {"SNO", "BOGUS"}})
        assert metrics.breadth(matrix, "alice") == 1


if __name__ == "__main__":
    unittest.main()
