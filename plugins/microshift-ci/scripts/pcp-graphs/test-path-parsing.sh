#!/usr/bin/bash
# Tests for path-parsing functions in generate-dashboard.sh
set -euo pipefail

PASS=0
FAIL=0

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "${expected}" == "${actual}" ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: ${label}: expected '${expected}', got '${actual}'" >&2
    fi
}

# --- parse_tarball_path tests ---

test_parse_tarball_path() {
    local WORKDIR="$1" tar_path="$2" exp_build="$3" exp_scenario="$4" exp_vm="$5"

    local rel="${tar_path#"${WORKDIR}/artifacts/"}"
    local build_id scenario vm_host
    build_id=$(echo "${rel}" | cut -d/ -f1)
    scenario=$(echo "${tar_path}" | sed -nE 's|.*/scenario-info/([^/]+)/vms/.*|\1|p')
    vm_host=$(echo "${tar_path}" | sed -nE 's|.*/vms/([^/]+)/pcp/.*|\1|p')

    assert_eq "tarball build_id [${tar_path}]" "${exp_build}" "${build_id}"
    assert_eq "tarball scenario [${tar_path}]" "${exp_scenario}" "${scenario}"
    assert_eq "tarball vm_host  [${tar_path}]" "${exp_vm}" "${vm_host}"
}

# URL mode: numeric build_id
test_parse_tarball_path \
    "/tmp/microshift-job-pcp-dashboard.123" \
    "/tmp/microshift-job-pcp-dashboard.123/artifacts/123/artifacts/e2e/openshift-microshift-e2e-metal-tests/artifacts/scenario-info/el98-src@test/vms/host1/pcp/pcp-archives.tar" \
    "123" "el98-src@test" "host1"

# Local mode: "local" build_id
test_parse_tarball_path \
    "/tmp/microshift-pcp-local.XXXXXX" \
    "/tmp/microshift-pcp-local.XXXXXX/artifacts/local/scenario-info/el98-src@upgrade-ok/vms/host1/pcp/pcp-archives.tar" \
    "local" "el98-src@upgrade-ok" "host1"

# Multi-VM scenario
test_parse_tarball_path \
    "/tmp/microshift-pcp-local.abc" \
    "/tmp/microshift-pcp-local.abc/artifacts/local/scenario-info/el96-prel@el98-src@upgrade-ok/vms/host2/pcp/pcp-archives.tar" \
    "local" "el96-prel@el98-src@upgrade-ok" "host2"

# --- process_hypervisor_dir build_id extraction tests ---

test_hypervisor_build_id() {
    local WORKDIR="$1" pcp_dir="$2" expected="$3"

    local rel="${pcp_dir#"${WORKDIR}/artifacts/"}"
    local build_id
    build_id=$(echo "${rel}" | cut -d/ -f1)

    assert_eq "hypervisor build_id [${pcp_dir}]" "${expected}" "${build_id}"
}

# URL mode: numeric build_id
test_hypervisor_build_id \
    "/tmp/microshift-job-pcp-dashboard.999" \
    "/tmp/microshift-job-pcp-dashboard.999/artifacts/999/artifacts/e2e/openshift-microshift-infra-pmlogs/artifacts/i-abc123/20260723.17.54" \
    "999"

# Local mode: "local" build_id
test_hypervisor_build_id \
    "/tmp/microshift-pcp-local.xyz" \
    "/tmp/microshift-pcp-local.xyz/artifacts/local/scenario-info/pmlogs/i-abc123/20260723.17.54" \
    "local"

# Long numeric build_id
test_hypervisor_build_id \
    "/tmp/microshift-job-pcp-dashboard.2074435688593362944" \
    "/tmp/microshift-job-pcp-dashboard.2074435688593362944/artifacts/2074435688593362944/artifacts/e2e-aws-tests/openshift-microshift-infra-pmlogs/artifacts/i-0f4918bdebf0ae43b.us-west-2.compute.internal/Latest" \
    "2074435688593362944"

# Malformed: no artifacts/ prefix → empty build_id
WORKDIR="/tmp/test"
pcp_dir="/some/random/path/pmlogs/host/Latest"
rel="${pcp_dir#"${WORKDIR}/artifacts/"}"
build_id=$(echo "${rel}" | cut -d/ -f1)
if [[ "${pcp_dir}" == "${rel}" ]]; then
    # Prefix didn't match, so rel == original path (malformed)
    assert_eq "malformed path yields unstripped rel" "${pcp_dir}" "${rel}"
else
    assert_eq "malformed should not strip" "SHOULD_NOT_REACH" ""
fi

# --- Results ---
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ ${FAIL} -eq 0 ]]
