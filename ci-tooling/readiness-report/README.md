# Readiness Report

CLI that fetches [Sippy Component Readiness](https://sippy.dptools.openshift.org/sippy-ng/component_readiness/main) views for edge topologies and prints a compact triage report: how many tests are regressed, which are already triaged (with JIRA links), and optionally the untriaged remainder.

Default views compare HA against two-node fencing, two-node arbiter, and single-node. Use this when the Payload Manager or a component owner needs a snapshot of CR status for a release — not the full nightly payload dashboard from [payload-monitor](../../payload-monitor/).

## Prerequisites

- Go 1.21 or later
- Network access to Sippy (default: `https://sippy.dptools.openshift.org`)

No credentials. The Sippy Component Readiness APIs are unauthenticated.

## Quick start

```bash
cd ci-tooling/readiness-report

# Default: OCP 5.0, TSV, HA vs TNF / TNA / SNO
go run ./cmd

# Markdown report with untriaged tests
go run ./cmd -format md -untriaged

# Another release
go run ./cmd -release 4.22 -format html > /tmp/cr-4.22.html
```

## What it does

1. Lists Sippy Component Readiness views from `/api/component_readiness/views`
2. Resolves the requested view suffixes (or full names) against that list for the given release
3. For each matching view, fetches the component report and the triage list
4. Deduplicates regressed tests, counts triaged vs untriaged, and joins nested triage data with JIRA bugs
5. Writes a summary plus a triaged table (and an untriaged table when `-untriaged` is set)

Default view suffixes, prefixed with `<release>-`:

- `ha-vs-two-node-fencing`
- `ha-vs-two-node-arbiter`
- `ha-vs-single`

Missing views are skipped with a warning. If none match, the command exits non-zero.

## CLI reference

```text
go run ./cmd [flags]

  -release string
        Release version to report on (default "5.0")
  -views string
        Comma-separated view suffixes or full view names.
        Default: ha-vs-two-node-fencing,ha-vs-two-node-arbiter,ha-vs-single
  -format string
        Output format: tsv, md, or html (default "tsv")
  -untriaged
        Include a table of untriaged regressed tests
  -list-views
        List Sippy views for the given release and exit
  -base-url string
        Sippy base URL (default "https://sippy.dptools.openshift.org")
```

Examples:

```bash
# Discover views for a release
go run ./cmd -list-views -release 5.0

# A single comparison
go run ./cmd -release 5.0 -views ha-vs-two-node-fencing -format md

# Full Sippy view name (not prefixed again)
go run ./cmd -views 5.0-ha-vs-single
```

## Output

All formats include:

| Section | Columns |
|---------|---------|
| Summary | View, regressed count, untriaged count, triaged count (plus a Sippy view link) |
| Triaged | View, test count, triage type, JIRA, open/resolved, Sippy triage link |
| Untriaged | View, component, status, test name and compact variants (only with `-untriaged`) |

`tsv` is the default (paste into a spreadsheet or Slack). `md` is GitHub-friendly. `html` is a standalone table page.

View names in the tables are shortened (`5.0-ha-vs-two-node-fencing` → `two-node-fencing`).

## Development

```bash
cd ci-tooling/readiness-report
go test ./cmd

# From the repository root: gofmt -s check used in CI
make lint-gofmt
```

Tests are offline: they cover view resolution, triage merging, and count/dedup logic. Live Sippy calls are not mocked in CI.
