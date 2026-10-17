#!/usr/bin/env bash
# Lab 3 participant lifecycle; help/argument checks have no runtime effects.
set -euo pipefail
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

# Run the selected private-state lifecycle with ordinary Docker configuration.
# Globals: BASH_SOURCE. Args: validated action/options. Outputs: status/UI.
# Returns: Python action status or prerequisite failure.
run_lab3() {
  local project
  if ! command -v python3 >/dev/null 2>&1 \
    || ! python3 -I -B -c 'import sys;sys.exit(sys.version_info < (3,9))'; then
    lab_status FAIL 'Python 3.9 or newer is required; no changes.'
    return 1
  fi
  project="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)" || return
  exec python3 -I -B "${project}/scripts/lab3_runtime.py" "$@"
}

# Validate the complete command before selecting Python, state or an engine.
# Globals: LAB_ARGS, LAB_VERBOSE, formatting. Args: action/options/help.
# Returns: action status, 0 help, 2 invalid arguments.
main() {
  lab_output_options "${1-help}" "${@:2}" || return
  set -- "${LAB_ARGS[@]}"
  local action="${1-help}"
  if [[ ( "${action}" == help || "${action}" == --help ) && $# -le 1 \
    || ( "${action}" =~ ^(setup|run-pipeline|enter|stop|reset)$ \
    && $# -eq 2 && "$2" == --help ) ]]; then
    help_lines \
      'Usage: ./lab.sh lab3 <setup|run-pipeline|enter|stop|reset>' '' \
      'Linux ARM64/AMD64 candidate; complete preparation first.' \
      '  setup         Prepare software and a stopped environment.' \
      '  run-pipeline  Activate provider-free; type START once for a task.' \
      '  enter         Separate terminal: OpenShell / Editor observation.' \
      '  stop          Verified owned STOP; preserve private evidence.' \
      '  reset         Stopped/settled disposal and recreation; default No.' \
      'Repeat setup: one default-No gateway/editor replacement decision.' \
      'Installed image/Pi configuration stays with its recorded image.' \
      'Save work before STOP. Detaching does not stop services/tasks.' \
      'Use one lab at a time; do not overlap workshop operations.' \
      '30-minute pipeline; one task, at most 5 minutes including cleanup.' \
      'START may cost. Optional CHECK is scripted, not agent behavior.' \
      'No retry/replay. Local stop does not guarantee cloud cancellation.' \
      'All actions accept -v/--verbose for safe diagnostic progress.' \
      'Only setup accepts --engine-socket /ENGINE/SIDE/socket.' \
      'Use ./lab.sh remove for workshop uninstall after verified STOP.'
    return 0
  fi
  if [[ ! "${action}" =~ ^(setup|run-pipeline|enter|stop|reset)$ ]]; then
    lab_status FAIL 'Use ./lab.sh lab3 --help.'
    return 2
  fi
  local arguments=("${action}")
  (( LAB_VERBOSE == 0 )) || arguments+=(--verbose)
  if [[ "${action}" != setup ]]; then
    if (( $# != 1 )); then
      lab_status FAIL 'Only setup accepts engine options. Use lab3 --help.'
      return 2
    fi
    run_lab3 "${arguments[@]}"
    return $?
  fi
  shift
  local socket=''
  while (( $# )); do
    case "$1" in
      --engine-socket)
        if (( $# < 2 )) || [[ -n "${socket}" || "$2" != /* \
          || "$2" == / || "$2" == *','* || "$2" == *$'\n'* \
          || "$2" == *$'\r'* ]]; then
          lab_status FAIL 'An absolute engine-side socket path is required.'
          return 2
        fi
        socket="$2"
        shift 2
        ;;
      *) lab_status FAIL 'Use ./lab.sh lab3 setup --help.'; return 2 ;;
    esac
  done
  if [[ -n "${socket}" ]]; then
    arguments+=(--engine-socket "${socket}")
  fi
  run_lab3 "${arguments[@]}"
}

main "$@"
