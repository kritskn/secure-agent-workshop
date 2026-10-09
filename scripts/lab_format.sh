#!/bin/bash
# Format public CLI lines; brief preparation hides details, not failures.

# Select public lines during preparation's internal, scoped brief view.
# Globals: LAB_SETUP_BRIEF. Args: line. Outputs: none. Returns: 0 show, 1 hide.
lab_line_visible() {
  if [[ "${LAB_SETUP_BRIEF:-0}" == 1 ]]; then
    case "$1" in
      '[PASS] '*|'[INFO] '*) return 1 ;;
    esac
  fi
  return 0
}

#######################################
# Print formatted text with terminal-only status accents, preserving newlines.
# Globals: TERM, NO_COLOR, LAB_SETUP_BRIEF, LAB_WORK_PID; lab_text helper.
# Arguments: printf format and values. Outputs: stdout (caller may redirect).
# Returns: printf status; no buffering of commands or subprocess diagnostics.
#######################################
lab_print() {
  local output line colour
  # Callers supply literal formats, exactly as for the printf builtin.
  # shellcheck disable=SC2059
  printf -v output "$@" || return
  while [[ "${output}" == *$'\n'* ]]; do
    line="${output%%$'\n'*}"
    output="${output#*$'\n'}"
    lab_line_visible "${line}" || continue
    colour=''
    case "${line}" in
      '[PASS] '*) colour='32' ;;
      '[FAIL] '*) colour='31' ;;
      '[WARN] '*) colour='33' ;;
      '[INFO] '*) colour='36' ;;
      '[HELP] '*|'[SUGGESTED FIX]') colour='34' ;;
    esac
    lab_text "${colour}" "${line}" 1 $'\n' || return
  done
  if [[ -n "${output}" ]]; then
    printf '%s' "${output}"
  fi
}
