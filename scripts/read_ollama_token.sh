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
# Returns: 0 saved, 3 replacement declined, 1 input/transport failure.
#######################################
main() {
  local mode="${1:-}" prompt token
  if (( $# < 2 )) || [[ ! -t 0 ]]; then
    lab_status FAIL 'No interactive terminal for masked token entry.'
    return 1
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
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  unset token
  TTY_STATE="$(stty -g </dev/tty)" || return 1
  stty -echo -icanon min 1 time 0 </dev/tty || return 1
  if [[ "${TERM:-dumb}" =~ ^(xterm|screen|tmux|rxvt|vt100) ]]; then
    PASTE_ENABLED=1
    printf '\033[?2004h' >/dev/tty || return 1
  fi
  printf '%s' "${prompt}" >/dev/tty || return 1
  if ! read_masked_token; then
    lab_print '\n%s\n' '[FAIL] Token input failed; no key was saved.' >&2
    return 1
  fi
  stty "${TTY_STATE}" </dev/tty || return 1
  TTY_STATE=''
  cleanup || return 1
  printf '\n' >/dev/tty
  if [[ -z "${token}" ]]; then
    if [[ "${mode}" == replace ]]; then
      lab_status WARN 'Current token kept; live check still failed.'
      return 3
    fi
    lab_status FAIL 'Empty token; no credential was saved.'
    return 1
  fi
  if printf '%s' "${token}" | "$@"; then
    unset token
    return 0
  fi
  unset token
  lab_print '%s\n' \
    '[FAIL] Token save failed; existing state kept where possible.' >&2
  return 1
}

main "$@"
