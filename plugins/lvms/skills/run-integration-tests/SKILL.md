---
name: lvms:run-integration-tests
argument-hint: "[JIRA-ID]"
description: Run LVMS QE integration tests on a TNF cluster via SSH — deploys operator from source, runs tests, parses results, posts to JIRA. Use for RC/EC builds where OLM catalog is unavailable.
user-invocable: true
allowed-tools: Bash, Read, AskUserQuestion, mcp__mcp-atlassian__jira_add_comment
---

# lvms:run-integration-tests

## Synopsis

```bash
/lvms:run-integration-tests
/lvms:run-integration-tests OCPEDGE-1995
```

## Description

Automates the full LVMS QE integration test pipeline on a TNF cluster. Designed for RC/EC builds
where the `redhat-operators` catalog does not include the `lvms-operator` package. For released
builds, use `/lvms:setup-prereq` instead.

The skill is **re-entrant**: invoke it once to start the run, then invoke it again when tests
complete to collect results. State is detected automatically from the hypervisor.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| TNF cluster | Fresh cluster with extra disks (`VM_EXTRADISKS_LIST="vda vdb vdc"`) |
| SSH access | Hypervisor reachable by SSH with `oc` CLI and cluster-admin kubeconfig |
| Go 1.24+ | Installed on the hypervisor (for building the test binary) |

## Implementation

### Step 1: Gather Inputs

Parse `$ARGUMENTS` for an optional JIRA ticket ID (e.g. `OCPEDGE-1995`).

Ask for the hypervisor SSH host:

```text
Hypervisor SSH host? (e.g. ec2-user@<IP>)
```

Set:

```text
SSH_HOST = user input or default
KUBECONFIG = /home/ec2-user/openshift-metal3/dev-scripts/ocp/ostest/auth/kubeconfig
```

### Step 2: Detect State

Check process and log state on the hypervisor to decide which phase to enter:

```bash
ssh "$SSH_HOST" '
  ps aux | grep "[i]ntegration-test run-suite" | grep -q . && echo RUNNING
  ls ~/lvms-mno.log ~/lvms-sno.log 2>/dev/null | head -1
' 2>/dev/null
```

| Result | Phase |
|--------|-------|
| Output contains `RUNNING` | → Phase 2: Tests In Progress |
| Output contains a log path (no RUNNING) | → Phase 3: Results Ready |
| No output | → Phase 1: Fresh Run |

---

## Phase 1: Fresh Run

### Step 1a: Ask for suite

```text
Which test suite?
- mno: Multi-Node OpenShift (36 tests) — use for TNF clusters
- sno: Single-Node OpenShift (30 tests) — use for SNO clusters
- both: Run MNO then SNO sequentially (~3-4 hours)
```

Default to `mno` for TNF topology.

### Step 1b: Check existing LVMS deployment

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; \
  oc get deployment/lvms-operator -n openshift-lvm-storage 2>/dev/null"
```

- **Found**: Ask: "LVMS already deployed. Redeploy from source or skip to test run?"
  - Redeploy: `ssh "$SSH_HOST" "cd ~/lvm-operator && make undeploy"` then continue
  - Skip: jump to Step 1d
- **Not found**: Continue

### Step 1c: Deploy LVMS from source

Patch image registry to Managed (some tests need it):

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; \
  oc patch configs.imageregistry.operator.openshift.io cluster \
  --type merge --patch '{\"spec\":{\"managementState\":\"Managed\",\"storage\":{\"emptyDir\":{}}}}'"
```

Clone or update lvm-operator:

```bash
ssh "$SSH_HOST" '
  if [ -d ~/lvm-operator ]; then
    cd ~/lvm-operator && git fetch origin && git checkout main && git pull origin main
  else
    git clone https://github.com/openshift/lvm-operator.git ~/lvm-operator
  fi
  echo "Commit: $(cd ~/lvm-operator && git rev-parse --short HEAD)"
'
```

Deploy (creates namespace, CRDs, RBAC, operator via kustomize — no image build required):

```bash
ssh "$SSH_HOST" "cd ~/lvm-operator && make deploy"
```

