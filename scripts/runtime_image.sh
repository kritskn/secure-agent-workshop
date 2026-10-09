#!/bin/bash
# Shared Pi dependency image wrapper; no container startup or CLI routing.

# shellcheck source=dependency_image.sh
source "${BASH_SOURCE[0]%/*}/dependency_image.sh"

#######################################
# Prepare/reuse the Pi dependency image using only its public build inputs.
# Globals: DOCKER, DOCKER_ARCH; RUNTIME_IMAGE_ID (validated result).
# Arguments: Trusted project directory, optional prepare|inspect (internal).
# Outputs: Fixed status/guidance.
# Returns: 0 on verified image, 1 on refusal; empty result on failure.
#######################################
prepare_runtime_image() {
  RUNTIME_IMAGE_ID=''
  RUNTIME_IMAGE_ID="$(prepare_dependency_image "$1" runtime '' '' \
    "${2:-prepare}")" || return
  lab_print '[PASS] Runtime image verified: %s\n' "${RUNTIME_IMAGE_ID}"
}

# Cached lookup only. Same globals/output above; exactly one project argument.
# Returns: 0 verified, 1 refused/missing. Never builds or loads build helpers.
lookup_runtime_image() {
  RUNTIME_IMAGE_ID=''
  if (( $# != 1 )); then
    return 1
  fi
  prepare_runtime_image "$1" inspect
}
