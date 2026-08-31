"""Tests for _common.py — Jira config/auth, HTTP client, and date helpers.

Covers happy-path config and pagination, failure inputs (missing env, 401,
persistent 5xx, malformed JSON), and boundary cases (empty result set, retry
that eventually succeeds, quarter/date parsing).
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _common  # noqa: E402


class _FakeTransport:
    """Records calls and replays a queue of canned responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        response = self._responses.pop(0)
        if callable(response):
            return response(method, path, body)
        return response


def _client(responses, max_retries=2):
    config = _common.JiraConfig(base_url="https://example.test", username="u", api_token="t")
    return _common.JiraClient(config, _FakeTransport(responses), max_retries=max_retries)


class TestJiraConfigFromEnv(unittest.TestCase):
    def test_reads_username_and_token(self):
        env = {"JIRA_USERNAME": "jcope@redhat.com", "JIRA_API_TOKEN": "secret"}
        config = _common.jira_config_from_env(env)
        assert config.username == "jcope@redhat.com"
        assert config.api_token == "secret"
        assert config.base_url.startswith("https://")

    def test_missing_username_raises_auth_error(self):
        with self.assertRaises(_common.JiraAuthError):
            _common.jira_config_from_env({"JIRA_API_TOKEN": "secret"})

    def test_missing_token_raises_auth_error(self):
        with self.assertRaises(_common.JiraAuthError):
            _common.jira_config_from_env({"JIRA_USERNAME": "jcope@redhat.com"})


class TestJiraClientHappyPath(unittest.TestCase):
    def test_search_walks_two_pages_then_stops(self):
        page_one = _common.HttpResponse(200, '{"issues": [{"key": "A-1"}], "nextPageToken": "t2"}')
        page_two = _common.HttpResponse(200, '{"issues": [{"key": "A-2"}], "isLast": true}')
        client = _client([page_one, page_two])
        issues = client.search("project = A", ["key"])
        assert [issue["key"] for issue in issues] == ["A-1", "A-2"]

    def test_empty_result_returns_empty_list(self):
        client = _client([_common.HttpResponse(200, '{"issues": [], "isLast": true}')])
        assert client.search("project = A", ["key"]) == []

    def test_get_issue_returns_parsed_body(self):
        client = _client([_common.HttpResponse(200, '{"key": "A-1", "fields": {}}')])
        assert client.get_issue("A-1", ["components"])["key"] == "A-1"


class TestJiraClientFailureInputs(unittest.TestCase):
    def test_401_raises_auth_error(self):
        client = _client([_common.HttpResponse(401, "nope")])
        with self.assertRaises(_common.JiraAuthError):
            client.search("project = A", ["key"])

    def test_persistent_5xx_raises_after_retries(self):
        responses = [_common.HttpResponse(503, "busy") for _ in range(5)]
        client = _client(responses, max_retries=2)
        with self.assertRaises(_common.CollectorError):
            client.search("project = A", ["key"])

    def test_malformed_json_raises_collector_error(self):
        client = _client([_common.HttpResponse(200, "{not json")])
        with self.assertRaises(_common.CollectorError):
            client.search("project = A", ["key"])


class TestJiraClientEdgeCases(unittest.TestCase):
    def test_retry_then_success(self):
        responses = [
            _common.HttpResponse(503, "busy"),
            _common.HttpResponse(200, '{"issues": [{"key": "A-1"}], "isLast": true}'),
        ]
        client = _client(responses, max_retries=2)
        assert [issue["key"] for issue in client.search("project = A", ["key"])] == ["A-1"]


class TestDateHelpers(unittest.TestCase):
    def test_parse_date(self):
        assert _common.parse_date("2026-04-01") == date(2026, 4, 1)

    def test_quarter_to_window_q2(self):
        window = _common.quarter_to_window("2026Q2")
        assert window.start == date(2026, 4, 1)
        assert window.end == date(2026, 6, 30)

    def test_quarter_to_window_q4(self):
        window = _common.quarter_to_window("2026Q4")
        assert window.start == date(2026, 10, 1)
        assert window.end == date(2026, 12, 31)

    def test_invalid_quarter_raises(self):
        with self.assertRaises(ValueError):
            _common.quarter_to_window("2026Q9")

    def test_window_contains_jira_timestamp(self):
        window = _common.Window(date(2026, 4, 1), date(2026, 6, 30))
        assert window.contains_timestamp("2026-05-01T12:00:00.000+0000") is True
        assert window.contains_timestamp("2026-03-31T12:00:00.000+0000") is False


class TestResolveWindow(unittest.TestCase):
    def test_quarter_takes_precedence(self):
        window = _common.resolve_window(quarter="2026Q2")
        assert window.start == date(2026, 4, 1)

    def test_explicit_date_pair(self):
        window = _common.resolve_window(from_date="2026-01-15", to_date="2026-02-20")
        assert window.start == date(2026, 1, 15)
        assert window.end == date(2026, 2, 20)

    def test_missing_everything_raises(self):
        with self.assertRaises(ValueError):
            _common.resolve_window()

    def test_partial_date_range_raises(self):
        with self.assertRaises(ValueError):
            _common.resolve_window(from_date="2026-01-15")


if __name__ == "__main__":
    unittest.main()
