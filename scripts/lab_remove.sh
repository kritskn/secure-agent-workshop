#!/usr/bin/env bash
# Confirmed preparation-only Docker removal; keep images and all lab state.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=docker_host.sh
source "${SCRIPT_DIR}/docker_host.sh"
# shellcheck source=prep_reset.sh
source "${SCRIPT_DIR}/prep_reset.sh"
# shellcheck source=prep_recovery.sh
source "${SCRIPT_DIR}/prep_recovery.sh"

#######################################
# Validate Docker, then delegate scoped inventory, consent and removal.
# Globals: SCRIPT_DIR, DOCKER/DOCKER_ARCH. Arguments: none.
# Outputs: warning/confirmation/recovery. Returns: 0 removed/absent, 1 failed
#   or declined, 2 bad args. Preserves cache, labs and VMs; no recreation.
#######################################
main() {
  if (( $# != 0 )); then
    lab_status FAIL 'Usage: ./lab.sh remove (no arguments)'
    return 2
  fi
  if [[ ! -t 0 || ! -t 1 || ! -t 2 ]]; then
    lab_print '%s\n' '[FAIL] Removal requires an interactive terminal.' \
      'Run ./lab.sh remove in a terminal to inspect and confirm its scope.' >&2
    return 1
  fi
  trap 'prep_cancelled remove; exit 130' INT
  trap 'prep_cancelled remove; exit 143' TERM
  trap 'prep_cancelled remove; exit 129' HUP
  if ! check_docker_host; then
    lab_print '%s\n' \
      '' '[SUGGESTED FIX]' \
      '  - Start Docker and check that the selected context is correct.' \
      '  - Run ./lab.sh remove again to review and confirm deletion.' >&2
    return 1
  fi
  if reset_prep_state "$@"; then
    lab_status INFO 'To prepare again, run ./lab.sh setup.'
    return 0
  fi
  lab_print '%s\n' \
    '' '[SUGGESTED FIX]' \
    '  - If you cancelled, no action is needed.' \
    '  - If removal failed, fix the error above before trying again.' \
    '  - Do not force-delete volumes or unrelated containers.' >&2
  return 1
}
main "$@"
