#!/bin/bash
# Same-shell progress animation; credential and reset prompts are never wrapped.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Stop and reap only this shell's progress process.
# Globals: LAB_WORK_PID (cleared). Arguments: none. Outputs: none.
# Returns: 0. Caller invokes on EXIT and before cancellation guidance.
#######################################
lab_stop_work() {
  if [[ -n "${LAB_WORK_PID:-}" ]]; then
    kill "${LAB_WORK_PID}" 2>/dev/null || :
    wait "${LAB_WORK_PID}" 2>/dev/null || :
    LAB_WORK_PID=''
  fi
}

#######################################
# Run noninteractive work in this shell, preserving globals and exit status.
# Globals: LAB_WORK_PID/TITLE/WORD, TERM, NO_COLOR; command publishes globals.
# Arguments: label, function/command, arguments. Outputs: unbuffered originals.
# Returns: delegated status. No animation on pipes, dumb terminals or NO_COLOR.
# Caller installs lab_stop_work EXIT/signal cleanup; no traps replaced here.
#######################################
lab_work() {
  local title="${LAB_WORK_TITLE:-$1}" status=0
  shift
  if [[ -t 1 && -t 2 && -z "${NO_COLOR+x}" \
    && "${TERM:-dumb}" =~ ^(xterm|screen|tmux|rxvt|vt100) ]]; then
    lab_spin "${title}" &
    LAB_WORK_PID=$!
  fi
  "$@" || status=$?
  lab_stop_work
  return "${status}"
}
