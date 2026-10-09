#!/bin/bash
# Internal Docker preparation coordinator; not a second participant entry point.
# shellcheck source=prep_dependencies.sh
source "${BASH_SOURCE[0]%/*}/prep_dependencies.sh"
# shellcheck source=prep_profile.sh
source "${BASH_SOURCE[0]%/*}/prep_profile.sh"
# shellcheck source=prep_recovery.sh
source "${BASH_SOURCE[0]%/*}/prep_recovery.sh"

#######################################
# Run dependency, private profile and bounded live stages in this shell.
# Globals: stages publish DOCKER/DOCKER_ARCH, image IDs, pins and PREP_VOLUME.
#   Clear stale PREP_VOLUME first; retained volume is not a readiness flag.
#   Scope LAB_SETUP_BRIEF/WORK_TITLE/WORK_WORD to this setup view only.
# Arguments: trusted project directory. Outputs: progress, prompts and results.
# Returns: 0 all stages passed, otherwise failed stage status; 1 bad arguments.
# No extra retry, rollback or reset. Caller owns cancellation handling.
# Real execution provisions dependencies/HOME and may enroll/call a provider;
# source/mock approval alone does not authorize those actions.
#######################################
setup_prep() {
  local project="${1:-}" status stage=dependencies LAB_WORK_WORD='Working…'
  PREP_VOLUME=''
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Preparing tools' \
    prepare_prep_dependencies "${project}" \
    && lab_status PASS 'Workshop Tools ready.' && lab_print '\n' \
    && stage=profile \
    && LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Preparing agent' \
      prepare_prep_profile "${project}" \
    && lab_status PASS 'Agent profile ready.' && lab_print '\n' \
    && stage=live \
    && LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Checking Ollama Cloud' \
      prepare_prep_live "${project}"; then
    lab_status PASS 'Ollama response and fresh observer log verified.'
    lab_status PASS \
      'Preparation setup completed. Run ./lab.sh check to confirm readiness.'
    return 0
  else
    status=$?
  fi
  prep_recovery "${stage}"
  return "${status}"
}
