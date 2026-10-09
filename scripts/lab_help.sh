#!/usr/bin/env bash
# Inert participant help: no engine, prerequisite or private-state inspection.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

# Render help with terminal-only headings and command accents.
# Globals: TERM, NO_COLOR. Args: lines. Outputs: stdout. Returns: printf status.
help_lines() {
  local line colour
  for line in "$@"; do
    colour=''
    case "${line}" in
      'Usage:'*|Requirements|'Ollama Cloud'|'Next steps') colour='1;36' ;;
      '  setup '*|'  check '*|'  remove '*|'  help '*|'  ./lab.sh '*)
        colour='32'
        ;;
    esac
    lab_text "${colour}" "${line}" 1 $'\n' || return
  done
}

# Select help without inspecting or mutating participant state.
# Globals: TERM, NO_COLOR. Args: optional command. Outputs: help/error.
# Returns: 0 for help, 2 for an unknown command.
main() {
  case "${1:-help}" in
    help)
      help_lines 'Usage: ./lab.sh <command>' '' \
        '  setup   Prepare dependencies/private Pi HOME and check access.' \
        '  check   Check cached tools, profile and live provider access.' \
        '  remove  Remove preparation containers/HOME after confirmation.' \
        '  help    Show help.' '' \
        'Requirements' \
        '  macOS, Linux, or Windows with WSL2.' \
        '  Docker running with Linux containers (amd64 or arm64).' \
        '  Use Bash; on Windows, use WSL2 Bash with Linux Docker.' '' \
        'Ollama Cloud' \
        '  A free account can be used for workshop labs, within usage limits.' \
        '  Setup/check use quota, may cost, and test logging' \
        '  in the workshop Docker volume.' \
        '  Setup may offer one key replacement and one additional request.' '' \
        'Next steps' \
        '  ./lab.sh setup' \
        '  ./lab.sh <command> --help' \
        '  Read README.md and the preparation guide.'
      ;;
    setup)
      help_lines 'Usage: ./lab.sh setup [--help]' '' \
        'Build/reuse Pi, nono and OpenShell dependency images.' \
        'Prepare private HOME in the workshop Docker volume.' \
        'Enroll a masked token.' \
        'Asterisks mask input; paste, then Enter. Backspace/Ctrl-U edit.' \
        'Start Docker yourself; setup never starts it or changes its context.' \
        'Existing incompatible state is refused, not silently repaired.' \
        'A free Ollama Cloud account can be used for labs, within its limits.' \
        'One live request; uses quota and may cost.' \
        'Tests observer logging in the workshop Docker volume.' \
        'Only live failure offers optional key replacement and one retry.' \
        'Enter at replacement keeps the current key and stops without retry.' \
        'No exercise, gateway or sandbox services are started.' \
        'On failure, follow the recovery guidance shown; do not force a reset.'
      ;;
    check)
      help_lines 'Usage: ./lab.sh check [--help]' '' \
        'Use cached images only; check profile, provider access and logging.' \
        'Shows brief results and confirms workshop preparation readiness.' \
        'At most one live request; uses quota and may cost.' \
        'Tests observer logging in the workshop Docker volume.' \
        'No build, pull, repair, service startup, prompt or retry.' \
        'A pass does not qualify exercises, sandbox enforcement or the Pi UI.' \
        'Missing preparation: run ./lab.sh setup; otherwise follow guidance.'
      ;;
    remove)
      help_lines 'Usage: ./lab.sh remove [--help]' '' \
        'Delete identified preparation containers and' \
        'the workshop Docker volume only.' \
        'Requires a terminal: Reset preparation? (Y/n), default Yes.' \
        'Enter/y/yes confirms; n/no/EOF/Ctrl-C cancels.' \
        'Preparation credentials, sessions and logs will be lost.' \
        'Images/cache, lab state, other containers and VMs are preserved.' \
        'Unknown references or external volume backends are refused.' \
        'Key deletion does not revoke the provider key. No force option.' \
        'Removal does not recreate state. Afterwards: ./lab.sh setup'
      ;;
    *)
      lab_status FAIL 'Use ./lab.sh help.'
      return 2
      ;;
  esac
}

main "$@"
