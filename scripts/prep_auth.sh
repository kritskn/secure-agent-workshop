#!/bin/bash
# Docker transport for the existing private Ollama enrollment policy.
# shellcheck source=prep_inspect.sh
source "${BASH_SOURCE[0]%/*}/prep_inspect.sh"

#######################################
# Retain or enroll a credential after checking its catalog and private path.
# Initializer/offline checks own the full HOME scan; no concurrent state edits.
# Globals: DOCKER, DOCKER_ARCH, RUNTIME_IMAGE_ID, PREP_VOLUME from preparation;
#   BASH (the running interpreter, reused for reader and consumer).
# Arguments: trusted project directory, optional install|replace.
# Outputs: fixed status/errors, masked terminal prompt. No online validation.
# Returns: 0 retained/saved, 3 declined replacement, 1 refusal/failure.
# Trusted checkout/daemon; no concurrent setup or state edits.
#######################################
prepare_prep_auth() {
  local project="${1:-}" mode="${2:-install}" file status source command=()
  if (( $# < 1 || $# > 2 )) || [[ ! "${mode}" =~ ^(install|replace)$ ]] \
    || [[ "${PREP_VOLUME:-}" != secagent-vol || "${DOCKER[0]:-}" != env ]] \
    || [[ ! "${RUNTIME_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || [[ "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ]]; then
    lab_print '%s\n' \
      '[FAIL] Prepare the runtime and private HOME before enrollment.' >&2
    return 1
  fi
  for file in setup_guest_auth.py read_ollama_token.sh read_masked_token.sh \
    runtime_image.tmpl prep_vol.tmpl; do
    if [[ -L "${project}/scripts" || -L "${project}/scripts/${file}" \
      || ! -f "${project}/scripts/${file}" \
      || ! -r "${project}/scripts/${file}" \
      || ! -s "${project}/scripts/${file}" ]]; then
      lab_status FAIL 'Missing or unsafe public enrollment input.'
      return 1
    fi
  done
  inspect_prep_image "${project}" || return
  inspect_prep_volume "${project}" || return
  # Only public Python source is an argument. The key is exclusively stdin.
  source="$(< "${project}/scripts/setup_guest_auth.py")" || return
  [[ -n "${source}" ]] || return 1
  command=("${DOCKER[@]}" run --rm --pull never --name secagent-prep-auth
    --label org.secagent.owner=secure-agent-workshop
    --label org.secagent.role=preparation-enrollment
    --platform "linux/${DOCKER_ARCH}" --network none --read-only
    --user 1000:1000
    --cap-drop ALL --security-opt no-new-privileges
    --pids-limit 32 --memory 256m --cpus 1 --workdir /tmp
    --mount 'type=volume,src=secagent-vol,dst=/home/lab-user,volume-nocopy'
    -i "${RUNTIME_IMAGE_ID}" python3 -I -B -c "${source}")
  if "${command[@]}" container-check </dev/null >/dev/null 2>&1; then
    if [[ "${mode}" == install ]]; then
      lab_print '%s\n' '[PASS] Existing private Ollama credential retained.'
      return 0
    fi
  else
    status=$?
    if (( status != 10 )) || [[ "${mode}" == replace ]]; then
      lab_print '%s\n' \
        '[FAIL] Credential/profile check failed; state preserved.' >&2
      return 1
    fi
  fi
  # Keep the prompt visible, but never emit raw Docker/helper diagnostics.
  if "${BASH}" "${project}/scripts/read_ollama_token.sh" "${mode}" \
    "${BASH}" -c '"$@" >/dev/null 2>&1' prep-auth-write \
    "${command[@]}" "container-${mode}"; then
    lab_print '%s\n' \
      '[PASS] Ollama credential saved privately (not checked online).'
    return 0
  else
    return $?
  fi
}
