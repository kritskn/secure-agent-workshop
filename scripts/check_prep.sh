#!/bin/bash
# Common Pi checks; provisioning, prompting and retries belong to no check mode.
# shellcheck source=prep_inspect.sh
source "${BASH_SOURCE[0]%/*}/prep_inspect.sh"

# Check offline readiness. Globals: checked DOCKER/arch/runtime ID.
# Args: project. Outputs: fixed status. Returns: 0 pass, 1 failure.
check_prep_runtime() {
  run_prep_check offline "$@"
}

# Explicit live request/log check, including offline prerequisites.
# Globals: checked DOCKER/arch/runtime ID. Args: project. Outputs: fixed status.
# Returns: 0 pass, 3 live failure, 1 prerequisites/transport failure; no retry.
check_prep_live() {
  run_prep_check live "$@"
}

#######################################
# Shared transport. Globals: DOCKER, DOCKER_ARCH, RUNTIME_IMAGE_ID.
# Args: offline|live, trusted project. Outputs/returns: as wrappers above.
# No image selection/build/pull, HOME repair, prompt or lab service startup.
# Trusted checkout/daemon; no concurrent setup or state edits.
#######################################
run_prep_check() {
  local mode="${1:-}" project="${2:-}" file source status entry=container
  local home_mount='type=volume,src=secagent-vol,dst=/home/lab-user'
  local network=(--network none)
  local assets=(scripts/prepare_guest.py scripts/setup_guest_pi.py
    scripts/setup_guest_auth.py agents/pi/settings.json agents/pi/models.json
    agents/pi/extensions/observer.ts scripts/runtime_config.json)
  if (( $# != 2 )) \
    || [[ -z "${project}" || ! "${mode}" =~ ^(offline|live)$ ]]; then
    lab_status FAIL 'Expected a check mode and preparation directory.'
    return 1
  fi
  if [[ "${mode}" == live ]]; then
    entry=container-live
    network=(--network bridge
      --tmpfs '/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777')
  else
    home_mount+=',readonly'
  fi
  home_mount+=',volume-nocopy'
  for file in scripts agents agents/pi agents/pi/extensions; do
    if [[ -L "${project}/${file}" ]]; then
      lab_status FAIL 'Symlinked checker source directory; refused.'
      return 1
    fi
  done
  for file in "${assets[@]}" scripts/check_guest.py; do
    if [[ ! -f "${project}/${file}" || ! -r "${project}/${file}" \
      || ! -s "${project}/${file}" || -L "${project}/${file}" ]]; then
      lab_status FAIL 'Missing or unsafe public checker input.'
      return 1
    fi
  done
  inspect_prep_image "${project}" || return
  inspect_prep_volume "${project}" || return
  # Public source is argv; the bundle is public stdin. Credentials stay inside.
  source="$(< "${project}/scripts/check_guest.py")" || return
  [[ -n "${source}" ]] || return 1
  if (
    COPYFILE_DISABLE=1 tar --format=ustar --no-xattrs -C "${project}" \
      -cf - "${assets[@]}" 2>/dev/null \
      | "${DOCKER[@]}" run --rm --pull never --name secagent-prep-check \
        --label org.secagent.owner=secure-agent-workshop \
        --label org.secagent.role=preparation-check \
        --platform "linux/${DOCKER_ARCH}" "${network[@]}" --read-only \
        --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
        --pids-limit 32 --memory 256m --cpus 1 --workdir /tmp \
        --mount "${home_mount}" \
        -i "${RUNTIME_IMAGE_ID}" python3 -I -B -c "${source}" "${entry}" \
        >/dev/null 2>&1
    # A tar failure must not become an eligible live retry, even if Docker is 3.
    local codes=("${PIPESTATUS[@]}")
    if (( codes[0] != 0 )); then
      exit 1
    fi
    exit "${codes[1]}"
  ); then
    if [[ "${mode}" == live ]]; then
      lab_status PASS 'Ollama response and fresh observer log verified.'
      lab_status INFO 'Lab readiness remains unverified.'
    else
      lab_status PASS 'Offline Node/npm/Pi and private profile passed.'
      lab_status INFO 'Provider access, observer execution and labs unverified.'
    fi
    return 0
  else
    status=$?
    if [[ "${mode}" == live ]] && (( status == 3 )); then
      lab_status FAIL 'Could not verify the Ollama response or activity log.'
      return 3
    fi
    lab_print '%s\n' \
      '[FAIL] Preparation prerequisite/transport check failed; state kept.' >&2
    return 1
  fi
}
