#!/usr/bin/env bash
# Shared masked token prompt; owns terminal cleanup before its caller resumes.
set +ax
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
TTY_STATE='' PASTE_ENABLED=0
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"
# shellcheck source=read_masked_token.sh
source "${BASH_SOURCE[0]%/*}/read_masked_token.sh"

# Restore exact terminal state on completion, failure or handled interruption.
# Globals: TTY_STATE, PASTE_ENABLED. Args: none. Outputs: cleanup/warnings.
cleanup() {
  if [[ -n "${TTY_STATE}" ]] && ! stty "${TTY_STATE}" </dev/tty; then
    lab_status WARN 'Could not restore terminal settings.'
  fi
  if (( PASTE_ENABLED == 1 )); then
    printf '\033[?2004l' >/dev/tty || return 1
    PASTE_ENABLED=0
  fi
}

#######################################
# Prompt and feed the token to a trusted stdin consumer.
# Globals: TTY_STATE/PASTE_ENABLED (restored), tracing (disabled for input).
# Arguments: install|replace, then trusted command and its public arguments.
# Outputs: masked prompt/status; consumer output is its caller's responsibility.
# Returns: 5 entry ended before submission; consumer status (5 becomes 1).
#######################################
main() {
  local mode="${1:-}" prompt token status
  if (( $# < 2 )); then
    lab_status FAIL 'Expected token mode and consumer command.'
    return 1
  fi
  if [[ ! -t 0 ]]; then
    lab_status FAIL 'No interactive terminal for masked token entry.'
    return 5
  fi
  shift
  case "${mode}" in
    install) prompt='Workshop Ollama Cloud token (masked): ' ;;
    replace)
      prompt='Replacement Ollama Cloud token (masked; Enter keeps current): '
      ;;
    *) return 1 ;;
  esac
  trap cleanup EXIT
  trap 'exit 5' INT # Before submission only; EXIT restores the terminal.
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  unset token
  TTY_STATE="$(stty -g </dev/tty)" || return 5
  # Handle the Ctrl-C key locally; do not signal the waiting setup adapter.
  # Restore the original interrupt character before dispatching the consumer.
  stty -echo -icanon intr undef min 1 time 0 </dev/tty || return 5
  if [[ "${TERM:-dumb}" =~ ^(xterm|screen|tmux|rxvt|vt100) ]]; then
    PASTE_ENABLED=1
    printf '\033[?2004h' >/dev/tty || return 5
  fi
  printf '%s' "${prompt}" >/dev/tty || return 5
  if ! read_masked_token; then
    printf '\n' >&2
    return 5
  fi
  stty "${TTY_STATE}" </dev/tty || return 5
  TTY_STATE=''
  cleanup || return 5
  printf '\n' >/dev/tty || return 5
  if [[ -z "${token}" ]]; then return 5; fi
  trap 'exit 130' INT # A submitted candidate may commit before interruption.
  if printf '%s' "${token}" | "$@"; then
    unset token
    return 0
  else
    status=$?
  fi
  # A consumer cannot certify that input was never submitted.
  if (( status == 5 )); then status=1; fi
  unset token
  return "${status}"
}

main "$@"
