#!/bin/bash
# Private profile setup and user-driven live validation; dependencies separate.
# shellcheck source=lab_work.sh
source "${BASH_SOURCE[0]%/*}/lab_work.sh"
# shellcheck source=prep_vol.sh
source "${BASH_SOURCE[0]%/*}/prep_vol.sh"
# shellcheck source=prep_auth.sh
source "${BASH_SOURCE[0]%/*}/prep_auth.sh"
# shellcheck source=check_prep.sh
source "${BASH_SOURCE[0]%/*}/check_prep.sh"

# Verify each explicitly entered candidate; only 401/403 offers another prompt.
# Globals/output/status: as prepare_prep_auth. Args: project, install|replace.
# No automatic request retry: each call prompts anew. No noninteractive loop.
prepare_prep_candidates() {
  local status
  while :; do
    if prepare_prep_auth "$@"; then return 0; else status=$?; fi
    if (( status != 4 )); then return "${status}"; fi
    if [[ ! -t 0 ]]; then return "${status}"; fi
    LAB_SETUP_BRIEF=0 lab_print '%s\n' \
      '[INFO] Access rejected for this model; candidate not saved.' \
      '[INFO] Enter another key, or cancel with Enter, EOF or Ctrl-C.' >&2
  done
}

# Initialize/reuse HOME, retain/enroll auth, then check offline readiness.
# Globals: checked DOCKER/DOCKER_ARCH/RUNTIME_IMAGE_ID from dependency setup;
#   PREP_VOLUME, PREP_AUTH_VERIFIED, LAB_SETUP_BRIEF.
# Arguments: trusted project directory. Outputs: progress and masked prompt.
# Returns: 0 complete, otherwise stage status. No rollback of existing state.
# No image selection/build/pull, automatic retry or reset.
prepare_prep_profile() {
  local project="${1:-}" status
  PREP_VOLUME=''
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if lab_work 'Private HOME' prepare_prep_volume "${project}" \
    && prepare_prep_candidates "${project}" install \
    && lab_work 'Offline readiness' check_prep_runtime "${project}"; then
    lab_status PASS \
      'Private profile ready offline in the workshop Docker volume.'
    if [[ "${PREP_AUTH_VERIFIED:-0}" != 1 ]]; then
      lab_status INFO 'Provider access and lab readiness remain unverified.'
    fi
    return 0
  else
    status=$?
  fi
  PREP_VOLUME=''
  return "${status}"
}

# Check saved-key access; only typed 401/403 permits candidate correction.
# Globals: DOCKER/DOCKER_ARCH/RUNTIME_IMAGE_ID/PREP_VOLUME, LAB_SETUP_BRIEF;
#   PREP_AUTH_VERIFIED (set by enrollment, initialized by setup).
# Arguments: trusted project directory. Outputs: warnings and masked prompt.
# Returns: 0 verified, otherwise delegated check/enrollment status; 1 bad args.
# Each further live attempt needs new input. Caller completes profile setup.
prepare_prep_live() {
  local project="${1:-}" status
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if [[ "${PREP_AUTH_VERIFIED:-0}" == 1 ]]; then return 0; fi
  if [[ "${LAB_SETUP_BRIEF:-0}" == 1 ]]; then
    lab_print '%s%s\n' \
      '[WARN] Online check uses available free credits first' \
      ' and tests observer log writing.' >&2
  else
    lab_print '%s%s\n' \
      '[INFO] Live check uses quota, may cost,' \
      ' and tests logging in the workshop Docker volume.'
  fi
  if lab_work 'Provider response and log' check_prep_live "${project}"; then
    return 0
  else
    status=$?
  fi
  if (( status != 4 )) || [[ ! -t 0 ]]; then
    return "${status}"
  fi
  LAB_SETUP_BRIEF=0 lab_print '%s\n' \
    '[INFO] Access rejected for this model. Enter a replacement key or cancel.'
  prepare_prep_candidates "${project}" replace
}
