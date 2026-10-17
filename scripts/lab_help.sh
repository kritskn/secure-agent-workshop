#!/usr/bin/env bash
# Inert participant help: no engine, prerequisite or private-state inspection.
set -euo pipefail
# Internal output/cleanup state belongs to this invocation, never its env.
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

# Select help without inspecting or mutating participant state.
# Globals: TERM, NO_COLOR. Args: optional command. Outputs: help/error.
# Returns: 0 for help, 2 for an unknown command.
main() {
  case "${1:-help}" in
    help)
      help_lines 'Usage: ./lab.sh <command>' '' \
        '  setup   Prepare tools/private Pi HOME; check access.' \
        '  check   Check cached tools and live provider access.' \
        '  remove  Confirm lab STOP and workshop data removal.' \
        '  lab1    Lab 1 ARM64/AMD64 candidate. See lab1 --help.' \
        '  lab2    Lab 2 ARM64/AMD64 candidate. See lab2 --help.' \
        '  lab3    Lab 3 candidate. See lab3 --help.' \
        '  build-labs  Build public lab images; see --help.' \
        '  help    Show help.' '' \
        'Requirements' \
        '  macOS, Linux, or Windows with WSL2.' \
        '  Docker: Linux amd64/arm64. Use Bash; WSL2 Bash on Windows.' '' \
        'Ollama Cloud' \
        '  A free account can be used for workshop labs, within usage limits.' \
        '  Full setup/check use quota, may cost, and test logging' \
        '  in the workshop Docker volume.' \
        '' \
        'Next steps' \
        '  ./lab.sh setup' \
        '  ./lab.sh <command> --help' \
        '  Read README.md and the preparation guide.'
      ;;
    setup)
      help_lines 'Usage: ./lab.sh setup [--build-only [--no-cache]]' \
        '       ./lab.sh setup --help' '' \
        'Build Pi, nono and OpenShell images using Docker cache.' \
        '--build-only: public builds, stock pulls and offline version probes.' \
        'No private HOME, credential access or model request in build-only.' \
        '--no-cache: rebuild layers; no environment or shared-cache cleanup.' \
        'Without --build-only, setup also performs these private/live steps:' \
        'Prepare private HOME in the workshop Docker volume.' \
        'Save a masked token only after successful live verification.' \
        'Asterisks mask input; paste, then Enter. Backspace/Ctrl-U edit.' \
        'Start Docker yourself; setup never starts it or changes its context.' \
        'Conflicting private state is preserved, not silently overwritten.' \
        'A free Ollama Cloud account can be used for labs, within its limits.' \
        'One request per submitted key; uses quota and may cost.' \
        'Tests observer logging in the workshop Docker volume.' \
        '401/403 offers another masked key until success or cancellation.' \
        'Enter/EOF/Ctrl-C cancels. Failed candidates keep saved keys intact.' \
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
      help_lines 'Usage: ./lab.sh remove [-v|--verbose] [--help]' \
        '       ./lab.sh remove [--prep-images|--release-reservations] [-v]' \
        '--release-reservations: separately confirm settled Lab 2 markers.' \
        'If any operation is outstanding or uncertain, decline release.' \
        '-v/--verbose: safe diagnostics; consent/safety scope stays visible.' \
        '--prep-images: remove exact local preparation tags after consent.' \
        'Shows image IDs and owner/role label mismatches; default No.' \
        'Includes mismatched tags; refuses container references. No force.' \
        'Keeps HOME, keys, labs, other tags, stock images and shared cache.' \
        'Without --prep-images: list owned preparation/Lab 1/2/3 resources,' \
        'the workshop Docker volume, lab storage, owned images and host logs.' \
        'One default-No confirmation before supported lab STOP and deletion.' \
        'Save editor work: STOP interrupts tasks; unsaved work may be lost.' \
        'Only y/yes confirms. Enter/n/no/EOF/Ctrl-C cancels.' \
        'Credentials, projects, configuration, sessions and logs are lost.' \
        'Ownership, identities and references are rechecked after consent.' \
        'Unknown/shared resources or pending Lab 3 facts block removal.' \
        'Preserves source, personal configuration and shared build cache.' \
        'Lab 3 STOP verifies local provider cleanup; no upstream revocation.' \
        'No automatic takeover, force or prune. Image-only never stops.' \
        'Partial failures retain remaining data; review printed progress.'
      ;;
    *)
      lab_status FAIL 'Use ./lab.sh help.'
      return 2
      ;;
  esac
}

main "$@"
