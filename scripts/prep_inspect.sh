#!/bin/bash
# Shared read-only preparation resource checks. No build, pull or repair.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Verify the selected runtime image identity and configuration without changes.
# Globals: DOCKER, DOCKER_ARCH, RUNTIME_IMAGE_ID from runtime preparation.
# Arguments: trusted project directory. Outputs: fixed errors to stderr.
# Returns: 0 exact runtime identity/configuration, 1 missing/unsafe/mismatched.
#######################################
inspect_prep_image() {
  local project="$1" file="$1/scripts/runtime_image.tmpl" format details pattern
  if [[ ! "${RUNTIME_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]] \
    || [[ "${DOCKER[0]:-}" != env ]]; then
    lab_status FAIL 'Checked Docker runtime identity required.'
    return 1
  fi
  if [[ -L "${project}/scripts" || -L "${file}" \
    || ! -f "${file}" || ! -r "${file}" || ! -s "${file}" ]]; then
    lab_status FAIL 'Missing or unsafe runtime inspection template.'
    return 1
  fi
  format="$(< "${file}")"
  pattern="^${RUNTIME_IMAGE_ID}\|linux\|${DOCKER_ARCH}"
  pattern+='\|[0-9a-f]{64}\|ok\|ok\|ok$'
  if ! details="$("${DOCKER[@]}" image inspect --format "${format}" \
    "${RUNTIME_IMAGE_ID}" 2>/dev/null)" \
    || [[ ! "${details}" =~ ${pattern} ]]; then
    lab_status FAIL 'Preparation image refused; existing state kept.'
    return 1
  fi
}

#######################################
# Verify the reserved private volume's ownership labels and local backend.
# Globals: DOCKER from preflight. Arguments: trusted project directory.
# Outputs: fixed errors to stderr. Returns: 0 owned local volume, 1 refused.
# Call after inspect_prep_image. Does not create an absent volume or read data.
#######################################
inspect_prep_volume() {
  local file="$1/scripts/prep_vol.tmpl" format details expected
  if [[ -L "$1/scripts" || -L "${file}" \
    || ! -f "${file}" || ! -r "${file}" || ! -s "${file}" ]]; then
    lab_status FAIL 'Missing or unsafe volume inspection template.'
    return 1
  fi
  format="$(< "${file}")"
  expected='secagent-vol|local|local|ok|'
  expected+='secure-agent-workshop|preparation-home|1'
  if ! details="$("${DOCKER[@]}" volume inspect --format "${format}" \
    secagent-vol 2>/dev/null)" || [[ "${details}" != "${expected}" ]]; then
    lab_status FAIL 'Volume ownership/options refused; state kept.'
    return 1
  fi
}
