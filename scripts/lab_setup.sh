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
# Globals: SCRIPT_DIR and handoffs. Arguments: --build-only [--no-cache].
# Outputs: progress/prompts/recovery. Returns: coordinator status, 2 bad args.
#######################################
main() {
  if ! [[ $# -eq 0 || ( "${1:-}" == --build-only \
    && ( $# -eq 1 || ( $# -eq 2 && "$2" == --no-cache ) ) ) ]]; then
    lab_status FAIL 'Usage: ./lab.sh setup [--build-only [--no-cache]]'
    return 2
  fi
  trap 'lab_stop_work' EXIT
  trap 'lab_stop_work; prep_cancelled setup; exit 130' INT
  trap 'lab_stop_work; prep_cancelled setup; exit 143' TERM
  trap 'lab_stop_work; prep_cancelled setup; exit 129' HUP
  setup_prep "${SCRIPT_DIR%/*}" "$@"
}
main "$@"
