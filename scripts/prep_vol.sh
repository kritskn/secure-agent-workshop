#!/bin/bash
# Private preparation HOME creation/reuse; reset and enrollment are separate.
# shellcheck source=prep_inspect.sh
source "${BASH_SOURCE[0]%/*}/prep_inspect.sh"

#######################################
# Create or reuse the reserved volume and initialize HOME from public assets.
# Globals: DOCKER, DOCKER_ARCH; RUNTIME_IMAGE_ID from prepare_runtime_image;
#   PREP_VOLUME (validated result, empty on failure).
# Arguments: Trusted project directory. Outputs: Fixed status/guidance.
# Returns: 0 initialized/reused, 1 refused. No concurrent setup or state edits.
#######################################
prepare_prep_volume() {
  local project="$1" file inventory found='' name='secagent-vol'
  local assets=(scripts/runtime_config.json agents/pi/settings.json
    agents/pi/models.json agents/pi/extensions/observer.ts)
  PREP_VOLUME=''
  if [[ ! "${RUNTIME_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]] \
    || [[ "${DOCKER[0]:-}" != env ]]; then
    lab_status FAIL 'Prepare the Pi runtime before private HOME.'
    return 1
  fi
  for file in scripts agents agents/pi agents/pi/extensions; do
    if [[ -L "${project}/${file}" ]]; then
      lab_status FAIL 'Symlinked profile source directory; refused.'
      return 1
    fi
  done
  for file in "${assets[@]}" scripts/runtime_image.tmpl \
    scripts/prep_vol.tmpl; do
    if [[ ! -f "${project}/${file}" || ! -r "${project}/${file}" \
      || ! -s "${project}/${file}" || -L "${project}/${file}" ]]; then
      lab_status FAIL "Missing or unsafe public profile input: ${file}"
      return 1
    fi
  done
  inspect_prep_image "${project}" || return
  if ! inventory="$("${DOCKER[@]}" volume ls --format '{{.Name}}' \
    --filter "name=${name}" 2>/dev/null)"; then
    lab_status FAIL 'Volume inventory failed; no changes attempted.'
    return 1
  fi
  while IFS= read -r file; do
    if [[ "${file}" == "${name}" ]]; then
      found=1
    fi
  done <<< "${inventory}"
  if [[ -z "${found}" ]]; then
    if ! "${DOCKER[@]}" volume create --driver local \
      --label org.secagent.owner=secure-agent-workshop \
      --label org.secagent.role=preparation-home \
      --label org.secagent.schema=1 "${name}" >/dev/null 2>&1; then
      lab_status FAIL 'Volume creation failed; partial state kept.'
      return 1
    fi
  fi
  inspect_prep_volume "${project}" || return
  if ! (set -o pipefail
    COPYFILE_DISABLE=1 tar --format=ustar --no-xattrs -C "${project}" \
      -cf - "${assets[@]}" 2>/dev/null \
      | "${DOCKER[@]}" run --rm --pull never --name secagent-prep-init \
        --label org.secagent.owner=secure-agent-workshop \
        --label org.secagent.role=preparation-initializer \
        --platform "linux/${DOCKER_ARCH}" \
        --network none --read-only --user 0:0 --cap-drop ALL \
        --pids-limit 32 --memory 256m --cpus 1 \
        --cap-add CHOWN --cap-add SETUID --cap-add SETGID \
        --security-opt no-new-privileges --workdir /tmp \
        --tmpfs /tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777 \
        --mount "type=volume,src=${name},dst=/home/lab-user,volume-nocopy" \
        -i "${RUNTIME_IMAGE_ID}" python3 -I -B -c \
        'import runpy, sys; \
module = runpy.run_path("/opt/secagent/preparation/setup_guest_pi.py"); \
module["initialize_container_volume"](sys.stdin.buffer)' \
        >/dev/null 2>&1); then
    lab_print '%s\n' '[FAIL] HOME initialization failed; partial state kept.' \
      'No reset or ownership repair attempted; review state before retry.' >&2
    return 1
  fi
  # Validated handoff to callers, not a display label.
  # shellcheck disable=SC2034
  PREP_VOLUME="${name}"
  lab_status PASS \
    'Private preparation HOME ready in the workshop Docker volume.'
}
