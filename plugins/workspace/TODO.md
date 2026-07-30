# Workspace Plugin — Post-Migration Cleanup

Findings from CodeRabbit review on PR #249 that are worth addressing.

## Low

- **`scripts/setup.sh:1`, `tests/test_setup.sh:1` — shebang alignment**
  Use `#!/usr/bin/bash` to match repo standard (CONTRIBUTING.md).

- **`scripts/resume-project.py:308,345` — rename `l` variable (ruff E741)**
  Rename to `ln` in both list comprehensions.

- **Skill frontmatter normalization (all 8 skills)** — add `allowed-tools`,
  use `workspace:` namespaced names, make descriptions action-triggered
  ("Use when…") per SKILL-GUIDELINES.md.
