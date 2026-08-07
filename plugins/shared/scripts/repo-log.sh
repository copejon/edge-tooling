#!/usr/bin/bash
set -euo pipefail

# git log wrapper for analysis agents.
#
# Shared across components via symlinks in each plugin's scripts/ directory.
#
# Usage:
#   repo-log.sh <repo-dir> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--paths p1,p2,...] [--limit N]
#
#   <repo-dir>: a git checkout or worktree (e.g. ${WORKDIR}/src/microshift-release-4.20)
#   --paths:    comma-separated path filters appended after '--'
#   --limit:    maximum number of commits (default 50)
#
# Output: one commit per line: '<short-hash> <date> <subject>'

usage() {
    echo "Usage: $(basename "$0") <repo-dir> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--paths p1,p2,...] [--limit N]" >&2
    exit 1
}

main() {
    local repo_dir=""
    local since=""
    local until=""
    local paths=""
    local limit=50

    while [[ ${#} -gt 0 ]]; do
        case "${1}" in
            --since)
                [[ ${#} -ge 2 ]] || usage
                since="${2}"; shift 2 ;;
            --until)
                [[ ${#} -ge 2 ]] || usage
                until="${2}"; shift 2 ;;
            --paths)
                [[ ${#} -ge 2 ]] || usage
                paths="${2}"; shift 2 ;;
            --limit)
                [[ ${#} -ge 2 ]] || usage
                limit="${2}"; shift 2 ;;
            -h|--help) usage ;;
            -*) echo "Unknown option: ${1}" >&2; usage ;;
            *) repo_dir="${1}"; shift ;;
        esac
    done

    [[ -z "${repo_dir}" ]] && usage

    if ! git -C "${repo_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Error: not a git work tree: ${repo_dir}" >&2
        echo "Hint: run 'doctor-helper.sh prepare ... --repo <org/name>' first to create the source checkout." >&2
        exit 1
    fi

    local -a args=(log --date=short --pretty='%h %ad %s' -n "${limit}")
    [[ -n "${since}" ]] && args+=("--since=${since}")
    [[ -n "${until}" ]] && args+=("--until=${until}")

    if [[ -n "${paths}" ]]; then
        local -a path_args=()
        IFS=',' read -ra path_args <<< "${paths}"
        git -C "${repo_dir}" "${args[@]}" -- "${path_args[@]}"
    else
        git -C "${repo_dir}" "${args[@]}"
    fi
}

main "${@}"
