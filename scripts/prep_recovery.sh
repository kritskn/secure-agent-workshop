#!/bin/bash
# Shared participant recovery guidance; prints instructions, never takes action.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Own the final preparation failure explanation and next step.
# Globals: LAB_SETUP_BRIEF, TERM, NO_COLOR, LAB_WORK_PID (output rendering).
# Arguments: dependencies|profile|live stage, optional failure status.
# Outputs: outcome/guidance to stderr. Returns: print status, not failure.
#######################################
prep_recovery() {
  local stage="${1:-}" status="${2:-1}"
  case "${stage}:${status}" in
    profile:5|live:5)
      lab_print '%s\n' \
        '[INFO] No candidate submitted; saved credentials unchanged.' >&2
      return
      ;;
    profile:3|live:3)
      lab_print '%s\n' \
        '[FAIL] Verification failed; saved credentials unchanged.' \
        '' '[SUGGESTED FIX]' \
        '  - Check connectivity, provider availability, quota/model access.' \
        '  - Then run ./lab.sh setup again.' \
        '    Verification uses quota and may cost.' \
        >&2
      return
      ;;
    profile:4|live:4)
      lab_print '%s\n' \
        '[FAIL] Access rejected for the selected model (401/403).' \
        '' '[SUGGESTED FIX]' \
        '  - Run ./lab.sh setup interactively to correct the key.' >&2
      return
      ;;
    *:129|*:130|*:143)
      lab_print '%s\n' \
        '[WARN] Outcome unconfirmed; a request or save may have completed.' \
        '' '[SUGGESTED FIX]' \
        '  - Inspect active work in Docker before retrying; do not reset.' >&2
      return
      ;;
    live:*)
      lab_print '%s\n' '[FAIL] Verification did not complete.' \
        '' '[SUGGESTED FIX]' \
        '  - Check preparation prerequisites and the selected Docker engine.' \
        '  - Inspect active work before running ./lab.sh setup again.' >&2
      return
      ;;
  esac
  lab_print '%s\n' '[INFO] Preparation incomplete; nothing was reset.' \
    '' '[SUGGESTED FIX]' >&2
  case "${stage}" in
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
