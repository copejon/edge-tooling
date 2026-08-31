"""Tests for collect_jira.py — Jira REST activity collection and attribution.

The HTTP layer is injected (a fake JiraClient, or a real JiraClient over a fake
transport), so no test touches the network. Coverage spans happy-path
attribution, failure inputs (missing credentials, auth/HTTP errors surfaced),
and boundary/anti-cheat cases: multi-component fan-out, alias de-duplication,
Planning/unmapped → unattributed (never dropped), and comment-window filtering.
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _common  # noqa: E402
import collect_jira  # noqa: E402

WINDOW = _common.Window(date(2026, 4, 1), date(2026, 6, 30))


def _issue(key, components, updated="2026-05-01T10:00:00.000+0000", comments=None, qa=None):
    fields = {
        "components": [{"name": name} for name in components],
        "updated": updated,
        "customfield_10470": qa,
    }
    if comments is not None:
        fields["comment"] = {"comments": comments}
    return {"key": key, "fields": fields}


def _comment(author_email, created):
    return {"author": {"emailAddress": author_email}, "created": created}


class FakeJiraClient:
    """Returns canned issues, routing by a substring match on the JQL."""

    def __init__(self, issues=None, issues_by_jql=None, base_url="https://jira.test"):
        self.base_url = base_url
        self._issues = issues or []
        self._issues_by_jql = issues_by_jql or {}
        self.searches = []

    def search(self, jql, fields):
        self.searches.append(jql)
        for needle, issues in self._issues_by_jql.items():
            if needle in jql:
                return issues
        return list(self._issues)


class _QueuedTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        return self._responses.pop(0)


def _real_client(responses):
    config = _common.JiraConfig("https://jira.test", "u", "t")
    return _common.JiraClient(config, _QueuedTransport(responses), max_retries=1)


class TestAssigneeCollectionHappyPath(unittest.TestCase):
    def test_single_component_is_tagged_with_workstream(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-1", ["SNO"])])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert len(activities) == 1
        assert activities[0].workstream == "SNO"
        assert activities[0].kind == "assignee"
        assert activities[0].issue_key == "OCPEDGE-1"
        assert activities[0].url == "https://jira.test/browse/OCPEDGE-1"

    def test_empty_result_returns_empty_list(self):
        client = FakeJiraClient(issues=[])
        assert collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW) == []


class TestAttributionEdgeCases(unittest.TestCase):
    def test_multiple_components_yield_one_row_per_mappable_workstream(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-2", ["SNO", "Two Node Fencing"])])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert {a.workstream for a in activities} == {"SNO", "TNF"}

    def test_alias_components_dedupe_to_one_workstream(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-3", ["TNF", "Two Node Fencing"])])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert [a.workstream for a in activities] == ["TNF"]

    def test_planning_component_becomes_unattributed_not_dropped(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-4", ["Planning"])])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert len(activities) == 1
        assert activities[0].workstream is None

    def test_issue_without_components_becomes_unattributed(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-5", [])])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert [a.workstream for a in activities] == [None]

    def test_qa_collection_tolerates_null_qa_field(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-6", ["SNO"], qa=None)])
        activities = collect_jira.collect_qa_activity(client, "u@redhat.com", WINDOW)
        assert [a.workstream for a in activities] == ["SNO"]
        assert activities[0].kind == "qa"


class TestCommentCollection(unittest.TestCase):
    def test_comment_by_member_in_window_is_attributed(self):
        issue = _issue(
            "OCPEDGE-7",
            ["SNO"],
            comments=[_comment("u@redhat.com", "2026-05-15T09:00:00.000+0000")],
        )
        client = FakeJiraClient(issues=[issue])
        activities = collect_jira.collect_comment_activity(client, "u@redhat.com", WINDOW)
        assert [a.workstream for a in activities] == ["SNO"]
        assert activities[0].kind == "comment"

    def test_comment_outside_window_is_excluded(self):
        issue = _issue(
            "OCPEDGE-8",
            ["SNO"],
            comments=[_comment("u@redhat.com", "2026-03-01T09:00:00.000+0000")],
        )
        client = FakeJiraClient(issues=[issue])
        assert collect_jira.collect_comment_activity(client, "u@redhat.com", WINDOW) == []

    def test_comment_by_other_author_is_excluded(self):
        issue = _issue(
            "OCPEDGE-9",
            ["SNO"],
            comments=[_comment("someone-else@redhat.com", "2026-05-15T09:00:00.000+0000")],
        )
        client = FakeJiraClient(issues=[issue])
        assert collect_jira.collect_comment_activity(client, "u@redhat.com", WINDOW) == []

    def test_issue_with_no_comment_field_yields_nothing(self):
        client = FakeJiraClient(issues=[_issue("OCPEDGE-10", ["SNO"])])
        assert collect_jira.collect_comment_activity(client, "u@redhat.com", WINDOW) == []


class TestJqlBuilders(unittest.TestCase):
    def test_assignee_jql_scopes_project_assignee_and_window(self):
        jql = collect_jira.assignee_jql("u@redhat.com", WINDOW)
        assert "project = OCPEDGE" in jql
        assert 'assignee = "u@redhat.com"' in jql
        assert "2026-04-01" in jql
        assert "2026-06-30" in jql

    def test_qa_jql_uses_qa_contact_custom_field(self):
        assert "cf[10470]" in collect_jira.qa_contact_jql("u@redhat.com", WINDOW)

    def test_ocpstrat_jql_uses_sme_custom_field(self):
        assert "cf[10475]" in collect_jira.ocpstrat_role_jql("u@redhat.com", WINDOW)


class TestFailureInputs(unittest.TestCase):
    def test_missing_credentials_raise_before_any_http(self):
        calls = []

        def transport(method, path, body):
            calls.append((method, path, body))
            return _common.HttpResponse(200, "{}")

        with self.assertRaises(_common.JiraAuthError):
            collect_jira.build_jira_client({}, transport=transport)
        assert calls == []

    def test_auth_error_propagates_through_collector(self):
        client = _real_client([_common.HttpResponse(401, "nope")])
        with self.assertRaises(_common.JiraAuthError):
            collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)

    def test_malformed_json_propagates_through_collector(self):
        client = _real_client([_common.HttpResponse(200, "{not json")])
        with self.assertRaises(_common.CollectorError):
            collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)


class TestPaginationThroughCollector(unittest.TestCase):
    def test_two_page_search_returns_all_activities(self):
        page_one = _common.HttpResponse(
            200,
            '{"issues": [{"key": "OCPEDGE-1", "fields": '
            '{"components": [{"name": "SNO"}]}}], "nextPageToken": "t2"}',
        )
        page_two = _common.HttpResponse(
            200,
            '{"issues": [{"key": "OCPEDGE-2", "fields": '
            '{"components": [{"name": "MicroShift"}]}}], "isLast": true}',
        )
        client = _real_client([page_one, page_two])
        activities = collect_jira.collect_assignee_activity(client, "u@redhat.com", WINDOW)
        assert {a.workstream for a in activities} == {"SNO", "USHIFT"}


if __name__ == "__main__":
    unittest.main()
