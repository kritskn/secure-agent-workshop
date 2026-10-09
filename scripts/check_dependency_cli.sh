#!/bin/bash
# Offline dependency CLI probes only; not sandbox or lab qualification.
# shellcheck source=runtime_image.sh
source "${BASH_SOURCE[0]%/*}/runtime_image.sh"
# shellcheck source=nono_image.sh
source "${BASH_SOURCE[0]%/*}/nono_image.sh"
# shellcheck source=openshell_image.sh
source "${BASH_SOURCE[0]%/*}/openshell_image.sh"

#######################################
# Look up the selected cached image and require its exact CLI version output.
# Globals: DOCKER, DOCKER_ARCH from preflight; lookup helpers refresh image IDs.
# Arguments: trusted project directory, nono|openshell, selected stable version.
# Outputs: fixed status/errors, never raw CLI output. Returns: 0 pass, 1 fail.
# No builds, pulls, HOME/socket mounts, credential reads or infrastructure.
# Trusted checkout/daemon, no concurrent setup; secagent-prep-check is reserved.
#######################################
check_dependency_cli() {
  local project="${1:-}" role="${2:-}" version="${3:-}" image output
  local number='(0|[1-9][0-9]*)'
  local pattern="^${number}\\.${number}\\.${number}$"
  if (( $# != 3 || ${#version} > 64 )) \
    || [[ -z "${project}" || ! "${version}" =~ ${pattern} ]]; then
    lab_status FAIL 'Expected project, CLI role and stable version.'
    return 1
  fi
  case "${role}" in
    nono)
      lookup_runtime_image "${project}" >/dev/null || return
      lookup_nono_image "${project}" >/dev/null || return
      image="${NONO_IMAGE_ID}"
      ;;
    openshell)
      lookup_openshell_image "${project}" >/dev/null || return
      image="${OPENSHELL_IMAGE_ID}"
      ;;
    *)
      lab_print '%s\n' \
        '[FAIL] Only nono/OpenShell CLI version checks supported.' >&2
      return 1
      ;;
  esac
  # Dedicated images already have the matching exec-form CLI ENTRYPOINT.
  # Share the identified check-container name for sequential checks/reset.
  if ! output="$("${DOCKER[@]}" run --rm --pull never \
    --name secagent-prep-check \
    --label org.secagent.owner=secure-agent-workshop \
    --label org.secagent.role=preparation-check \
    --platform "linux/${DOCKER_ARCH}" --network none --read-only \
    --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 32 --memory 256m --cpus 1 --workdir /tmp \
    "${image}" --version </dev/null 2>/dev/null)"; then
    lab_print '[FAIL] %s CLI version probe failed; cache preserved.\n' \
      "${role}" >&2
    return 1
  fi
  if [[ "${output}" != "${role} ${version}" ]]; then
    lab_status FAIL "${role} CLI version mismatch; cache preserved."
    return 1
  fi
  lab_status PASS "${role} CLI version ${version} verified offline."
  lab_status INFO 'Sandbox enforcement and lab readiness unverified.'
}