Wait for operator:

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; \
  oc -n openshift-lvm-storage wait deployment/lvms-operator \
  --for=condition=Available --timeout=120s"
```

Apply LVMCluster CR (required for CSI driver registration):

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; \
  oc apply -n openshift-lvm-storage \
  -f ~/lvm-operator/config/samples/lvm_v1alpha1_lvmcluster.yaml"
```

Wait for Ready (poll every 10s, timeout 3m):

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; \
  for i in \$(seq 1 18); do
    STATE=\$(oc -n openshift-lvm-storage get lvmcluster my-lvmcluster \
      -o jsonpath='{.status.state}' 2>/dev/null)
    echo \"[\$i] \$STATE\"
    [ \"\$STATE\" = \"Ready\" ] && break
    sleep 10
  done"
```

Verify CSI driver — if `topolvm.io` is not listed, stop immediately:

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; oc get csidrivers | grep topolvm"
```

**CRITICAL:** If `topolvm.io` is absent, stop and report:
> CSI driver `topolvm.io` not registered. Check vg-manager logs:
> `oc logs -n openshift-lvm-storage -l app.kubernetes.io/name=vg-manager`
> Do not start tests — all cases will silently skip.

### Step 1d: Build test binary and start tests

```bash
ssh "$SSH_HOST" "cd ~/lvm-operator/test/integration && make integration-build"
```

Remove stale logs, then start the run with `nohup`:

```bash
# For mno:
ssh "$SSH_HOST" '
  rm -f ~/lvms-mno.log
  cd ~/lvm-operator/test/integration
  nohup bash -c "./integration-test run-suite -c 1 \
    openshift/lvm-operator/test/integration/qe_tests/mno > ~/lvms-mno.log 2>&1" &
  echo "PID: $!"
'

# For sno:
ssh "$SSH_HOST" '
  rm -f ~/lvms-sno.log
  cd ~/lvm-operator/test/integration
  nohup bash -c "./integration-test run-suite -c 1 \
    openshift/lvm-operator/test/integration/qe_tests/sno > ~/lvms-sno.log 2>&1" &
  echo "PID: $!"
'

# For both (sequential):
ssh "$SSH_HOST" '
  rm -f ~/lvms-mno.log ~/lvms-sno.log
  cd ~/lvm-operator/test/integration
  nohup bash -c "
    ./integration-test run-suite -c 1 \
      openshift/lvm-operator/test/integration/qe_tests/mno > ~/lvms-mno.log 2>&1
    ./integration-test run-suite -c 1 \
      openshift/lvm-operator/test/integration/qe_tests/sno > ~/lvms-sno.log 2>&1
  " &
  echo "PID: $!"
'
```

### Step 1e: Exit with monitoring instructions

```text
Tests started on <SSH_HOST> (PID above). Suite: <SUITE> — ~1-2 hours per suite.

The OTE framework buffers output per-test, so the log stays empty while tests run.

Monitor:
  ssh <SSH_HOST> 'ps aux | grep integration-test'
  ssh <SSH_HOST> 'tail -f ~/lvms-<suite>.log'

When complete, re-invoke:
  /lvms:run-integration-tests
```

**Stop here.** Do not proceed to Phase 2 or 3 in the same invocation.

---

## Phase 2: Tests In Progress

Count completed tests from the partial log:

```bash
ssh "$SSH_HOST" "python3 -c \"
import json, sys, os
try:
  raw = open(os.path.expanduser('~/lvms-mno.log')).read()
  # partial JSON — count result fields
  passed = raw.count('\"result\": \"passed\"')
  failed = raw.count('\"result\": \"failed\"')
  print(f'passed: {passed}, failed: {failed}')
except FileNotFoundError: print('log not yet written')
\" 2>/dev/null || echo 'log not yet written'"
```

Report to the user:

```text
Tests still running on <SSH_HOST>.
Progress: X passed, Y failed so far.

Monitor: ssh <SSH_HOST> 'tail -f ~/lvms-<suite>.log'

Re-invoke /lvms:run-integration-tests when complete.
```

**Stop here.**

---

## Phase 3: Results Ready

### Step 3a: Determine which logs exist

```bash
ssh "$SSH_HOST" "ls ~/lvms-mno.log ~/lvms-sno.log 2>/dev/null"
```

### Step 3b: Parse each log

For each log file, use Python to parse the OTE JSON output (the log is a JSON array with a trailing
`Error: N tests failed` line):

```bash
ssh "$SSH_HOST" "python3 -c \"
import json, re, os
raw = open(os.path.expanduser('~/lvms-<suite>.log')).read()
data = json.loads(raw[:raw.rfind(']')+1])
passed = [t for t in data if t['result'] == 'passed']
failed = [t for t in data if t['result'] == 'failed']
print(f'TOTAL:{len(data)} PASSED:{len(passed)} FAILED:{len(failed)}')
for t in failed:
    m = re.search(r'-(\d{5,})-', t['name'])
    tid = f'OCP-{m.group(1)}' if m else 'unknown'
    print(f'FAIL|{tid}|{t[\"name\"][:80]}|{t.get(\"output\",\"\").strip().splitlines()[-1][:120]}')
\""
```

### Step 3c: Get cluster version

```bash
ssh "$SSH_HOST" "export KUBECONFIG=$KUBECONFIG; oc version --short 2>/dev/null || oc version"
```

### Step 3d: Generate Markdown report

Known flakes (flag but do not count as failures):

| Test ID | Known Issue |
|---------|-------------|
| OCP-86156 | `pvmove` fails with `No data to move` — VG state sensitivity between tests |
| OCP-71012 | ForceWipe — virtio partition naming on libvirt VMs |
| OCP-69772 | RAID test picks `/dev/sr0` (virtual CD-ROM) |

Report format:

```markdown
### LVMS Integration Test Results

**OCP Version:** <from oc version>
**lvm-operator:** main @ <commit>
**Suite:** <mno|sno|both>
**Date:** <YYYY-MM-DD>

#### Summary

| Suite | Passed | Failed | Total | Pass Rate |
|-------|--------|--------|-------|-----------|
| MNO   | X      | Y      | Z     | XX.X%     |

#### Failures

| Test ID | Test Name | Failure Reason | Known Flake? |
|---------|-----------|----------------|--------------|

#### Conclusion
**PASS** / **BLOCKED** — <one-line summary>
```

Use **PASS** if pass rate ≥ 90% and no unexpected failures. Use **BLOCKED** otherwise.

### Step 3e: Post to JIRA

If a JIRA ticket was provided (from `$ARGUMENTS`), ask before posting:

```text
Post results to <JIRA-ID>? (yes/no)
```

If yes, post using the `mcp__mcp-atlassian__jira_add_comment` MCP tool.

### Step 3f: Offer log cleanup

Ask: "Remove log files from the hypervisor? (yes/no)"

If yes:

```bash
ssh "$SSH_HOST" "rm -f ~/lvms-mno.log ~/lvms-sno.log"
```

## Error Handling

| Error | Action |
|-------|--------|
| SSH connection refused | Hypervisor down — start it and retry |
| Go not found | Install Go 1.24+ on the hypervisor |
| `make deploy` fails | Check `oc get events -n openshift-lvm-storage` |
| LVMCluster not Ready after 3m | Check `oc describe lvmcluster -n openshift-lvm-storage` |
| `topolvm.io` CSI driver missing | Check vg-manager logs: `oc logs -n openshift-lvm-storage -l app.kubernetes.io/name=vg-manager` |
| `make integration-build` fails | Verify Go version — must be 1.24+ |
| Log empty after process exits | SSH disconnect killed the run — restart with nohup |
| JIRA post fails | Display report for manual copy |

## Notes

- **`-c 1` is mandatory** — Serial/Disruptive tests modify the LVMCluster CR; higher concurrency causes interference
- **`nohup` is mandatory** — SSH disconnect kills the run otherwise
- **Run from the hypervisor only** — test binary resolves cluster-internal DNS
- **OTE log buffering** — log stays empty until each test completes; monitor via `ps aux`
- **Free disks required** — check worker nodes with `lsblk`; disks with partitions/filesystems are skipped
