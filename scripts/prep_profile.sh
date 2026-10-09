#!/bin/bash
# Private profile setup and bounded live validation; dependencies separate.
# shellcheck source=lab_work.sh
source "${BASH_SOURCE[0]%/*}/lab_work.sh"
# shellcheck source=prep_vol.sh
source "${BASH_SOURCE[0]%/*}/prep_vol.sh"
# shellcheck source=prep_auth.sh
source "${BASH_SOURCE[0]%/*}/prep_auth.sh"
# shellcheck source=check_prep.sh
source "${BASH_SOURCE[0]%/*}/check_prep.sh"

#######################################
# Initialize/reuse HOME, retain/enroll auth, then check offline readiness.
# Globals: checked DOCKER/DOCKER_ARCH/RUNTIME_IMAGE_ID from dependency setup;
#   PREP_VOLUME (published on success, cleared on failure), LAB_SETUP_BRIEF.
# Arguments: trusted project directory. Outputs: progress and masked prompt.
# Returns: 0 complete, 1 stopped. Existing/partial state is never rolled back.
# No image selection/build/pull, replacement, retry, reset or live request.
# Native enrollment requires separate approval; tests use synthetic state only.
#######################################
prepare_prep_profile() {
  local project="${1:-}"
  PREP_VOLUME=''
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if lab_work 'Private HOME' prepare_prep_volume "${project}" \
    && prepare_prep_auth "${project}" install \
    && lab_work 'Offline readiness' check_prep_runtime "${project}"; then
    lab_status PASS \
      'Private profile ready offline in the workshop Docker volume.'
    lab_status INFO 'Provider access and lab readiness remain unverified.'
    return 0
  fi
  PREP_VOLUME=''
  if [[ "${LAB_SETUP_BRIEF:-0}" != 1 ]]; then
    lab_status FAIL \
      'Private profile preparation stopped; existing/partial state kept.'
    lab_print '%s\n' 'No credential replacement, retry or reset attempted.' >&2
  fi
  return 1
}

#######################################
# Check live access; only typed live failure permits one optional replacement.
# Globals: DOCKER/DOCKER_ARCH/RUNTIME_IMAGE_ID/PREP_VOLUME, LAB_SETUP_BRIEF.
# Arguments: trusted project directory. Outputs: warnings and masked prompt.
# Returns: 0 verified, otherwise delegated check/enrollment status; 1 bad args.
# At most two live attempts; no retry without successful explicit replacement.
# Caller must complete private profile setup first. No rollback or reset.
#######################################
prepare_prep_live() {
  local project="${1:-}" status
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
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
  if (( status != 3 )) || [[ ! -t 0 ]]; then
    return "${status}"
  fi
  LAB_SETUP_BRIEF=0 lab_print '%s\n' \
    '[INFO] This failure does not mean your key is wrong.'
  if prepare_prep_auth "${project}" replace; then
    :
  else
    return $?
  fi
  lab_print '%s\n' \
    '[WARN] Retrying once with the new key. This may use paid credits.' >&2
  lab_work 'Provider response and log' check_prep_live "${project}"
}
