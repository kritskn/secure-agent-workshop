#!/bin/bash
# Build public dependency images with Docker cache, or inspect without building.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

# Globals: DOCKER, DOCKER_ARCH.
# Args: project, role, Pi tag, prepare|inspect, optional cache|no-cache.
# Outputs: image ID on stdout; diagnostics on stderr.
# Returns: tool status or 1.
# Trusted checkout/daemon; no concurrent builds, edits or admin mutation.
prepare_dependency_image() {
  local project="$1" role="$2" file tag inventory details
  local image_id format title recipe mode="${4:-prepare}" base="$3"
  local files=() directories=(scripts docker) pass pattern cache="${5:-cache}"
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
      ;;
    *)
      lab_status FAIL 'Unknown internal image role.'
      return 1
      ;;
  esac
  files+=(scripts/setup_guest_pi.py scripts/runtime_config.json)
  if [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]] \
    || [[ "${DOCKER[0]:-}" != env || ! "${mode}" =~ ^(prepare|inspect)$ \
      || ! "${cache}" =~ ^(cache|no-cache)$ ]]; then
    lab_status FAIL 'Run Docker preflight; select prepare or inspect.'
    return 1
  fi
  local engine=(env -u BUILDX_BUILDER -u BUILDKIT_HOST \
    -u DOCKER_DEFAULT_PLATFORM DOCKER_BUILDKIT=1 "${DOCKER[@]}")
  if [[ "${mode}" == inspect ]]; then
    files=() directories=(scripts)
  fi
  for file in "${directories[@]}"; do
    if [[ -L "${project}/${file}" ]]; then
      lab_status FAIL "Symlinked ${role} source directory: ${file}"
      return 1
    fi
  done
  for file in ${files[@]+"${files[@]}"} "scripts/${role}_image.tmpl"; do
    if [[ ! -f "${project}/${file}" || ! -r "${project}/${file}" \
      || ! -s "${project}/${file}" || -L "${project}/${file}" ]]; then
      lab_status FAIL "Missing or unsafe ${role} source: ${file}"
      return 1
    fi
  done
  tag="secagent-${role}:local-${DOCKER_ARCH}"
  if ! inventory="$("${engine[@]}" image ls --all \
    --format '{{.Repository}}:{{.Tag}}' --filter "reference=${tag}" \
    2>/dev/null)" || [[ -n "${inventory}" && "${inventory}" != "${tag}" ]]; then
    lab_status FAIL 'Image inventory refused; images preserved.'
    return 1
  fi
  format="$(< "${project}/scripts/${role}_image.tmpl")"
  # Validate existing ownership before replacement and the result after build.
  for pass in before after; do
    if [[ -n "${inventory}" ]]; then
      if ! details="$("${engine[@]}" image inspect --format "${format}" \
        "${tag}" 2>/dev/null)"; then
        lab_status FAIL "Cannot inspect ${role} image; images preserved."
        return 1
      fi
      image_id="${details%%|*}"
      pattern="^sha256:[0-9a-f]{64}\\|linux\\|${DOCKER_ARCH}"
      pattern+='\|owned\|ok\|ok\|ok$'
      if [[ "${mode}" == prepare && "${pass}" == before ]]; then
        pattern='^sha256:[0-9a-f]{64}\|[^|]*\|[^|]*\|owned\|'
      fi
      if [[ ! "${details}" =~ ${pattern} ]]; then
        lab_status FAIL "${title} image validation failed: ${tag}; preserved."
        return 1
      fi
    elif [[ "${mode}" == inspect ]]; then
      lab_status FAIL "${role} image is not cached. Run setup."
      return 1
    fi
    if [[ "${mode}" == inspect || "${pass}" == after ]]; then
      printf '%s\n' "${image_id}"
      return 0
    fi
    # shellcheck source=dependency_build.sh
    source "${BASH_SOURCE[0]%/*}/dependency_build.sh" || return
    build_dependency_image "${project}" "${recipe}" "${tag}" \
      "${role}" "${base}" "${title}" "${cache}" "${files[@]}" || return
    inventory="${tag}"
  done
}
