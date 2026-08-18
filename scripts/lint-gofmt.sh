#!/usr/bin/bash
# Check that Go files match gofmt -s. Used by CI via `make lint-gofmt`.
#
# Usage:
#   scripts/lint-gofmt.sh        # check (exit 1 if files need formatting)
#   scripts/lint-gofmt.sh --fix  # rewrite files in place

set -euo pipefail

FIX=false
for _arg in "$@"; do
    case "$_arg" in
        --fix) FIX=true ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v gofmt >/dev/null 2>&1; then
    echo "gofmt not found; install Go (1.21+)." >&2
    exit 1
fi

file_list=$(find . \
    \( -name .git -o -name vendor -o -name two-node-toolbox \) -prune -o \
    -type f -name '*.go' -print) || {
    status=$?
    echo "find failed with status ${status}" >&2
    exit "${status}"
}

files=()
if [ -n "${file_list}" ]; then
    while IFS= read -r f; do
        [ -n "${f}" ] && files+=("${f}")
    done <<< "${file_list}"
fi

if [ "${#files[@]}" -eq 0 ]; then
    echo "No Go files found."
    exit 0
fi

if [ "$FIX" = true ]; then
    gofmt -s -w "${files[@]}"
    echo "gofmt -s applied to ${#files[@]} file(s)."
    exit 0
fi

gofmt_out=$(gofmt -s -l "${files[@]}") || {
    status=$?
    echo "gofmt -s -l failed with status ${status}" >&2
    exit "${status}"
}

unformatted=()
if [ -n "${gofmt_out}" ]; then
    while IFS= read -r f; do
        [ -n "${f}" ] && unformatted+=("${f}")
    done <<< "${gofmt_out}"
fi

if [ "${#unformatted[@]}" -gt 0 ]; then
    echo "The following Go files need gofmt -s:" >&2
    printf '%s\n' "${unformatted[@]}" >&2
    echo >&2
    gofmt -s -d "${unformatted[@]}" >&2
    echo "Run: make lint-fix-gofmt" >&2
    exit 1
fi
