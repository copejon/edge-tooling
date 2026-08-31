---
name: edge-contribution:heatmap
description: Show the whole OCP-Edge Eng/QE team's cross-workstream contribution as a people×workstream heatmap (a distinct color per contributor) plus two team scores — Flexibility (distinct contributors per workstream) and Opportunity (workstreams touched per active member) — for a quarter or date range.
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
user-invocable: true
---

# Manager Team Heatmap

Report how the OCP-Edge Eng/QE team spread across the six workstreams (SNO, TNA,
TNF, LVMS, USHIFT, TOPO) in a reporting period. Output is a people×workstream
**heatmap** where each contributor has a distinct color (color encodes the
person, not intensity), plus two scores derived from the binary "did they
contribute?" matrix:

- **Flexibility** — per workstream, the number of distinct contributors; team
  scalar is the mean over all 6 workstreams.
- **Opportunity** — per member, the number of workstreams touched; team scalar is
  the mean over *active* members, reported with the active/total roster count.

## Prerequisites

- `JIRA_USERNAME` and `JIRA_API_TOKEN` exported (same credentials the Atlassian
  MCP uses). The collectors hit `redhat.atlassian.net` REST directly.
- `gh` authenticated (`gh auth status`) for PR collection.
- Python 3.9+ with `requests` available.

## Arguments

- `--quarter <YYYYQn>` — e.g. `2026Q2`. Or use an explicit range:
- `--from <YYYY-MM-DD> --to <YYYY-MM-DD>`.
- `--format <html|text|csv>` — defaults to `html` (the heatmap is most legible
  graphically).

If neither `--quarter` nor a `--from/--to` pair is given, ask the user which
period to report on with AskUserQuestion.

## Steps

`PLUGIN_ROOT` is `${CLAUDE_PLUGIN_ROOT}` (this plugin's directory).

1. **Resolve the period.** `PERIOD` = the `--quarter` value or `<from>_<to>`
   (used for labels and the workdir name). `<PERIOD-FLAGS>` = `--quarter $QUARTER`
   or `--from $FROM --to $TO`, passed to both collectors.

2. **Resolve edge-context** (for the roster):
   - If `$EDGE_CONTEXT_DIR` is set and exists, use it.
   - Else if `../edge-context` exists (sibling checkout), use it.
   - Else `gh repo clone openshift-eng/edge-context "$WORKDIR/edge-context"` and
     use that.

3. **Set up the workdir:**

   ```bash
   WORKDIR="/tmp/edge-contribution-$PERIOD"
   mkdir -p "$WORKDIR"
   ```

4. **Load the full Eng/QE roster:**

   ```bash
   python3 "$PLUGIN_ROOT/bin/load_context.py" --edge-context "$EDGE_CONTEXT_DIR" \
     --output "$WORKDIR/roster.json"
   ```

5. **Collect activity** (Jira + GitHub) for the whole roster:

   ```bash
   python3 "$PLUGIN_ROOT/bin/collect_jira.py"   --members-file "$WORKDIR/roster.json" \
     <PERIOD-FLAGS> --output "$WORKDIR/jira_activity.json"
   python3 "$PLUGIN_ROOT/bin/collect_github.py" --members-file "$WORKDIR/roster.json" \
     <PERIOD-FLAGS> --output "$WORKDIR/github_activity.json"
   ```

   This is the long-running step (one set of queries per member); let it finish.

6. **Render the heatmap + scores:**

   ```bash
   python3 "$PLUGIN_ROOT/bin/report.py" --view manager \
     --members-file "$WORKDIR/roster.json" \
     --activity "$WORKDIR/jira_activity.json" \
     --activity "$WORKDIR/github_activity.json" \
     --period "$PERIOD" --format "$FORMAT" \
     --output "$WORKDIR/heatmap-$PERIOD.$FORMAT"
   ```

7. **Present the result.** For `html`, report the file path
   (`$WORKDIR/heatmap-$PERIOD.$FORMAT`) so the user can open it in a browser, and
   summarize team Flexibility, team Opportunity (with active/total), and any
   standout per-workstream gaps. For `text`, show the grid inline. Report the
   unattributed count as a footnote — those items are excluded from the matrix.

## Notes

- The matrix is binary: a cell is filled if the member has ≥1 attributed item in
  that workstream during the period.
- Flexibility team mean = total contributions / 6. Opportunity team mean = total
  contributions / active members (members with ≥1 contribution).
- The canonical six workstreams and their Jira component aliases live in
  `bin/workstream_map.py`.
