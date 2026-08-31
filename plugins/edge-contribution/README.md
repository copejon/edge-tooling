# edge-contribution

Cross-workstream contribution reporting for the OpenShift Edge team. Answers two
questions for a quarter or date range from the same underlying data:

- **IC (`breadth` skill):** which of the six workstreams did an engineer touch,
  what did they do in each, and what is their breadth "N of 6"?
- **Manager (`heatmap` skill):** a people×workstream heatmap (a distinct color per
  contributor) plus two team scores — **Flexibility** and **Opportunity**.

The six workstreams are **SNO, TNA, TNF, LVMS, USHIFT, TOPO**. Activity is drawn
from Jira (OCPEDGE assignee/QA-contact/comments, OCPSTRAT roles) and GitHub
(authored + reviewed PRs), and each item is attributed to a workstream via its
Jira component.

## Install

```text
/plugin marketplace add openshift-eng/edge-tooling
/plugin install edge-contribution
```

## Prerequisites

- **Jira credentials:** export `JIRA_USERNAME` and `JIRA_API_TOKEN` (the same
  credentials the Atlassian MCP uses). The collectors call
  `redhat.atlassian.net` REST directly — no MCP at runtime.
- **GitHub CLI:** `gh` installed and authenticated (`gh auth status`).
- **Python 3.9+** with `requests` available.
- **edge-context checkout** for the roster — set `$EDGE_CONTEXT_DIR`, keep a
  sibling `../edge-context`, or let the skill `gh repo clone` it.

## Usage

Invoke the skills from Claude Code:

```text
/edge-contribution:breadth --quarter 2026Q2
/edge-contribution:breadth --member jdoe@redhat.com --from 2026-04-01 --to 2026-06-30 --format html
/edge-contribution:heatmap --quarter 2026Q2 --format html
```

`breadth` defaults to `$JIRA_USERNAME`; `heatmap` covers the full Eng/QE roster.
Both accept `--format html|text|csv` (breadth defaults to `text`, heatmap to
`html`).

### Running the pipeline directly

The skills orchestrate four standalone scripts under `bin/`. You can run them by
hand:

```bash
# 1. roster (Eng/QE only) from edge-context
python3 bin/load_context.py --edge-context ../edge-context --output roster.json

# 2. collect activity for the window
python3 bin/collect_jira.py   --members-file roster.json --quarter 2026Q2 \
  --output jira_activity.json
python3 bin/collect_github.py --members-file roster.json --quarter 2026Q2 \
  --output github_activity.json

# 3. render a report
python3 bin/report.py --view manager --members-file roster.json \
  --activity jira_activity.json --activity github_activity.json \
  --period 2026Q2 --format html --output heatmap.html

python3 bin/report.py --view ic --member jdoe@redhat.com \
  --activity jira_activity.json --activity github_activity.json \
  --period 2026Q2 --format text
```

## Metrics

Defined precisely in [`references/metrics.md`](references/metrics.md). In short,
from a binary "did member *m* contribute to workstream *w*?" matrix:

- **Breadth** (per member) = distinct workstreams touched, "of 6".
- **Flexibility** (per workstream) = distinct contributors; team mean =
  `total_ones / 6`.
- **Opportunity** (per member) = breadth; team mean over *active* members =
  `total_ones / active_count`, shown with the active/total roster count.

Items whose Jira component maps to no workstream (or to `Planning`) are reported
as **unattributed** — counted separately, never silently dropped.

## Architecture

```text
workstream_map.py   internal SNO/TNA/TNF/LVMS/USHIFT/TOPO ↔ Jira component map
load_context.py     edge-context people/team-roster.md → roster.json (Eng/QE)
collect_jira.py     Jira REST → jira_activity.json      (assignee/QA/comment/ocpstrat)
collect_github.py   gh CLI    → github_activity.json    (pr_authored/pr_reviewed)
report.py           activity + roster → contribution matrix → metrics → render
metrics.py          matrix → breadth / flexibility / opportunity
render.py           report → html | text | csv
_common.py          Jira config/auth, HTTP client (pagination/retry), date helpers
```

`workstream_map`, `load_context`, `metrics`, `render`, and `report` are pure and
side-effect-free; all Jira/GitHub/filesystem I/O is isolated in the collectors
and `_common.py`, with the HTTP and `gh` layers injected so tests stay hermetic.

## Development

Built test-first (TDD). Run the suite:

```bash
python3 -m pytest plugins/edge-contribution/bin/tests
```

Optional style/type gate (see `requirements-dev.txt`):

```bash
black --check bin && ruff check bin && mypy bin
```

Every module has happy-path, failure, and edge/boundary tests. See the plan and
`references/` for the design rationale and the workstream/component map.
