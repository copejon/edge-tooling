"""Tests for transform-features."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from importlib import import_module

_mod = import_module("transform-features")
transform_feature = _mod.transform_feature


class TestPriority(unittest.TestCase):
    def test_priority_is_persisted(self):
        raw = {"key": "OCPSTRAT-1", "summary": "F", "status": {"name": "New"},
               "priority": {"name": "Blocker"}}
        assert transform_feature(raw)["priority"] == "Blocker"

    def test_priority_defaults_to_undefined_when_absent(self):
        raw = {"key": "OCPSTRAT-2", "summary": "F", "status": {"name": "New"}}
        assert transform_feature(raw)["priority"] == "Undefined"

    def test_priority_defaults_to_undefined_when_null(self):
        raw = {"key": "OCPSTRAT-3", "summary": "F", "status": {"name": "New"}, "priority": None}
        assert transform_feature(raw)["priority"] == "Undefined"


if __name__ == "__main__":
    unittest.main()
