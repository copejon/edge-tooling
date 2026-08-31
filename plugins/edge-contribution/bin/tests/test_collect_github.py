"""Tests for collect_github.py — GitHub PR collection via the ``gh`` CLI.

The command runner and the Jira workstream resolver are both injected, so tests
are hermetic (no ``gh`` subprocess, no Jira network). Coverage spans happy-path
attribution of authored/reviewed PRs, failure inputs (``gh`` non-zero exit,
malformed JSON), and boundary/anti-cheat cases: key in body only, multiple keys
deduped across workstreams, unmapped/absent keys → unattributed (never dropped),
and the search commands carrying the correct owner/author/window scoping.
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _common  # noqa: E402
import collect_github  # noqa: E402

WINDOW = _common.Window(date(2026, 4, 1), date(2026, 6, 30))


def _pr(title, body="", repo="openshift/example", url="https://gh/pr/1", created="2026-05-01T00:00:00Z"):
    return {
        "title": title,
        "body": body,
        "repository": {"nameWithOwner": repo},
        "url": url,
        "createdAt": created,
    }


class FakeRunner:
    def __init__(self, result):
        self._result = result
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return self._result


def _ok(stdout):
    return collect_github.CommandResult(returncode=0, stdout=stdout, stderr="")


def _resolver(mapping):
    return lambda key: mapping.get(key)


class TestExtractJiraKeys(unittest.TestCase):
    def test_finds_known_project_keys(self):
        keys = collect_github.extract_jira_keys("Fixes OCPEDGE-123 and USHIFT-7")
        assert keys == ["OCPEDGE-123", "USHIFT-7"]

    def test_dedupes_and_uppercases(self):
        assert collect_github.extract_jira_keys("ocpbugs-1 OCPBUGS-1") == ["OCPBUGS-1"]

    def test_ignores_unknown_project_prefixes(self):
        assert collect_github.extract_jira_keys("FOO-1 BAR-22") == []

    def test_empty_text_yields_no_keys(self):
        assert collect_github.extract_jira_keys("") == []


class TestAuthoredCollectionHappyPath(unittest.TestCase):
    def test_key_in_title_is_attributed_to_workstream(self):
        runner = FakeRunner(_ok('[{"title": "OCPEDGE-1 fix", "body": "", '
                                '"repository": {"nameWithOwner": "openshift/ovn"}, '
                                '"url": "https://gh/pr/9", "createdAt": "2026-05-01T00:00:00Z"}]'))
        activities = collect_github.collect_authored_activity(
            runner, _resolver({"OCPEDGE-1": "SNO"}), "u@redhat.com", "handle", WINDOW
        )
        assert len(activities) == 1
        activity = activities[0]
        assert activity.kind == "pr_authored"
        assert activity.workstream == "SNO"
        assert activity.repo == "openshift/ovn"
        assert activity.pr_url == "https://gh/pr/9"
        assert activity.source_key == "OCPEDGE-1"

    def test_empty_result_returns_empty_list(self):
        runner = FakeRunner(_ok("[]"))
        activities = collect_github.collect_authored_activity(
            runner, _resolver({}), "u@redhat.com", "handle", WINDOW
        )
        assert activities == []


class TestReviewedCollection(unittest.TestCase):
    def test_reviewed_pr_is_tagged_pr_reviewed(self):
        runner = FakeRunner(_ok(f"[{_pr_json('USHIFT-3 topic', 'body')}]"))
        activities = collect_github.collect_reviewed_activity(
            runner, _resolver({"USHIFT-3": "USHIFT"}), "u@redhat.com", "handle", WINDOW
        )
        assert [a.kind for a in activities] == ["pr_reviewed"]
        assert [a.workstream for a in activities] == ["USHIFT"]


class TestAttributionEdgeCases(unittest.TestCase):
    def test_key_in_body_only_is_found(self):
        runner = FakeRunner(_ok(f"[{_pr_json('no key here', 'relates to USHIFT-9')}]"))
        activities = collect_github.collect_authored_activity(
            runner, _resolver({"USHIFT-9": "USHIFT"}), "u@redhat.com", "handle", WINDOW
        )
        assert [a.workstream for a in activities] == ["USHIFT"]

    def test_multiple_keys_attributed_across_workstreams_deduped(self):
        runner = FakeRunner(_ok(f"[{_pr_json('OCPEDGE-1 OCPEDGE-1', 'also OCPBUGS-5')}]"))
        activities = collect_github.collect_authored_activity(
            runner,
            _resolver({"OCPEDGE-1": "SNO", "OCPBUGS-5": "TNF"}),
            "u@redhat.com",
            "handle",
            WINDOW,
        )
        assert {a.workstream for a in activities} == {"SNO", "TNF"}

    def test_key_resolving_to_none_is_unattributed_not_dropped(self):
        runner = FakeRunner(_ok(f"[{_pr_json('OCPEDGE-2 planning', '')}]"))
        activities = collect_github.collect_authored_activity(
            runner, _resolver({"OCPEDGE-2": None}), "u@redhat.com", "handle", WINDOW
        )
        assert len(activities) == 1
        assert activities[0].workstream is None
        assert activities[0].source_key == "OCPEDGE-2"

    def test_pr_with_no_key_is_unattributed(self):
        runner = FakeRunner(_ok(f"[{_pr_json('cleanup', 'no ticket')}]"))
        activities = collect_github.collect_authored_activity(
            runner, _resolver({}), "u@redhat.com", "handle", WINDOW
        )
        assert len(activities) == 1
        assert activities[0].workstream is None
        assert activities[0].source_key is None


class TestSearchCommands(unittest.TestCase):
    def test_authored_command_scopes_owners_author_and_created_window(self):
        command = collect_github.authored_search_command("handle", WINDOW)
        assert "--author" in command and "handle" in command
        assert command.count("--owner") == 2
        assert "openshift" in command and "openshift-eng" in command
        assert "--created" in command
        assert "2026-04-01..2026-06-30" in command

    def test_reviewed_command_uses_reviewed_by_and_updated_window(self):
        command = collect_github.reviewed_search_command("handle", WINDOW)
        assert "--reviewed-by" in command
        assert "--updated" in command
        assert "2026-04-01..2026-06-30" in command


class TestFailureInputs(unittest.TestCase):
    def test_gh_nonzero_exit_raises(self):
        runner = FakeRunner(collect_github.CommandResult(1, "", "gh: not authenticated"))
        with self.assertRaises(_common.CollectorError):
            collect_github.collect_authored_activity(
                runner, _resolver({}), "u@redhat.com", "handle", WINDOW
            )

    def test_gh_malformed_json_raises(self):
        runner = FakeRunner(_ok("{not json"))
        with self.assertRaises(_common.CollectorError):
            collect_github.collect_authored_activity(
                runner, _resolver({}), "u@redhat.com", "handle", WINDOW
            )


class _FakeIssueClient:
    def __init__(self, issues_by_key, errors=None):
        self._issues = issues_by_key
        self._errors = errors or {}
        self.get_calls = []

    def get_issue(self, key, fields):
        self.get_calls.append(key)
        if key in self._errors:
            raise self._errors[key]
        return self._issues.get(key, {"key": key, "fields": {"components": []}})


def _issue_with_components(key, components):
    return {"key": key, "fields": {"components": [{"name": name} for name in components]}}


class TestJiraWorkstreamResolver(unittest.TestCase):
    def test_resolves_component_to_workstream(self):
        client = _FakeIssueClient({"OCPEDGE-1": _issue_with_components("OCPEDGE-1", ["SNO"])})
        resolve = collect_github.make_jira_workstream_resolver(client)
        assert resolve("OCPEDGE-1") == "SNO"

    def test_planning_component_resolves_to_none(self):
        client = _FakeIssueClient({"OCPEDGE-2": _issue_with_components("OCPEDGE-2", ["Planning"])})
        resolve = collect_github.make_jira_workstream_resolver(client)
        assert resolve("OCPEDGE-2") is None

    def test_result_is_cached(self):
        client = _FakeIssueClient({"OCPEDGE-1": _issue_with_components("OCPEDGE-1", ["SNO"])})
        resolve = collect_github.make_jira_workstream_resolver(client)
        resolve("OCPEDGE-1")
        resolve("OCPEDGE-1")
        assert client.get_calls == ["OCPEDGE-1"]

    def test_missing_issue_error_resolves_to_none(self):
        client = _FakeIssueClient({}, errors={"OCPBUGS-9": _common.CollectorError("404")})
        resolve = collect_github.make_jira_workstream_resolver(client)
        assert resolve("OCPBUGS-9") is None

    def test_auth_error_is_not_swallowed(self):
        client = _FakeIssueClient({}, errors={"OCPEDGE-1": _common.JiraAuthError("401")})
        resolve = collect_github.make_jira_workstream_resolver(client)
        with self.assertRaises(_common.JiraAuthError):
            resolve("OCPEDGE-1")


def _pr_json(title, body):
    import json

    return json.dumps(_pr(title, body))


if __name__ == "__main__":
    unittest.main()
