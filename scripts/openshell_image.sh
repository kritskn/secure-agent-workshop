#!/bin/bash
# Linux OpenShell CLI/operator image wrapper; no gateway or container startup.

# shellcheck source=dependency_image.sh
source "${BASH_SOURCE[0]%/*}/dependency_image.sh"

#######################################
# Prepare/reuse the OpenShell CLI image using only its public build inputs.
# Globals: DOCKER, DOCKER_ARCH; OPENSHELL_IMAGE_ID (validated result).
# Arguments: Trusted project directory, optional prepare|inspect (internal).
# Outputs: Fixed status/guidance.
# Returns: 0 on verified image, 1 on refusal; empty result on failure.
#######################################
prepare_openshell_image() {
  OPENSHELL_IMAGE_ID=''
  OPENSHELL_IMAGE_ID="$(prepare_dependency_image "$1" openshell '' '' \
    "${2:-prepare}")" || return
  lab_print '[PASS] OpenShell image verified: %s\n' "${OPENSHELL_IMAGE_ID}"
}

# Cached lookup only. Same globals/output above; exactly one project argument.
# Returns: 0 verified, 1 refused/missing. Never builds or loads build helpers.
lookup_openshell_image() {
  OPENSHELL_IMAGE_ID=''
  if (( $# != 1 )); then
    return 1
  fi
  prepare_openshell_image "$1" inspect
}
