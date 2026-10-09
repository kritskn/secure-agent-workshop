#!/bin/bash
# Internal stock image caching; no container creation or infrastructure startup.

# shellcheck source=openshell_stock_data.sh
source "${BASH_SOURCE[0]%/*}/openshell_stock_data.sh"

#######################################
# Cache/reuse all three reviewed Linux stock artifacts, never replace/delete.
# Globals: DOCKER, DOCKER_ARCH from preflight; OPENSHELL_STOCK_IMAGES (result).
# Arguments: Selected OpenShell version, optional prepare|inspect (internal).
# Outputs: Coarse status/guidance. Returns: 0 verified, 1 refused.
# Requires trusted source/daemon without concurrent administrator mutations.
# Installation checks only; image identity is not native lab qualification.
#######################################
prepare_openshell_stock() {
  local metadata role manifest config repo reference inventory row present
  local details mode="${2:-prepare}"
  local images=() format='{{.Id}}|{{.Os}}|{{.Architecture}}'
  OPENSHELL_STOCK_IMAGES=()
  if [[ ! "${mode}" =~ ^(prepare|inspect)$ ]]; then
    lab_status FAIL 'Unknown stock image operation; no action.'
    return 1
  fi
  if [[ "${DOCKER_ARCH:-}" != 'amd64' && "${DOCKER_ARCH:-}" != 'arm64' ]] \
    || [[ "${DOCKER[0]:-}" != env ]]; then
    lab_status FAIL 'Run Docker preflight before stock image caching.'
    return 1
  fi
  if ! metadata="$(openshell_stock_metadata "$1" "${DOCKER_ARCH}")"; then
    return 1
  fi
  local engine=(env -u DOCKER_DEFAULT_PLATFORM "${DOCKER[@]}")
  while IFS='|' read -r role manifest config; do
    repo="ghcr.io/nvidia/openshell/${role}"
    reference="${repo}@sha256:${manifest}"
    if ! inventory="$("${engine[@]}" image ls --all --digests \
      --format '{{.Repository}}@{{.Digest}}' --filter "reference=${repo}" \
      2>/dev/null)"; then
      lab_print '%s\n' \
        '[FAIL] Stock inventory failed; cached images preserved.' >&2
      return 1
    fi
    present=''
    while IFS= read -r row; do
      if [[ -z "${row}" ]]; then
        continue
      fi
      if [[ "${row}" != "${repo}@<none>" && \
        ( "${row}" != "${repo}@"* \
          || ! "${row#"${repo}@"}" =~ ^sha256:[0-9a-f]{64}$ ) ]]; then
        lab_status FAIL 'Stock inventory refused; images preserved.'
        return 1
      fi
      if [[ "${row}" == "${reference}" ]]; then
        present=1
      fi
    done <<< "${inventory}"
    if [[ -z "${present}" ]]; then
      if [[ "${mode}" == inspect ]]; then
        lab_print '[FAIL] Stock %s is not cached; run setup.\n' "${role}" >&2
        return 1
      fi
      if ! "${engine[@]}" pull --platform "linux/${DOCKER_ARCH}" \
        "${reference}" >/dev/null 2>&1; then
        lab_print '[FAIL] OpenShell %s pull failed; partial cache kept.\n' \
          "${role}" >&2
        return 1
      fi
    fi
    if ! details="$("${engine[@]}" image inspect --format "${format}" \
      "${reference}" 2>/dev/null)"; then
      lab_print '[FAIL] Cannot inspect stock %s; images preserved.\n' \
        "${role}" >&2
      return 1
    fi
    # Classic/containerd stores report the config/manifest digest as image ID.
    if [[ "${details}" != "sha256:${config}|linux|${DOCKER_ARCH}" \
      && "${details}" != "sha256:${manifest}|linux|${DOCKER_ARCH}" ]]; then
      lab_print '[FAIL] Stock %s identity/platform mismatch; preserved.\n' \
        "${role}" >&2
      return 1
    fi
    images+=("${reference}")
    lab_print '[PASS] OpenShell stock %s cached (linux/%s).\n' \
      "${role}" "${DOCKER_ARCH}"
  done <<< "${metadata}"
  OPENSHELL_STOCK_IMAGES=("${images[@]}")
  lab_print '[INFO] Cached %s stock artifacts; infrastructure not started.\n' \
    "${#OPENSHELL_STOCK_IMAGES[@]}"
}

# Cached lookup only. Same globals/output above; exactly one version argument.
# Returns: 0 all verified, 1 refused/missing. Never pulls or starts services.
lookup_openshell_stock() {
  OPENSHELL_STOCK_IMAGES=()
  if (( $# != 1 )); then
    return 1
  fi
  prepare_openshell_stock "$1" inspect
}
