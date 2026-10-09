#!/bin/bash
# Compact participant status output; helpers never persist command output.
# shellcheck source=lab_format.sh
source "${BASH_SOURCE[0]%/*}/lab_format.sh"

# Print text and optional ending together, with terminal-only colour/clearing.
# Globals: TERM, NO_COLOR, LAB_WORK_PID. Args: colour, text, fd=1, ending=''.
# Outputs: requested stream; plain for pipes/NO_COLOR/dumb. Returns: printf.
lab_text() {
  local colour="$1" text="$2" stream="${3:-1}" ending="${4:-}" clear=''
  # Any NO_COLOR value, including empty, opts out.
  if [[ -t "${stream}" && "${TERM:-dumb}" != 'dumb' \
    && -z "${NO_COLOR+x}" ]]; then
    [[ -z "${LAB_WORK_PID:-}" ]] || clear=$'\r\033[2K'
    if [[ -n "${colour}" ]]; then
      text=$'\033['"${colour}m${text}"$'\033[0m'
    fi
  fi
  printf '%s' "${clear}${text}${ending}" >&"${stream}"
}

# Print status, with colour only on a supported terminal stream.
# Globals: TERM, NO_COLOR, LAB_SETUP_BRIEF. Args: status, message.
# Outputs: stdout; FAIL/WARN to stderr; BANNER without prefix. Returns: printf.
lab_status() {
  local stream=1 colour='' message="[$1] $2"
  lab_line_visible "${message}" || return 0
  case "$1" in
    PASS|BANNER) colour='32' ;;
    FAIL)
      stream=2
      colour='31'
      ;;
    WARN)
      stream=2
      colour='33'
      ;;
    INFO) colour='36' ;;
    HELP) colour='34' ;;
  esac
  [[ "$1" != 'BANNER' ]] || message="$2"
  lab_text "${colour}" "${message}" "${stream}" $'\n'
}

# Animate until terminated; reap each short sleep before clearing the line.
# Globals: LAB_WORK_WORD. Args: title. Outputs: stdout. Returns: 0 on TERM.
lab_spin() {
  local frame
  trap 'exit 0' TERM
  trap 'printf "\r\033[2K"' EXIT
  while :; do
    for frame in '⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏'; do
      printf '\r\033[2K\033[36m%s %s %s\033[0m' \
        "${frame}" "${LAB_WORK_WORD:-Working...}" "$1"
      sleep 0.1 || return $?
    done
  done
}
