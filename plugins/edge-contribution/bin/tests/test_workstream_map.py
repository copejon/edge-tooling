"""Tests for workstream_map.py — the internal workstream -> Jira component map.

Covers happy-path lookups, failure inputs (unknown/None/empty), and the
boundary/anti-cheat cases: case-insensitivity, whitespace, multi-component
aliases, and the explicitly-excluded ``Planning`` component.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import workstream_map  # noqa: E402

# The canonical map, restated here independently of the module so the test is a
# real oracle rather than a mirror of the implementation.
EXPECTED_ALIAS_TO_ACRONYM = {
    "SNO": "SNO",
    "Two Node with Arbiter": "TNA",
    "TNF": "TNF",
    "Two Node Fencing": "TNF",
    "Logical Volume Manager Storage": "LVMS",
    "MicroShift": "USHIFT",
    "Topology Transitions": "TOPO",
    "Mutable Topology": "TOPO",
}
EXPECTED_ACRONYMS_IN_ORDER = ["SNO", "TNA", "TNF", "LVMS", "USHIFT", "TOPO"]


class TestWorkstreamsHappyPath(unittest.TestCase):
    def test_component_to_workstream_maps_exact_names(self):
        assert workstream_map.component_to_workstream("SNO") == "SNO"
        assert workstream_map.component_to_workstream("Two Node Fencing") == "TNF"
        assert workstream_map.component_to_workstream("MicroShift") == "USHIFT"

    def test_workstream_acronyms_returns_six_in_canonical_order(self):
        assert workstream_map.workstream_acronyms() == EXPECTED_ACRONYMS_IN_ORDER

    def test_workstreams_returns_six_entries_with_name_and_components(self):
        streams = workstream_map.workstreams()
        assert len(streams) == 6
        for stream in streams:
            assert stream.acronym
            assert stream.name
            assert len(stream.components) >= 1


class TestWorkstreamsFailureInputs(unittest.TestCase):
    def test_unknown_component_returns_none(self):
        assert workstream_map.component_to_workstream("Foobar") is None

    def test_none_component_returns_none_without_raising(self):
        assert workstream_map.component_to_workstream(None) is None

    def test_empty_string_component_returns_none(self):
        assert workstream_map.component_to_workstream("") is None

    def test_whitespace_only_component_returns_none(self):
        assert workstream_map.component_to_workstream("   ") is None


class TestWorkstreamsEdgeCases(unittest.TestCase):
    def test_lookup_is_case_insensitive(self):
        assert workstream_map.component_to_workstream("sno") == "SNO"
        assert workstream_map.component_to_workstream("microSHIFT") == "USHIFT"

    def test_lookup_trims_surrounding_whitespace(self):
        assert workstream_map.component_to_workstream("  TNF  ") == "TNF"

    def test_tnf_aliases_both_map_to_tnf(self):
        assert workstream_map.component_to_workstream("TNF") == "TNF"
        assert workstream_map.component_to_workstream("Two Node Fencing") == "TNF"

    def test_topology_aliases_both_map_to_topo(self):
        assert workstream_map.component_to_workstream("Topology Transitions") == "TOPO"
        assert workstream_map.component_to_workstream("Mutable Topology") == "TOPO"

    def test_planning_component_is_excluded(self):
        assert workstream_map.component_to_workstream("Planning") is None

    def test_every_known_alias_maps_as_expected(self):
        for alias, acronym in EXPECTED_ALIAS_TO_ACRONYM.items():
            assert workstream_map.component_to_workstream(alias) == acronym, alias


if __name__ == "__main__":
    unittest.main()
