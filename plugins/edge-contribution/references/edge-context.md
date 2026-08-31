# edge-context inputs

The plugin reads its **roster** from the `openshift-eng/edge-context` repo. The
**workstream→Jira-component map is internal** to the plugin
(`bin/workstream_map.py`), so the plugin is not blocked on any edge-context PR.

## Locating the checkout

The skills resolve edge-context in this order:

1. `$EDGE_CONTEXT_DIR`, if set and it exists.
2. `../edge-context`, a sibling checkout next to `edge-tooling`.
3. Otherwise `gh repo clone openshift-eng/edge-context` into the workdir.

## Roster: `people/team-roster.md`

A GitHub-flavored markdown pipe table. `load_context.py` parses these columns:

| Column   | Used for                                                        |
|----------|-----------------------------------------------------------------|
| Name     | `name`, and the Rover profile link that yields `kerberos`       |
| GitHub   | `github` handle (used by the GitHub PR collector)               |
| Role     | the Eng/QE filter (see below)                                   |
| Location | ignored                                                         |

Derived identity:

- `kerberos` comes from the Rover profile URL in the Name cell
  (`…/people/profile/<kerberos>`).
- `jira_username = <kerberos>@redhat.com`.

### Eng/QE filter

Only engineers and quality engineers are included. A member is kept when their
role (lower-cased) contains **"software engineer"** or **"software quality
engineer"**. This deliberately includes titles like "Associate Software
Engineer" and "Senior Software Quality Engineer", and excludes
"Manager, Engineering", "Project Manager - Technical", and
"Principal Product Security Engineer" (they contain "Engineer"/"Engineering" but
not the qualifying phrase). See `bin/tests/test_load_context.py`.

## Workstreams (internal, not parsed from edge-context)

The six workstreams and their Jira component aliases are the canonical constant in
`bin/workstream_map.py`:

| Workstream | Jira component(s)                          |
|------------|--------------------------------------------|
| SNO        | `SNO`                                       |
| TNA        | `Two Node with Arbiter`                     |
| TNF        | `TNF`, `Two Node Fencing`                   |
| LVMS       | `Logical Volume Manager Storage`            |
| USHIFT     | `MicroShift`                                |
| TOPO       | `Topology Transitions`, `Mutable Topology`  |
| _(excluded)_ | `Planning` — cutline epics, not a workstream |

Keeping this map in code (rather than parsing `about/workstreams.md`) is a
deliberate decision so development isn't gated on doc-repo review. Mirroring the
map into edge-context docs is a non-blocking follow-up; if the two ever diverge,
`bin/workstream_map.py` is the source of truth at runtime.
