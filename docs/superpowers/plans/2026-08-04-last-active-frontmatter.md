# `last-active` Frontmatter for Project Ordering

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Order recent projects by when they were last meaningfully worked on, using a `last-active: YYYY-MM-DD` frontmatter field instead of filesystem mtime.

**Architecture:** Add a `last-active:` field to project CLAUDE.md frontmatter. `recent-projects.py` reads it with its existing yaml-free parser and prefers it over `newest_mtime()`. Three skills (`new-project`, `update-project`, `close-project`) write the field; `resume-project` does not — reading a project is not working on it.

**Tech Stack:** Python 3.9+, Bash (test suite), no new dependencies. `recent-projects.py` stays yaml-free.

## Global Constraints

- Python 3.9+ with `from __future__ import annotations` — macOS system python.
- `recent-projects.py` must **never** import PyYAML or any third-party module.
- All scripts emit JSON on stdout; no stderr for normal operation.
- Tests run standalone: `python3 tests/test_recent_projects.py`.
- Plugin root = `/home/pfontani/Workspace/edge-tooling/plugins/workspace/`.

---

### Task 1: Teach `recent-projects.py` to prefer `last-active` over mtime

**Files:**
- Modify: `scripts/recent-projects.py:48-88` (collect_projects)
- Create: `tests/test_recent_projects.py`

**Interfaces:**
- Consumes: `parse_frontmatter()` (already returns `dict[str, str]`)
- Produces: `collect_projects()` returns entries sorted by `last-active` date (when present), falling back to `newest_mtime()` for projects without the field. Each entry gains a `"sort_source"` key (`"frontmatter"` or `"mtime"`) for testability.

- [ ] **Step 1: Write the test file scaffold and first test — frontmatter date preferred over mtime**

```python
#!/usr/bin/env python3
"""Tests for scripts/recent-projects.py.

Standalone: python3 tests/test_recent_projects.py
No third-party dependencies (mirrors the script under test).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
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


class TestCollectProjects(unittest.TestCase):
    """Test project ordering logic in recent-projects.py."""

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

    def test_frontmatter_date_beats_mtime(self):
        """A project with last-active sorts above a newer-mtime project without it."""
        # older-project: old mtime but has last-active today
        write_project(self.projects, "older-project", last_active="2026-08-04")
        # Set its mtime to the past
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


class TestFallbackToMtime(unittest.TestCase):
    """When no last-active field exists, mtime ordering still works."""

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


class TestDoneProjectsFiltered(unittest.TestCase):
    """Done/closed projects never appear regardless of last-active."""

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

    def test_done_project_excluded(self):
        write_project(self.projects, "finished", status="done",
                      last_active="2099-12-31")
        write_project(self.projects, "active-one", last_active="2026-01-01")

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        self.assertNotIn("finished", result["systemMessage"])
        self.assertIn("active-one", result["systemMessage"])


class TestNamesFlag(unittest.TestCase):
    """--names output uses last-active ordering too."""

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


class TestLastActiveDateDisplay(unittest.TestCase):
    """When last-active is present, LAST ACTIVE column shows the date, not mtime."""

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

    def test_date_column_shows_frontmatter_date(self):
        write_project(self.projects, "my-proj", last_active="2026-07-15")
        # Force mtime to a different date
        os.utime(self.projects / "my-proj" / "CLAUDE.md", (1700000000, 1700000000))

        result = run_hook(self.ws)
        self.assertIsNotNone(result)
        self.assertIn("Jul 15", result["systemMessage"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && python3 tests/test_recent_projects.py -v`
Expected: Failures — `recent-projects.py` ignores `last-active` and sorts by mtime.

- [ ] **Step 3: Modify `collect_projects` to prefer `last-active` over mtime**

In `scripts/recent-projects.py`, replace the `collect_projects` function (lines 65-89):

```python
def _parse_last_active(value: str) -> float | None:
    """Parse a YYYY-MM-DD date string into a timestamp, or None."""
    try:
        parts = value.split("-")
        if len(parts) != 3:
            return None
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(y, m, d, 23, 59, 59).timestamp()
    except (ValueError, OverflowError):
        return None


def collect_projects(projects_dir: Path) -> list[dict]:
    """Collect non-done projects with their metadata, sorted by last-active date or mtime."""
    entries = []
    for d in sorted(projects_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue

        fm = parse_frontmatter(d / "CLAUDE.md")
        if fm.get("status", "").lower() in TERMINAL_STATUSES:
            continue

        last_active_str = fm.get("last-active", "")
        la_ts = _parse_last_active(last_active_str) if last_active_str else None

        if la_ts is not None:
            sort_ts = la_ts
            date_str = datetime.fromtimestamp(la_ts).strftime("%b %d")
            sort_source = "frontmatter"
        else:
            sort_ts = newest_mtime(d)
            if sort_ts is None:
                continue
            date_str = datetime.fromtimestamp(sort_ts).strftime("%b %d %H:%M")
            sort_source = "mtime"

        entries.append({
            "name": d.name,
            "type": fm.get("type", "—"),
            "status": fm.get("status", "—"),
            "mtime": sort_ts,
            "date_str": date_str,
            "sort_source": sort_source,
        })

    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries
```

Key decisions:
- `last-active` parsed manually (no `datetime.strptime` — keeps it simple and avoids format-string portability).
- When `last-active` is present, the timestamp is set to 23:59:59 of that day, so a frontmatter date of today always beats an mtime from earlier today.
- Display format: frontmatter dates show `"Jul 15"` (date only, no time — the field is date-precision). Mtime fallback keeps the existing `"Jul 15 14:30"` format with time, making it visually obvious which source is in use.
- The `sort_source` field is internal — not displayed, but available for test assertions.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && python3 tests/test_recent_projects.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_recent_projects.py scripts/recent-projects.py
git commit -m "workspace: prefer last-active frontmatter over mtime in recent-projects

