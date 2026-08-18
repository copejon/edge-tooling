# CI Tooling

Standalone helpers for OpenShift edge CI: Sippy Component Readiness, payload health, and related triage workflows. Each subdirectory is its own tool with a README.

| Tool | Purpose |
|------|---------|
| [readiness-report/](readiness-report/) | Fetch Sippy Component Readiness views for edge topologies and print a triage report |

These tools query public CI APIs (Sippy). They do not deploy clusters. For nightly payload health across SNO/TNA/TNF, see [payload-monitor/](../payload-monitor/).
