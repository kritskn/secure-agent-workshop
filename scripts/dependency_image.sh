#!/bin/bash
# Fingerprint and verify dependency images; build only in prepare mode.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"
# No concurrent edits. Globals: DOCKER, DOCKER_ARCH. Args: project, role,
# Pi tag/ID, prepare|inspect (default prepare). Prints ID/errors; returns 0/1.
prepare_dependency_image() {
  local project="$1" role="$2" file record digest tag inventory details
  local image_id format title recipe mode="${5:-prepare}" base=''
  local files=() directories=(scripts docker) hash=(sha256sum)
  case "${role}" in
    runtime)
      title='Runtime' recipe='docker/pi.Dockerfile'
      files+=("${recipe}" scripts/prepare_guest.py)
      ;;
    openshell)
      title='OpenShell' recipe='docker/openshell.Dockerfile'
      files+=("${recipe}" scripts/prepare_openshell.py)
      ;;
    nono)
      title='nono' recipe='docker/nono.Dockerfile'
      files+=("${recipe}" scripts/prepare_nono.py scripts/prepare_openshell.py)
      base="$3"
      ;;
    *)
      lab_status FAIL 'Unknown internal image role.'
      return 1
      ;;
  esac
  files+=(scripts/setup_guest_pi.py scripts/runtime_config.json)
  if [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]] \
    || [[ "${DOCKER[0]:-}" != env || ! "${mode}" =~ ^(prepare|inspect)$ ]]; then
    lab_status FAIL 'Run Docker preflight; select prepare or inspect.'
    return 1
  fi
  local engine=(env -u BUILDX_BUILDER -u BUILDKIT_HOST \
    -u DOCKER_DEFAULT_PLATFORM DOCKER_BUILDKIT=1 "${DOCKER[@]}")
  for file in "${directories[@]}"; do
    if [[ -L "${project}/${file}" ]]; then
      lab_status FAIL "Symlinked ${role} source directory: ${file}"
      return 1
    fi
  done
  for file in "${files[@]}" "scripts/${role}_image.tmpl"; do
    if [[ ! -f "${project}/${file}" || ! -r "${project}/${file}" \
      || ! -s "${project}/${file}" || -L "${project}/${file}" ]]; then
      lab_status FAIL "Missing or unsafe ${role} source: ${file}"
      return 1
    fi
  done
  if ! command -v sha256sum >/dev/null; then
    hash=(shasum -a 256)
  fi
  if ! record="$(set -o pipefail; cd -- "${project}" \
    && "${hash[@]}" "${files[@]}" 2>/dev/null | "${hash[@]}" 2>/dev/null)"; then
    lab_status FAIL 'Source hashing needs working sha256sum/shasum.'
    return 1
  fi
  if [[ "${role}" == nono ]]; then
    record="$(printf '%s\n' "${record%% *}" "$4" | "${hash[@]}")" || return
  fi
  digest="${record%% *}"
  if [[ ! "${digest}" =~ ^[0-9a-f]{64}$ ]]; then
    lab_status FAIL "Invalid ${role} source digest; no image action."
    return 1
  fi
  tag="secagent-${role}:src-${digest}-${DOCKER_ARCH}"
  if ! inventory="$("${engine[@]}" image ls --all \
    --format '{{.Repository}}:{{.Tag}}' --filter "reference=${tag}" \
    2>/dev/null)" || [[ -n "${inventory}" && "${inventory}" != "${tag}" ]]; then
    lab_status FAIL 'Image inventory refused; images preserved.'
    return 1
  fi
  if [[ -z "${inventory}" ]]; then
    if [[ "${mode}" == inspect ]]; then
      lab_status FAIL "${role} image is not cached. Run setup."
      return 1
    fi
    # shellcheck source=dependency_build.sh
    source "${BASH_SOURCE[0]%/*}/dependency_build.sh" || return
    build_dependency_image "${project}" "${recipe}" "${tag}" \
      "${digest}" "${base}" "${title}" "${files[@]}" || return
  fi
  format="$(< "${project}/scripts/${role}_image.tmpl")"
  if ! details="$("${engine[@]}" image inspect --format "${format}" "${tag}" \
    2>/dev/null)"; then
    lab_status FAIL "Cannot inspect ${role} image; images preserved."
    return 1
  fi
  image_id="${details%%|*}"
  if [[ ! "${image_id}" =~ ^sha256:[0-9a-f]{64}$ ]] || [[ "${details}" != \
    "${image_id}|linux|${DOCKER_ARCH}|${digest}|ok|ok|ok" ]]; then
    lab_status FAIL "${title} image mismatch; preserved, not replaced."
    return 1
  fi
  printf '%s\n' "${image_id}"
}
