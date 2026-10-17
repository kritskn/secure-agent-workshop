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
# Arguments: project, optional --build-only [--no-cache].
# Outputs: progress, prompts and results.
# Returns: 0 success; 3 live failure, 4 rejection, 5 no submission; else error.
# No extra retry, rollback or reset. Caller owns cancellation handling.
# Real execution provisions dependencies/HOME and may enroll/call a provider;
# source/mock approval alone does not authorize those actions.
#######################################
setup_prep() {
  local project="${1:-}" status stage=dependencies LAB_WORK_WORD='Working…'
  local cache=cache PREP_AUTH_VERIFIED=0
  PREP_VOLUME=''
  if [[ -z "${project}" ]] || ! [[ $# -eq 1 \
    || ( "${2:-}" == --build-only \
      && ( $# -eq 2 || ( $# -eq 3 && "$3" == --no-cache ) ) ) ]]; then
    lab_print '%s\n' \
      '[FAIL] Usage: ./lab.sh setup [--build-only [--no-cache]]' >&2
    return 2
  fi
  if [[ "${3:-}" == --no-cache ]]; then cache=no-cache; fi
  if LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Preparing tools' \
    prepare_prep_dependencies "${project}" "${cache}"; then
    lab_status PASS 'Workshop Tools ready.'
    if [[ "${2:-}" == --build-only ]]; then
      lab_status INFO 'Build-only complete; private preparation not checked.'
      return 0
    fi
    lab_print '\n'
  else
    status=$?
    if [[ "${2:-}" == --build-only ]]; then
      lab_status INFO 'Build-only stopped; completed cache kept. Nothing reset.'
      lab_status INFO \
        'Resolve the error, then rerun the same build-only command.'
    else
      prep_recovery dependencies "${status}"
    fi
    return "${status}"
  fi
  stage=profile
  if LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Preparing agent' \
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
  prep_recovery "${stage}" "${status}"
  return "${status}"
}
