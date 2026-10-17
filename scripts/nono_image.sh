#!/bin/bash
# Reuse the actual prepared Pi image as the nono dependency layer's local base.

# shellcheck source=dependency_image.sh
source "${BASH_SOURCE[0]%/*}/dependency_image.sh"

#######################################
# Build nono from the selected Pi runtime, or inspect cached nono.
# Globals: DOCKER, DOCKER_ARCH; RUNTIME_IMAGE_ID from prepare_runtime_image;
#   NONO_IMAGE_ID (validated result, empty on failure).
# Arguments: Project, optional prepare|inspect and cache|no-cache.
# Outputs: Fixed status/guidance.
# Returns: 0 verified, 1 refused. No base build/pull, startup or configuration.
# Caller must first prepare/look up the selected Pi runtime on the same daemon.
#######################################
prepare_nono_image() {
  local project="$1" record tag tagged format
  local pattern="^${RUNTIME_IMAGE_ID:-invalid}"
  NONO_IMAGE_ID=''
  if [[ ! "${RUNTIME_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]] \
    || [[ "${DOCKER[0]:-}" != env ]]; then
    lab_status FAIL 'Prepare the Pi runtime before the nono image.'
    return 1
  fi
  local engine=(env -u BUILDX_BUILDER -u BUILDKIT_HOST \
    -u DOCKER_DEFAULT_PLATFORM DOCKER_BUILDKIT=1 "${DOCKER[@]}")
  pattern+="\|linux\|${DOCKER_ARCH}\|owned\|ok\|ok\|ok$"
  if [[ -L "${project}/scripts" \
    || -L "${project}/scripts/runtime_image.tmpl" \
    || ! -s "${project}/scripts/runtime_image.tmpl" ]]; then
    lab_status FAIL 'Missing or unsafe Pi image verification template.'
    return 1
  fi
  format="$(< "${project}/scripts/runtime_image.tmpl")"
  if ! record="$("${engine[@]}" image inspect --format "${format}" \
    "${RUNTIME_IMAGE_ID}" 2>/dev/null)" \
    || [[ ! "${record}" =~ ${pattern} ]]; then
    lab_print '%s\n' \
      '[FAIL] Pi base identity/configuration refused; preserved.' >&2
    return 1
  fi
  tag="secagent-runtime:local-${DOCKER_ARCH}"
  # BuildKit consumes a local tag, not a registry-style config digest.
  # Recheck the tag binding; trusted daemon/no concurrent mutation is required.
  if ! tagged="$("${engine[@]}" image inspect --format '{{.Id}}' "${tag}" \
    2>/dev/null)" || [[ "${tagged}" != "${RUNTIME_IMAGE_ID}" ]]; then
    lab_print '%s\n' \
      '[FAIL] Pi base tag changed or absent; no nono image action.' >&2
    return 1
  fi
  NONO_IMAGE_ID="$(prepare_dependency_image "${project}" nono \
    "${tag}" "${2:-prepare}" "${3:-cache}")" || return
  lab_print '[PASS] nono image verified: %s\n' "${NONO_IMAGE_ID}"
}

# Cached lookup only. Same globals/output above; exactly one project argument.
# Returns: 0 verified with a usable Pi base, 1 refused/missing; no builds.
lookup_nono_image() {
  NONO_IMAGE_ID=''
  if (( $# != 1 )); then
    return 1
  fi
  prepare_nono_image "$1" inspect
}
