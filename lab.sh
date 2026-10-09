#!/usr/bin/env bash
# Docker preparation, live checks, confirmed preparation removal and inert help.

set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=scripts/lab_output.sh
source "${SCRIPT_DIR}/scripts/lab_output.sh"

#######################################
# Validate arguments before dispatch; help never inspects the host or Docker.
# Globals: SCRIPT_DIR, BASH (the running interpreter, reused for children).
# Arguments: participant command and optional --help.
# Outputs: help, compact status or actionable error.
# Returns: selected command's status, or 2 for invalid arguments.
#######################################
main() {
  local script status
  if (( $# == 2 )) && [[ "$1" == 'help' && "$2" == '--help' ]]; then
    set -- help
  fi
  case "${1:-help}" in
    help|--help)
      if (( $# <= 1 )); then
        exec "${BASH}" "${SCRIPT_DIR}/scripts/lab_help.sh"
      fi
      ;;
    setup|check|remove)
      if (( $# == 2 )) && [[ "$2" == '--help' ]]; then
        exec "${BASH}" "${SCRIPT_DIR}/scripts/lab_help.sh" "$1"
      fi
      if (( $# == 1 )); then
        script="${SCRIPT_DIR}/scripts/check_lab.sh"
        if [[ "$1" == 'setup' || "$1" == 'remove' ]]; then
          script="${SCRIPT_DIR}/scripts/lab_$1.sh"
        fi
        if "${BASH}" "${script}"; then
          return 0
        else
          status=$?
        fi
        return "${status}"
      fi
      ;;
  esac
  lab_status FAIL 'Invalid command or arguments. Use ./lab.sh help.'
  return 2
}

main "$@"
