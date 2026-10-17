#!/bin/bash
# Docker transport for retained credentials and one verify-before-save attempt.
# shellcheck source=prep_inspect.sh
source "${BASH_SOURCE[0]%/*}/prep_inspect.sh"
# Retain a saved key or verify one candidate before saving it.
# Globals: DOCKER, DOCKER_ARCH, RUNTIME_IMAGE_ID, PREP_VOLUME, BASH;
#   PREP_AUTH_VERIFIED is set only after this invocation verifies and saves.
# Args: trusted project, optional install|replace. Output: masked prompt/status.
# Returns: 0 success, 5 no submission, 4 rejected, 3 live error; other failures.
prepare_prep_auth() {
  local project="${1:-}" mode="${2:-install}" file status source data
  local command=() inputs=() assets=(scripts/check_guest.py
    scripts/prepare_guest.py scripts/setup_guest_pi.py
    scripts/setup_guest_auth.py agents/pi/settings.json agents/pi/models.json
    agents/pi/extensions/observer.ts
    scripts/runtime_config.json)
  PREP_AUTH_VERIFIED=0
  if (( $# < 1 || $# > 2 )) || [[ ! "${mode}" =~ ^(install|replace)$ ]] \
    || [[ "${PREP_VOLUME:-}" != secagent-vol || "${DOCKER[0]:-}" != env ]] \
    || [[ ! "${RUNTIME_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]]; then
    lab_status FAIL 'Prepare the runtime and private HOME before enrollment.'
    return 1
  fi
  for file in scripts agents agents/pi agents/pi/extensions; do
    if [[ -L "${project}/${file}" ]]; then
      lab_status FAIL "Symlinked host source: ${project}/${file}; refused."
      return 1
    fi
  done
  for file in "${assets[@]}" scripts/read_ollama_token.sh \
    scripts/read_masked_token.sh scripts/runtime_image.tmpl \
    scripts/prep_vol.tmpl; do
    if [[ -L "${project}/${file}" || ! -f "${project}/${file}" \
      || ! -r "${project}/${file}" || ! -s "${project}/${file}" ]]; then
      lab_status FAIL 'Missing or unsafe public enrollment input.'
      return 1
    fi
  done
  inspect_prep_image "${project}" || return
  inspect_prep_volume "${project}" || return
  source="$(< "${project}/scripts/setup_guest_auth.py")" || return
  [[ -n "${source}" ]] || return 1
  command=("${DOCKER[@]}" run --rm --pull never --name secagent-prep-auth
    --label org.secagent.owner=secure-agent-workshop
    --label org.secagent.role=preparation-enrollment
    --platform "linux/${DOCKER_ARCH}" --read-only --user 1000:1000
    --cap-drop ALL --security-opt no-new-privileges
    --pids-limit 32 --memory 256m --cpus 1 --workdir /tmp
    --mount 'type=volume,src=secagent-vol,dst=/home/lab-user,volume-nocopy')
  if "${command[@]}" --network none -i "${RUNTIME_IMAGE_ID}" \
    python3 -I -B -c "${source}" container-check \
    </dev/null >/dev/null 2>&1; then
    if [[ "${mode}" == install ]]; then
      lab_status PASS 'Existing private Ollama credential retained.'
      return 0
    fi
  else
    status=$?
    if (( status != 10 )) || [[ "${mode}" == replace ]]; then
      lab_status FAIL 'Credential/profile check failed; state preserved.'
      return 1
    fi
  fi
  for file in "${assets[@]}"; do
    data="$(cat "${project}/${file}" && printf .)" || return 1
    inputs+=("${data%.}")
  done
  LAB_SETUP_BRIEF=0 lab_print '%s\n' \
    '[WARN] Candidate verification uses quota, may cost, and writes a log.' \
    '[INFO] The key is saved only after response and log verification.' >&2
  if "${BASH}" "${project}/scripts/read_ollama_token.sh" "${mode}" \
    "${BASH}" -c '"$@" >/dev/null 2>&1' prep-auth-verify \
    "${command[@]}" --network bridge \
    --tmpfs '/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777' \
    -i "${RUNTIME_IMAGE_ID}" python3 -I -B -c "${source}" \
    "container-${mode}" "${inputs[@]}"; then
    # shellcheck disable=SC2034 # Consumed by the setup/live coordinator.
    PREP_AUTH_VERIFIED=1
    lab_status PASS 'Verified Ollama credential saved privately.'
    return 0
  else
    status=$?
  fi
  return "${status}"
}
