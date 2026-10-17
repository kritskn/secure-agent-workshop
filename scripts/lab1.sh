#!/usr/bin/env bash
# Lab 1 participant commands; Python owns resource and lifecycle validation.
set -euo pipefail
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

# Resolve Docker only for an explicit action, never help.
# Globals: DOCKER from check_docker_host; BASH source location.
# Arguments: action, optional --verbose. Outputs: status/UI. Returns: 0/1.
run_lab1() {
  local action="$1" project endpoint output status
  shift
  if [[ "${action}" == enter || "${action}" == reset ]] \
    && [[ ! -t 0 || ! -t 1 || ! -t 2 ]]; then
    lab_status FAIL 'An interactive terminal is required; no changes made.'
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    lab_status FAIL 'Python 3 is required for Lab 1.'
    return 1
  fi
  project="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)" || return
  if [[ "${action}" == setup ]]; then
    lab_status INFO "Lab 1 ${action}..."
    if output="$(python3 -I -B "${project}/scripts/lab1_setup.py" \
      "$@" 3>&2 2>/dev/null)"; then
      lab_print '%s\n' "${output}"
      return 0
    fi
    lab_print '%s\n' "[FAIL] ${output:-Setup failed; state retained.}" >&2
    return 1
  fi
  # shellcheck source=docker_host.sh
  source "${project}/scripts/docker_host.sh"
  check_docker_host || return
  endpoint="${DOCKER[${#DOCKER[@]} - 1]}"
  lab_status INFO "Lab 1 ${action}..."
  if python3 -I -B "${project}/scripts/lab1_runtime.py" "${action}" \
    --endpoint "${endpoint}" "$@"; then
    lab_status PASS "Lab 1 ${action} command completed."
  else
    status=$?
    if [[ "${action}" == reset ]] && (( status == 3 )); then
      lab_status INFO 'Reset cancelled; nothing deleted.'
      return 0
    fi
    lab_status FAIL 'Lab 1 command did not complete; no automatic retry.'
    return 1
  fi
}

# Validate arguments before dispatch; help never inspects private state.
# Globals: LAB_ARGS, LAB_VERBOSE, formatting. Args: action, --help, -v.
# Outputs: help/status. Returns: 0 success/help, 1 refused, 2 invalid arguments.
main() {
  lab_output_options "${1-help}" "${@:2}" || return
  set -- "${LAB_ARGS[@]}"
  local action="${1-help}"
  case "${action}" in
    help|--help)
      if (( $# > 1 )); then
        lab_status FAIL 'Use ./lab.sh lab1 --help.'
        return 2
      fi
      ;;
    setup|enter|stop|reset)
      if (( $# == 1 )); then
        if (( LAB_VERBOSE )); then
          run_lab1 "${action}" --verbose
        else
          run_lab1 "${action}"
        fi
        return $?
      elif (( $# != 2 )) || [[ "$2" != --help ]]; then
        lab_status FAIL 'Use ./lab.sh lab1 --help.'
        return 2
      fi
      ;;
    *)
      lab_status FAIL 'Use ./lab.sh lab1 --help.'
      return 2
      ;;
  esac
  help_lines \
    'Usage: ./lab.sh lab1 <setup|enter|stop|reset> [--help]' '' \
    'ARM64/AMD64 candidate; preparation must already be complete.' \
    '  setup  Prepare tools/config; automatically copy the key for new HOME.' \
    '  enter  Open Agent and Editor tabs; reattach without duplicating apps.' \
    '  stop   Stop Lab 1, keeping saved work. Save editors first.' \
    '  reset  Confirm (y/N), discard Lab 1 HOME and restore starter assets.' \
    '' \
    'Setup builds current tooling with Docker caching; no Pi/model requests.' \
    'Setup checks installation only, never exercise behavior.' \
    'All actions accept -v/--verbose; setup/reset append lab-log.txt.' \
    'Ctrl+B then q detaches without stopping. Enter starts Pi normally.' \
    'Stop/reset cannot guarantee cancellation of submitted model requests.'
}

main "$@"