Projects with a last-active: YYYY-MM-DD field in their CLAUDE.md
frontmatter now sort by that date instead of filesystem mtime.
Falls back to mtime for older projects without the field."
```

---

### Task 2: Teach `update-project` to write `last-active`

This is a skill change (SKILL.md), not a script change. The skill instructs Claude to update the frontmatter field when applying session updates.

**Files:**
- Modify: `skills/update-project/SKILL.md`

**Interfaces:**
- Consumes: nothing new
- Produces: `last-active: YYYY-MM-DD` in project CLAUDE.md frontmatter after every update

- [ ] **Step 1: Add `last-active` to the update-project skill's Step 4**

In `skills/update-project/SKILL.md`, after the existing "Scope Rules" section's "NEVER touch" list (line 23), add `last-active` as a required frontmatter update. Insert after the `## Step 3: Identify Updates` section's list item 5 (line 46), before `## Step 4: Apply`:

```markdown
6. **`last-active` timestamp** — always update `last-active: <YYYY-MM-DD>`
   in the frontmatter to today's date when any other update is applied.
   If the field does not exist yet, add it after the `status:` line.
```

Then in `## Step 4: Apply` (line 50), after "Edit each file individually", add:

```markdown
Always set `last-active: <YYYY-MM-DD>` (today) in the frontmatter as
the first edit to CLAUDE.md, before applying checklist or progress
changes. This field drives the SessionStart ordering hook.
```

- [ ] **Step 2: Verify the edit reads correctly**

Read `skills/update-project/SKILL.md` in full to confirm the additions are clear and don't contradict the existing "NEVER touch" list (which covers `status:`, memory files, tasks, and repo sources — `last-active` is none of those).

- [ ] **Step 3: Commit**

```bash
git add skills/update-project/SKILL.md
git commit -m "workspace: update-project writes last-active frontmatter

The skill now sets last-active: YYYY-MM-DD on every update,
driving the SessionStart ordering hook."
```

---

### Task 3: Teach `new-project` to write `last-active` at creation

**Files:**
- Modify: `skills/new-project/SKILL.md`

**Interfaces:**
- Consumes: nothing new
- Produces: `last-active: YYYY-MM-DD` in newly created project CLAUDE.md frontmatter

- [ ] **Step 1: Add `last-active` to the Common Frontmatter template**

In `skills/new-project/SKILL.md`, in the "Common Frontmatter" YAML block (line 359), add `last-active:` after `created:`:

```yaml
created: <YYYY-MM-DD>
last-active: <YYYY-MM-DD>
status: active
```

Both `created` and `last-active` get today's date at creation time.

- [ ] **Step 2: Verify the edit reads correctly**

Read the Common Frontmatter section to confirm `last-active` sits between `created` and `status`.

- [ ] **Step 3: Commit**

```bash
git add skills/new-project/SKILL.md
git commit -m "workspace: new-project writes last-active in frontmatter

New projects get last-active: YYYY-MM-DD (same as created) so the
SessionStart hook can order them from day one."
```

---

### Task 4: Teach `close-project` to write `last-active` at close

**Files:**
- Modify: `skills/close-project/SKILL.md`

**Interfaces:**
- Consumes: nothing new
- Produces: `last-active: YYYY-MM-DD` updated in CLAUDE.md frontmatter at close time

- [ ] **Step 1: Add `last-active` to the frontmatter update step**

In `skills/close-project/SKILL.md`, in "Step 3b: Update frontmatter fields" (line 176), after item 2 (which adds `closed: <YYYY-MM-DD>`), add:

```markdown
3. Update `last-active: <YYYY-MM-DD>` to today's date (or add it after
   `closed:` if it doesn't exist).
```

Renumber existing items 3 and 4 to 4 and 5.

- [ ] **Step 2: Verify the edit reads correctly**

Read the Step 3b section to confirm the renumbering is correct.

- [ ] **Step 3: Commit**

```bash
git add skills/close-project/SKILL.md
git commit -m "workspace: close-project updates last-active in frontmatter

Closing a project stamps last-active to today, keeping the
SessionStart hook accurate through the project's full lifecycle."
```

---

### Task 5: Run the full test suite and validate

**Files:**
- Run: `tests/test_recent_projects.py`, `tests/test_setup.sh`, `tests/test_skills.py`, `tests/test_domain_info.py`

**Interfaces:**
- Consumes: all prior tasks
- Produces: clean test run confirming no regressions

- [ ] **Step 1: Run the new test suite**

Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && python3 tests/test_recent_projects.py -v`
Expected: All tests PASS.

- [ ] **Step 2: Run the existing test suites for regressions**

Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && bash tests/test_setup.sh`
Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && python3 tests/test_skills.py -v`
Run: `cd /home/pfontani/Workspace/edge-tooling/plugins/workspace && python3 tests/test_domain_info.py -v`
Expected: All PASS — none of these test files depend on `recent-projects.py` or frontmatter ordering.

- [ ] **Step 3: Spot-check the SKILL.md files for consistency**

Grep across skills for `last-active` to confirm all three skills reference it and nothing else unexpectedly does:

```bash
grep -rn 'last-active' plugins/workspace/skills/
```

Expected: hits in `new-project/SKILL.md`, `update-project/SKILL.md`, `close-project/SKILL.md` only.
