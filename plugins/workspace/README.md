# workspace — Workspace Manager (Claude Code plugin)

An installable [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview)
plugin for AI-assisted development. It works with a single repo or many —
install it once, then run `/workspace:setup-environment` to scaffold a
workspace with structured project tracking and long-running task management.

**Single-repo** — run setup inside any git checkout to wrap it as a
self-workspace. No cloning, no domains; you get project tracking and
session handoff on top of your existing repo.

**Multi-repo** — declare the repos you need via a **domain** (or a custom
config), and the plugin clones and organizes them, layers per-repo Claude
context on top, and gives you a unified workspace across all of them. Ships
with bundled domains for common scenarios (the included ones target OpenShift
components) — or build your own.

## Install

From inside Claude Code:

```text
/plugin marketplace add openshift-eng/edge-tooling
/plugin install workspace@edge-tooling
```

## Quick Start

```text
/workspace:setup-environment
```

The skill walks you through everything. Inside a git repo it offers to wrap
it as a **single-repo self-workspace** — no cloning needed. Otherwise it
asks **where** to create a multi-repo workspace, lets you pick a **domain**
(or an external one by git URL), clones the repos, distributes context
files, and generates the workspace's root `CLAUDE.md`. Either way, launch
`claude` from the workspace directory for future sessions.

To build a multi-repo workspace from an arbitrary set of repos instead of a
bundled domain, use `/workspace:create-domain`.

## Skills

| Skill | Description |
|-------|-------------|
| `/workspace:setup-environment` | Set up or refresh a workspace — multi-repo from a domain, or a single-repo self-workspace wrapping the current checkout |
| `/workspace:create-domain` | Build a custom multi-repo workspace from arbitrary repos, generating per-repo context collaboratively |
| `/workspace:new-project` | Create a new project workspace for a task (bug, feature, CI, docs, analysis) |
| `/workspace:handoff` | Save session progress to the project docs and arm a handoff for the next `/clear` |
| `/workspace:resume-project` | Resume an existing project workspace — reload its context and continue |
| `/workspace:close-project` | Close a project workspace, mark it done, and clean up its worktrees |
| `/workspace:update-project` | Update project documentation from what was accomplished in this session |
| `/workspace:consolidate-project` | Consolidate a bloated project CLAUDE.md by archiving completed checklist items |
| `/workspace:update-domain` | Feed lessons learned from a project back into its domain — context files, supplemental CLAUDE.md, and reference docs |
| `/workspace:auto-update` | Start a 5-minute loop that keeps project docs updated during idle |

A SessionStart hook surfaces your recent projects whenever you launch Claude
Code inside a workspace (it stays silent elsewhere). After
`/workspace:handoff`, that same hook instead resumes the handed-off
project on your next `/clear`.

## Concepts

- **Plugin root** — where the plugin ships (read-only). You never edit here.
- **Workspace root** — the directory you choose during setup (or the repo
  root in a self-workspace). Always contains `dev-env.yaml` and `projects/`.
  Multi-repo workspaces also have `repos/` and workspace-local `domains/`.
- **Domain** (multi-repo only) — a reusable config: a `dev-env.yaml` repo
  list plus optional per-repo context, supplemental CLAUDE.md files, and
  docs.

### Domains

- **Bundled** — ship with the plugin (`tnf`, `lvm-operator`, `example`).
- **External** — installed from a git URL into your workspace's `domains/`:
  `/workspace:setup-environment` → "External domain (git URL)". A URL may
  include a `#subdir` fragment for packs holding multiple domains.
- **Authoring** — a domain is a directory with `domain.yaml` (name +
  description), `dev-env.yaml` (repos), and optional `context/<repo>.md`,
  `supplemental/<repo>.md`, `docs/`, and `settings.local.json.tpl`. Workspace
  domains shadow bundled ones of the same name.

## dev-env.yaml

Generated in your workspace by the setup skills. The schema depends on the
workspace mode.

**Single-repo (self-workspace):**

```yaml
self:
  name: my-repo            # workspace name (usually the repo basename)
  summary: "Brief description of the repo"

repos: []                  # no external repos to clone
```

**Multi-repo (domain workspace):**

```yaml
domain:                    # auto-recorded by setup; enables refresh-domain
  name: <domain-name>
  source: bundled          # 'bundled' or the external git URL
  # ref / subdir            # (external only)

repos:
  - name: my-repo          # identifier and directory name under repos/
    url: https://github.com/org/my-repo.git
    branch: main
    category: development  # docs | development | testing | deployment | troubleshooting
    summary: "Brief description of the repo's role"
    directory: my-repo     # (optional) overrides the directory name
```

Multi-repo workspaces clone with `--filter=blob:none` (blobless): full
structure visible, blob contents fetched on demand.

## Requirements

- Git (2.27+ for blobless clones)
- Python 3.9+ with **PyYAML** (`pip3 install pyyaml`), *or* `yq` — needed to
  parse `dev-env.yaml`/project frontmatter. The project tooling reports a clear
  message if PyYAML is missing.
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview)

## Upgrading from the pre-plugin version

Earlier versions were cloned-and-run and installed a SessionStart hook into
your workspace's `.claude/settings.local.json`. The hook now ships with the
plugin, so **remove the stale `hooks` block** from that file to avoid a
duplicate/failing hook:

```jsonc
// delete this block from .claude/settings.local.json
"hooks": {
  "SessionStart": [ { "hooks": [ { "type": "command",
    "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/recent-projects.py" } ] } ]
}
```

The old `/dev-env-setup` and `/project:*` commands are replaced by the
`/workspace:*` skills above.

## Developing the plugin

See [CLAUDE.md](CLAUDE.md) for the layout, dev loop
(`claude --plugin-dir .` + `/reload-plugins`), and test command
(`bash tests/test_setup.sh`).
