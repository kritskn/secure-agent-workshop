#!/bin/bash
# Dependency-only setup stage; participant CLI routing remains separate.
# shellcheck source=lab_work.sh
source "${BASH_SOURCE[0]%/*}/lab_work.sh"
# shellcheck source=docker_host.sh
source "${BASH_SOURCE[0]%/*}/docker_host.sh"
# shellcheck source=load_prep_versions.sh
source "${BASH_SOURCE[0]%/*}/load_prep_versions.sh"
# shellcheck source=check_dependency_cli.sh
source "${BASH_SOURCE[0]%/*}/check_dependency_cli.sh"
# shellcheck source=openshell_stock.sh
source "${BASH_SOURCE[0]%/*}/openshell_stock.sh"

#######################################
# Prepare dependency caches, then verify nono/OpenShell CLI versions offline.
# Globals: publishes checked DOCKER/DOCKER_ARCH and existing helper image IDs,
#   pins and OPENSHELL_STOCK_IMAGES; LAB_SETUP_BRIEF hides success details.
#   Image/pin results clear on failure.
# Arguments: trusted project directory. Outputs: progress and fixed results.
# Returns: 0 complete, 1 stopped. Completed image/cache work is always retained.
# No private HOME, enrollment, model request, lab service or cleanup action.
# Real invocation may build/pull dependencies; tests use mocks only.
#######################################
prepare_prep_dependencies() {
  local project="${1:-}"
  RUNTIME_IMAGE_ID='' NONO_IMAGE_ID='' OPENSHELL_IMAGE_ID=''
  PI_VERSION='' NONO_VERSION='' OPENSHELL_VERSION=''
  OPENSHELL_STOCK_IMAGES=()
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if lab_work 'Docker' check_docker_host \
    && lab_work 'Pi runtime' prepare_runtime_image "${project}" \
    && lab_work 'Selected versions' load_prep_versions "${project}" \
    && lab_work 'nono' prepare_nono_image "${project}" \
    && lab_work 'OpenShell' prepare_openshell_image "${project}" \
    && lab_work 'Stock images' prepare_openshell_stock "${OPENSHELL_VERSION}" \
    && lab_work 'nono CLI' check_dependency_cli "${project}" nono \
      "${NONO_VERSION}" \
    && lab_work 'OpenShell CLI' check_dependency_cli "${project}" openshell \
      "${OPENSHELL_VERSION}"; then
    lab_print '%s\n' \
      '[PASS] Dependency cache ready; nono/OpenShell CLI checks passed.' \
      '[INFO] Private HOME, provider access and lab readiness not checked.'
    return 0
  fi
  RUNTIME_IMAGE_ID='' NONO_IMAGE_ID='' OPENSHELL_IMAGE_ID=''
  PI_VERSION='' NONO_VERSION='' OPENSHELL_VERSION=''
  OPENSHELL_STOCK_IMAGES=()
  if [[ "${LAB_SETUP_BRIEF:-0}" != 1 ]]; then
    lab_print '%s\n' \
      '[FAIL] Dependency preparation stopped; completed cache kept.' >&2
  fi
  return 1
}
