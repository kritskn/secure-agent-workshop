#!/bin/bash
# Character-by-character token input with bracketed paste; never echo input.

#######################################
# Read a masked token; bracketed paste waits for Enter, then trim its edges.
# Globals: caller's local token (filled), terminal already set to no echo.
# Arguments: none. Outputs: asterisks/editing to /dev/tty, never raw input.
# Returns: 0 on Enter, 1 on EOF or unsupported terminal input.
#######################################
read_masked_token() {
  local character sequence paste=0
  unset character sequence
  token=''
  while :; do
    IFS= read -r -s -n 1 character </dev/tty || return 1
    [[ "${character}" != $'\004' ]] || return 1
    if [[ "${character}" == $'\033' ]]; then
      IFS= read -r -s -n 5 -t 1 sequence </dev/tty || return 1
      case "${paste}|${sequence}" in
        '0|[200~') paste=1 ;;
        '1|[201~') paste=0 ;;
        *) return 1 ;;
      esac
      continue
    fi
    if (( paste == 1 )); then
      token+="${character:-$'\n'}"
      printf '*' >/dev/tty
      continue
    fi
    case "${character}" in
      ''|$'\r') break ;;
      $'\177'|$'\b')
        if [[ -n "${token}" ]]; then
          token="${token%?}"
          printf '\b \b' >/dev/tty
        fi
        ;;
      $'\025')
        while [[ -n "${token}" ]]; do
          token="${token%?}"
          printf '\b \b' >/dev/tty
        done
        ;;
      *)
        token+="${character}"
        printf '*' >/dev/tty
        ;;
    esac
  done
  while [[ "${token}" == [[:space:]]* ]]; do
    token="${token#?}"
  done
  while [[ "${token}" == *[[:space:]] ]]; do
    token="${token%?}"
  done
  return 0
}
