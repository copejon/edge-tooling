#!/usr/bin/env python3
"""Tests for scripts/recent-projects.py.

Standalone: python3 tests/test_recent_projects.py
No third-party dependencies (mirrors the script under test).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_hook(workspace: Path, extra_args: list[str] | None = None) -> dict | None:
    """Run recent-projects.py with WORKSPACE_ROOT pointing at workspace."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "recent-projects.py"),
        *(extra_args or []),
    ]
    env = {**os.environ, "WORKSPACE_ROOT": str(workspace)}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        return None
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def write_project(
    projects_dir: Path,
    name: str,
    *,
    status: str = "active",
    last_active: str | None = None,
    project_type: str = "bug",
) -> Path:
    """Create a minimal project directory with a CLAUDE.md frontmatter."""
    d = projects_dir / name
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"project: {name}",
        f"type: {project_type}",
        f"status: {status}",
    ]
    if last_active:
        lines.append(f"last-active: {last_active}")
    lines += ["---", "", f"# {name}", ""]
    (d / "CLAUDE.md").write_text("\n".join(lines))
    return d


class RecentProjectsFixture(unittest.TestCase):
    """Temp workspace with dev-env.yaml and projects dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = Path(self.tmp) / "workspace"
        self.ws.mkdir()
        (self.ws / "dev-env.yaml").write_text("domain: test\nrepos: []\n")
        self.projects = self.ws / "projects"
        self.projects.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)


class TestCollectProjects(RecentProjectsFixture):
    """Test project ordering logic in recent-projects.py."""

    def test_frontmatter_date_beats_mtime(self):
        """A project with last-active sorts above a newer-mtime project without it."""
        # older-project: old mtime but has last-active in the future
        write_project(self.projects, "older-project", last_active="2099-01-01")
        old_time = 1700000000  # 2023-11-14
        p = self.projects / "older-project" / "CLAUDE.md"
        os.utime(p, (old_time, old_time))

        # newer-project: recent mtime but no last-active
        write_project(self.projects, "newer-project")

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        text = result["systemMessage"]
        older_pos = text.index("older-project")
        newer_pos = text.index("newer-project")
        self.assertLess(older_pos, newer_pos,
                        "Project with last-active should sort before mtime-only project")


class TestFallbackToMtime(RecentProjectsFixture):
    """When no last-active field exists, mtime ordering still works."""

    def test_mtime_ordering_without_frontmatter(self):
        """Projects without last-active still sort by newest file mtime."""
        write_project(self.projects, "first")
        old_time = 1700000000
        os.utime(self.projects / "first" / "CLAUDE.md", (old_time, old_time))

        write_project(self.projects, "second")

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        text = result["systemMessage"]
        self.assertLess(text.index("second"), text.index("first"))


class TestMalformedLastActiveFallback(RecentProjectsFixture):
    """A malformed last-active value falls back to mtime, not dropped."""

    def test_malformed_date_falls_back_to_mtime(self):
        """Project with invalid last-active still appears, ordered by mtime."""
        write_project(self.projects, "bad-date", last_active="not-a-date")
        old_time = 1700000000
        os.utime(self.projects / "bad-date" / "CLAUDE.md", (old_time, old_time))

        write_project(self.projects, "no-date")

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        text = result["systemMessage"]
        self.assertIn("bad-date", text)
        self.assertLess(text.index("no-date"), text.index("bad-date"))


class TestDoneProjectsFiltered(RecentProjectsFixture):
    """Done/closed projects never appear regardless of last-active."""

    def test_done_project_excluded(self):
        write_project(self.projects, "finished", status="done",
                      last_active="2099-12-31")
        write_project(self.projects, "active-one", last_active="2026-01-01")

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        self.assertNotIn("finished", result["systemMessage"])
        self.assertIn("active-one", result["systemMessage"])


class TestNamesFlag(RecentProjectsFixture):
    """--names output uses last-active ordering too."""

    def test_names_ordered_by_last_active(self):
        write_project(self.projects, "z-old", last_active="2026-01-01")
        write_project(self.projects, "a-new", last_active="2026-08-01")
        # Set z-old mtime to the future to prove mtime doesn't win
        future = 2000000000
        os.utime(self.projects / "z-old" / "CLAUDE.md", (future, future))

        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "recent-projects.py"),
            "--names",
        ]
        env = {**os.environ, "WORKSPACE_ROOT": str(self.ws)}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        names = result.stdout.strip().splitlines()
        self.assertEqual(names, ["a-new", "z-old"])


class TestLastActiveDateDisplay(RecentProjectsFixture):
    """When last-active is present, LAST ACTIVE column shows the date, not mtime."""

    def test_date_column_shows_frontmatter_date(self):
        write_project(self.projects, "my-proj", last_active="2026-07-15")
        # Force mtime to a different date
        os.utime(self.projects / "my-proj" / "CLAUDE.md", (1700000000, 1700000000))

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        self.assertIn("Jul 15", result["systemMessage"])


class TestResumeStampsLastActive(RecentProjectsFixture):
    """resume-project.py should update last-active on successful resolve."""

    def test_resolve_stamps_last_active(self):
        """Successful resolve updates last-active to today."""
        d = self.projects / "my-proj"
        d.mkdir()
        (d / "CLAUDE.md").write_text(
            "---\nproject: my-proj\ntype: bug\nstatus: active\n"
            "last-active: 2020-01-01\n---\n\n# my-proj\n"
        )

        RESUME_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "resume-project.py"
        env = {**os.environ, "WORKSPACE_ROOT": str(self.ws)}
        result = subprocess.run(
            [sys.executable, str(RESUME_SCRIPT), "my-proj"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "ok")

        text = (d / "CLAUDE.md").read_text()
        today = datetime.date.today().isoformat()
        self.assertIn(f"last-active: {today}", text)

    def test_resolve_inserts_last_active_when_absent(self):
        """If no last-active field exists, insert it after status."""
        d = self.projects / "no-la"
        d.mkdir()
        (d / "CLAUDE.md").write_text(
            "---\nproject: no-la\ntype: bug\nstatus: active\n---\n\n# no-la\n"
        )

        RESUME_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "resume-project.py"
        env = {**os.environ, "WORKSPACE_ROOT": str(self.ws)}
        subprocess.run(
            [sys.executable, str(RESUME_SCRIPT), "no-la"],
            capture_output=True, text=True, env=env,
        )

        text = (d / "CLAUDE.md").read_text()
        today = datetime.date.today().isoformat()
        self.assertIn(f"last-active: {today}", text)
        lines = text.splitlines()
        status_idx = next(i for i, line in enumerate(lines) if line.startswith("status:"))
        la_idx = next(i for i, line in enumerate(lines) if line.startswith("last-active:"))
        self.assertEqual(la_idx, status_idx + 1)


if __name__ == "__main__":
    unittest.main()
