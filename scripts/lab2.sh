#!/usr/bin/env bash
# Lab 2 lifecycle; selected-run reset requires stopped state and consent.
set -euo pipefail
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"
# Resolve one engine; setup captures status, entry/reset use the terminal.
# Globals: DOCKER, BASH_SOURCE, LAB_VERBOSE. Args: action, run, setup port.
# Outputs: status/consent/UI. Returns: exact Python status or preflight failure.
run_lab2() {
  local action="$1" run="$2" project output status
  shift 2
  if [[ "${action}" =~ ^(enter|reset)$ && ( ! -t 0 || ! -t 1 \
    || ! -t 2 ) ]]; then
    lab_status FAIL "Interactive terminal required for ${action}; no changes."
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1 || ! python3 -I -B -c \
    'import sys; sys.exit(sys.version_info < (3, 9))'; then
    lab_status FAIL 'Python 3.9 or newer is required; no changes made.'
    return 1
  fi
  project="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)" || return
  # shellcheck source=docker_host.sh
  source "${project}/scripts/docker_host.sh"
  check_docker_host || return
  local options=(--endpoint "${DOCKER[${#DOCKER[@]} - 1]}" --run "${run}")
  (( LAB_VERBOSE == 0 )) || options+=(--verbose)
  lab_status INFO "Lab 2 Run ${run} ${action}..."
  if [[ "${action}" == reset ]]; then
    python3 -I -B "${project}/scripts/lab2_reset.py" \
      "${options[@]}" && return 0
    status=$?
  elif [[ "${action}" != setup ]]; then
    exec python3 -I -B "${project}/scripts/lab2_entry.py" "${action}" \
      "${options[@]}"
  elif output="$(python3 -I -B "${project}/scripts/lab2_setup.py" \
    "${options[@]}" "$@" 3>&2 2>/dev/null)"; then
    lab_print '%s\n' "${output}"
    return 0
  else
    status=$?
  fi
  if (( status == 3 )); then
    lab_status FAIL "Lab 2 Run ${run} is not confirmed stopped."
    lab_text '1;33' "[NEXT] Save work; ./lab.sh lab2 stop --run ${run}" 2 $'\n'
    lab_status HELP "After STOP succeeds, retry ${action}."
    [[ "${action}" != reset ]] || lab_status WARN 'Reset deletes run data.'
    [[ -z "${output:-}" ]] || lab_print '%s\n' "${output}" >&2
  elif [[ "${action}" == setup ]]; then
    lab_status FAIL "${output:-Setup incomplete; existing state retained.}"
  fi
  return "${status}"
}

# Validate complete arguments before selecting tools or private state.
# Globals: LAB_ARGS, LAB_VERBOSE, formatting. Args: action/options/help.
# Outputs: inert help or action. Returns: action status or 2 for invalid args.
main() {
  lab_output_options "${1-help}" "${@:2}" || return
  set -- "${LAB_ARGS[@]}"
  local action="${1-help}" port
  if [[ ( "${action}" == help || "${action}" == --help ) && $# -le 1 \
    || ( "${action}" =~ ^(setup|enter|stop|reset)$ && $# -eq 2 \
    && "$2" == --help ) ]]; then
    help_lines \
      'Usage: ./lab.sh lab2 <setup|enter|stop|reset> --run <1|2>' \
      '       ./lab.sh lab2 setup --run <1|2> [--app-port PORT]' '' \
      'Linux AMD64/ARM64 candidate; complete preparation first.' \
      'One lab at a time. Setup leaves services stopped; repeat keeps keys.' \
      'Run 1 entry launches Pi; Run 2 protected launch is manual.' \
      'Save work before STOP; detaching does not stop services/tasks.' \
      'Configuration replacement/reset: default No. Reset deletes run data.' \
      '-v/--verbose: safe diagnostics; never bypasses lifecycle checks.'
    return 0
  fi
  if [[ ! "${action}" =~ ^(setup|enter|stop|reset)$ \
    || ( $# -ne 3 && $# -ne 5 ) || "$2" != --run \
    || ( "$3" != 1 && "$3" != 2 ) ]]; then
    lab_status FAIL 'Use ./lab.sh lab2 <setup|enter|stop|reset> --run <1|2>.'
    return 2
  fi
  if (( $# == 5 )); then
    port="$5"
    if [[ "${action}" != setup || "$4" != --app-port \
      || ! "${port}" =~ ^[1-9][0-9]{3,4}$ ]]; then
      lab_status FAIL 'Setup accepts --app-port with decimal port 1024..65535.'
      return 2
    fi
    if (( port < 1024 || port > 65535 )); then
      lab_status FAIL 'Browser port must be 1024..65535; no action taken.'
      return 2
    fi
    run_lab2 "${action}" "$3" --app-port "${port}"
  else
    run_lab2 "${action}" "$3"
  fi
}

main "$@"
