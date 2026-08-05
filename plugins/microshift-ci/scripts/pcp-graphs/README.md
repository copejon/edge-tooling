# PCP Performance Metrics for MicroShift CI

Extract performance metrics from PCP (Performance Co-Pilot) archives
collected during MicroShift CI job runs. Produces CPU, memory, disk I/O,
and disk usage JSON files that are embedded as interactive Chart.js charts
in the ci-doctor HTML report.

## Background

MicroShift CI jobs collect PCP archives via the `pcp-zeroconf` package
on the test host throughout the run, capturing system-wide performance
metrics at high resolution. This tool processes those archives and
produces time-series graphs at 15-second intervals.

### CPU Usage

Stacked area chart showing **User**, **System**, and **I/O Wait** CPU
usage (0-100%). Useful for identifying CPU saturation and I/O-bound
workloads during test runs.

### Memory Usage

Stacked area chart showing **Used** and **Cached** memory in GB, with
a dashed **Total** line. Useful for detecting memory pressure.

### Disk I/O

Shows **Disk Read OPS**, **Disk Write OPS**, and **Disk Await** (ms).
Disk Await is the average time I/O requests spend waiting to be serviced.
When await rises above ~10 ms, etcd heartbeats can be missed. Reports
the max await across all block devices at each sample point.

### Disk Usage

Per-partition line chart showing fill percentage (0-100%) over time.
Legend includes device name, mount point, capacity, and peak usage.
Useful for detecting disk space exhaustion during image builds and tests.

## PCP Data Location in CI Artifacts

```text
artifacts/<test_name>/openshift-microshift-infra-pmlogs/artifacts/<ci_hostname>/
```

The directory contains files like `yyyymmdd.hh.mm.{0,index,meta}` and a
`Latest` folio file.

## Prerequisites

- `pcp-export-pcp2json` package (provides the `pcp2json` command)
- Python 3

Install:

```bash
sudo dnf install -y pcp-export-pcp2json
```

## Usage

Graphs are generated automatically by `doctor-helper.sh graphs`:

```bash
bash doctor-helper.sh graphs --workdir /tmp/microshift-ci-claude-workdir.YYMMDD
```

This finds all PCP archives in downloaded artifacts and produces JSON
metric files at `${WORKDIR}/graphs/<build_id>/`. The `finalize` step
embeds the JSON data in the HTML report as interactive Chart.js charts.

## Output

| File | Description |
|---|---|
| `cpu.json` | CPU usage: user%, sys%, iowait%, idle% at 15s intervals |
| `mem.json` | Memory usage: used_gb, cached_gb, free_gb, total_gb at 15s intervals |
| `io.json` | Disk I/O: read/write ops/s, iops, await (ms), queue depth at 15s intervals |
| `disk.json` | Disk usage per partition: used_pct%, used_gb at 15s intervals |

## Files

| File | Purpose |
|---|---|
| `generate-graphs.sh` | Orchestrator: finds PCP archives, runs extraction in parallel |
| `extract_cpu.sh` | Runs `pcp2json` for CPU metrics, pipes through `parse_cpu.py` |
| `parse_cpu.py` | Parses pcp2json CPU output (user, sys, iowait, idle), normalizes to percentages |
| `extract_mem.sh` | Runs `pcp2json` for memory metrics, pipes through `parse_mem.py` |
| `parse_mem.py` | Parses pcp2json memory output (used, free, cached, physmem), converts to GB |
| `extract_io.sh` | Runs `pcp2json` for disk metrics, pipes through `parse_pcp.py` |
| `parse_pcp.py` | Parses pcp2json disk output, aggregates per-device (sum read/write, max await) |
| `extract_disk_usage.sh` | Runs `pcp2json` for filesystem metrics, pipes through `parse_disk_usage.py` |
| `parse_disk_usage.py` | Parses pcp2json filesys output, tracks all partitions as usage percentages |
| `pcp-charts.js` | Shared Chart.js rendering functions for CPU/mem/io/disk charts |
| `create-pcp-dashboard.py` | Standalone interactive HTML dashboard from PCP metrics |
| `generate-dashboard.sh` | Per-scenario dashboard generator (handles per-VM PCP tarballs) |
| `plot_*.py` | Legacy matplotlib plotters (no longer called by the pipeline) |

## Adding a New Metric Type

1. Create `extract_<type>.sh` and `parse_<type>.py` (follow existing patterns)
2. Add a block to `generate-graphs.sh` to extract the new metric
3. Add a rendering function to `pcp-charts.js`
4. Update `create-report.py` to load the new JSON file in `_METRIC_FILES`
