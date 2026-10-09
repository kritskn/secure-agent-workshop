#!/usr/bin/env bash
# Docker readiness entry adapter; no preparation, prompts or retries.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=lab_work.sh
source "${SCRIPT_DIR}/lab_work.sh"
# shellcheck source=check_preparation.sh
source "${SCRIPT_DIR}/check_preparation.sh"

#######################################
# Check selected cached dependencies, private profile and one live request.
# Globals: SCRIPT_DIR and checker handoffs. Arguments: none.
# Outputs: status/recovery. Returns: checker status, 2 bad args.
#######################################
main() {
  if (( $# != 0 )); then
    lab_print '%s\n' '[FAIL] Usage: ./lab.sh check (no arguments)' >&2
    return 2
  fi
  trap 'lab_stop_work' EXIT
  trap 'lab_stop_work; prep_cancelled check; exit 130' INT
  trap 'lab_stop_work; prep_cancelled check; exit 143' TERM
  trap 'lab_stop_work; prep_cancelled check; exit 129' HUP
  check_preparation "${SCRIPT_DIR%/*}"
}
main "$@"
