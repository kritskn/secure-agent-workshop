#!/usr/bin/env bash
# Confirmed workshop removal, or image-only removal via --prep-images.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=docker_host.sh
source "${SCRIPT_DIR}/docker_host.sh"
# shellcheck source=prep_recovery.sh
source "${SCRIPT_DIR}/prep_recovery.sh"

#######################################
# Validate Docker, then delegate scoped inventory, consent and removal.
# Globals: SCRIPT_DIR, DOCKER/DOCKER_ARCH, LAB_ARGS, LAB_VERBOSE.
# Arguments: --prep-images or --release-reservations, verbosity, or --help.
# Outputs: inventory/consent/status. Returns: exact removal status, 2 bad args.
# Normal Docker config; no automatic stop, recreation, force or global prune.
#######################################
main() {
  lab_output_options remove "$@" || return
  set -- "${LAB_ARGS[@]}"
  shift
  if (( $# == 1 )) && [[ "$1" == --help ]]; then
    exec "${BASH}" "${SCRIPT_DIR}/lab_help.sh" remove
  fi
  local command='./lab.sh remove'
  if ! [[ $# -eq 0 || ( $# -eq 1 &&
    ( "$1" == --prep-images || "$1" == --release-reservations ) ) ]]; then
    lab_status FAIL 'Use remove [--prep-images|--release-reservations] [-v]'
    return 2
  fi
  if (( $# == 1 )); then command+=" $1"; fi
  if [[ ! -t 0 || ! -t 1 || ! -t 2 ]]; then
    lab_print '%s\n' '[FAIL] Removal requires an interactive terminal.' \
      "Run ${command} in a terminal to inspect and confirm its scope." >&2
    return 1
  fi
  trap 'prep_cancelled remove; exit 130' INT
  trap 'prep_cancelled remove; exit 143' TERM
  trap 'prep_cancelled remove; exit 129' HUP
  if ! check_docker_host; then
    lab_print '%s\n' \
      '' '[SUGGESTED FIX]' \
      '  - Start Docker and check that the selected context is correct.' \
      "  - Run ${command} again to review and confirm deletion." >&2
    return 1
  fi
  if [[ "${1:-}" == --prep-images ]]; then
    # shellcheck source=prep_images_remove.sh
    source "${SCRIPT_DIR}/prep_images_remove.sh"
    shift
    remove_prep_images "${LAB_VERBOSE}"
    return $?
  fi
  if ! command -v python3 >/dev/null 2>&1 \
    || ! python3 -I -B -c \
      'import sys; sys.exit(sys.version_info < (3, 9))'; then
    lab_status FAIL 'Python 3.9 or newer is required for workshop removal.'
    return 1
  fi
  local options=(--endpoint "${DOCKER[${#DOCKER[@]} - 1]}")
  (( LAB_VERBOSE == 0 )) || options+=(--verbose)
  if [[ "${1:-}" == --release-reservations ]]; then options+=("$1"); fi
  exec python3 -I -B "${SCRIPT_DIR}/workshop_remove.py" "${options[@]}"
}
main "$@"
