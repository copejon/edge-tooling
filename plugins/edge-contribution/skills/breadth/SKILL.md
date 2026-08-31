---
name: edge-contribution:breadth
description: Show one engineer's cross-workstream contribution breadth for a quarter or date range — which of the 6 OCP-Edge workstreams they touched, a per-workstream activity breakdown (assignee/QA/comments/PRs/reviews), and their breadth count "N of 6". Defaults to the current user ($JIRA_USERNAME).
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
user-invocable: true
---

# IC Contribution Breadth

Report how broadly a single engineer contributed across the six OCP-Edge
workstreams (SNO, TNA, TNF, LVMS, USHIFT, TOPO) in a reporting period. Output is
a summarized list of workstreams contributed to, a per-workstream activity
breakdown, and the breadth count **N of 6**.

## Prerequisites

- `JIRA_USERNAME` and `JIRA_API_TOKEN` exported (same credentials the Atlassian
  MCP uses). The collectors hit `redhat.atlassian.net` REST directly.
- `gh` authenticated (`gh auth status`) for PR collection.
- Python 3.9+ with `requests` available.

## Arguments

- `--member <jira-username>` — who to report on. Defaults to `$JIRA_USERNAME`.
- `--quarter <YYYYQn>` — e.g. `2026Q2`. Or use an explicit range:
- `--from <YYYY-MM-DD> --to <YYYY-MM-DD>`.
- `--format <html|text|csv>` — defaults to `text`.

If neither `--quarter` nor a `--from/--to` pair is given, ask the user which
period to report on with AskUserQuestion.

## Steps

`PLUGIN_ROOT` is `${CLAUDE_PLUGIN_ROOT}` (this plugin's directory). Run all
commands from a fresh working directory.

1. **Resolve inputs.**
   - `MEMBER` = `--member` value, else `$JIRA_USERNAME`.
   - `PERIOD` = the `--quarter` value, or `<from>_<to>`; used only for labels and
     the workdir name.
   - Pass the period to the collectors as either `--quarter` or `--from/--to`
     exactly as the user supplied it.

2. **Resolve edge-context** (for the roster / GitHub handle):
   - If `$EDGE_CONTEXT_DIR` is set and exists, use it.
   - Else if `../edge-context` exists (sibling checkout), use it.
   - Else `gh repo clone openshift-eng/edge-context "$WORKDIR/edge-context"` and
     use that.

3. **Set up the workdir:**

   ```bash
   WORKDIR="/tmp/edge-contribution-$PERIOD"
   mkdir -p "$WORKDIR"
   ```

4. **Load the roster** and reduce it to the target member:

   ```bash
   python3 "$PLUGIN_ROOT/bin/load_context.py" --edge-context "$EDGE_CONTEXT_DIR" \
     --output "$WORKDIR/roster.json"
   ```

   Filter to just `MEMBER` (match on `jira_username`) into
   `"$WORKDIR/member.json"` — e.g. with `jq`:

   ```bash
   jq --arg m "$MEMBER" '[.[] | select(.jira_username == $m)]' \
     "$WORKDIR/roster.json" > "$WORKDIR/member.json"
   ```

   If `member.json` is empty, tell the user the member isn't in the Eng/QE
   roster and stop.

5. **Collect activity** (Jira + GitHub), scoped to the one member:

   ```bash
   python3 "$PLUGIN_ROOT/bin/collect_jira.py"   --members "$MEMBER" \
     <PERIOD-FLAGS> --output "$WORKDIR/jira_activity.json"
   python3 "$PLUGIN_ROOT/bin/collect_github.py" --members-file "$WORKDIR/member.json" \
     <PERIOD-FLAGS> --output "$WORKDIR/github_activity.json"
   ```

   where `<PERIOD-FLAGS>` is `--quarter $QUARTER` or `--from $FROM --to $TO`.

6. **Render the report:**

   ```bash
   python3 "$PLUGIN_ROOT/bin/report.py" --view ic --member "$MEMBER" \
     --activity "$WORKDIR/jira_activity.json" \
     --activity "$WORKDIR/github_activity.json" \
     --period "$PERIOD" --format "$FORMAT" \
     --output "$WORKDIR/breadth-$MEMBER.$FORMAT"
   ```

7. **Present the result.** For `text`, show it inline. For `html`/`csv`, report
   the file path (`$WORKDIR/breadth-$MEMBER.$FORMAT`) and summarize the breadth
   count and touched workstreams. Note any unattributed items as a caveat.

## Notes

- Breadth is always "of 6" — the six workstreams are the canonical set in
  `bin/workstream_map.py`.
- Items whose Jira component maps to no workstream (or to `Planning`) are
  reported as unattributed, never silently dropped.
