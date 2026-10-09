#!/usr/bin/env bash
# Docker preparation entry adapter; lab.sh is the participant entry point.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=lab_work.sh
source "${SCRIPT_DIR}/lab_work.sh"
# shellcheck source=setup_prep.sh
source "${SCRIPT_DIR}/setup_prep.sh"

#######################################
# Run shared Docker preparation, retaining partial work on failure/cancellation.
# Globals: SCRIPT_DIR and coordinator handoffs. Arguments: none.
# Outputs: progress/prompts/recovery. Returns: coordinator status, 2 bad args.
#######################################
main() {
  if (( $# != 0 )); then
    lab_print '%s\n' '[FAIL] Usage: ./lab.sh setup (no arguments)' >&2
    return 2
  fi
  trap 'lab_stop_work' EXIT
  trap 'lab_stop_work; prep_cancelled setup; exit 130' INT
  trap 'lab_stop_work; prep_cancelled setup; exit 143' TERM
  trap 'lab_stop_work; prep_cancelled setup; exit 129' HUP
  setup_prep "${SCRIPT_DIR%/*}"
}
main "$@"
