#!/bin/bash
# Shared participant recovery guidance; prints instructions, never takes action.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Print short, stage-specific next steps after a preparation failure.
# Globals: LAB_SETUP_BRIEF, TERM, NO_COLOR, LAB_WORK_PID (output rendering).
# Arguments: dependencies|profile|live stage.
# Outputs: guidance to stderr. Returns: printf status.
#######################################
prep_recovery() {
  lab_print '%s\n' '[INFO] Existing files are kept; nothing was reset.' \
    '' '[SUGGESTED FIX]' >&2
  case "${1:-}" in
    dependencies)
      lab_print '%s\n' \
        '  - Start Docker and check that the selected context is correct.' \
        '  - Fix the error above, then run ./lab.sh setup.' >&2
      ;;
    profile)
      lab_print '%s\n' \
        '  - If preparation is missing, run ./lab.sh setup.' >&2
      lab_print '%s%s\n' \
        '  - If files or settings were rejected, follow the fix guide' \
        ' in the preparation PDF.' >&2
      lab_print '%s\n' \
        '  - Do not delete files or change permissions to bypass the error.' >&2
      ;;
    live)
      lab_print '%s\n' \
        '  - Check your internet connection.' \
        '  - Check Ollama model access and quota.' \
        '  - Run ./lab.sh check again. It may use paid credits.' >&2
      ;;
  esac
}

#######################################
# Explain cancellation without claiming remote work stopped or was rolled back.
# Globals: LAB_SETUP_BRIEF, TERM, NO_COLOR, LAB_WORK_PID (output rendering).
# Arguments: setup|check|remove. Outputs: stderr guidance.
# Returns: printf status. Never signals Docker or cleans resources itself.
#######################################
prep_cancelled() {
  lab_print '[WARN] %s cancelled; partial state may remain.\n' "$1" >&2
  lab_print '%s\n' \
    'Docker or a provider request may still be running.' \
    '' '[SUGGESTED FIX]' \
    '  - Check for active work in Docker before retrying.' \
    '  - Keep existing files. Do not force-delete state.' >&2
}
