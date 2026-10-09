#!/bin/bash
# Read-only identification of the exact disposable preparation resources.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Identify removable preparation resources, refusing unknown references.
# Globals: DOCKER from preflight. Arguments: none. Returns: 0 safe, 1 refused.
# Outputs: container|ID|status and volume|secagent-vol rows, or fixed stderr.
# Unknown container references or external volume backends stop cleanup.
#######################################
prep_reset_inventory() {
  local names refs volumes id record status options seen=$'\n'
  local owner='secure-agent-workshop' allowed=''
  local filter='name=^/secagent-prep-(init|auth|check)$'
  local states='^(created|exited|dead|running|restarting|paused)$'
  local format='{{.Id}}|{{.Name}}|'
  format+='{{with index .Config "Labels"}}{{index . "org.secagent.owner"}}|'
  format+='{{index . "org.secagent.role"}}{{end}}|{{.State.Status}}'
  if ! names="$("${DOCKER[@]}" container ls --all --no-trunc \
    --format '{{.ID}}' --filter "${filter}" 2>/dev/null)" \
    || ! refs="$("${DOCKER[@]}" container ls --all --no-trunc \
    --format '{{.ID}}' --filter volume=secagent-vol 2>/dev/null)" \
    || ! volumes="$("${DOCKER[@]}" volume ls --format '{{.Name}}' \
    --filter name=secagent-vol 2>/dev/null)"; then
    lab_status FAIL 'Reset inventory failed; cleanup halted.'
    return 1
  fi
  while IFS= read -r id; do
    if [[ -z "${id}" || "${seen}" == *$'\n'"${id}"$'\n'* ]]; then
      continue
    fi
    if [[ ! "${id}" =~ ^[0-9a-f]{64}$ ]] \
      || ! record="$("${DOCKER[@]}" container inspect --format "${format}" \
        "${id}" 2>/dev/null)"; then
      lab_status FAIL 'Container identity unavailable; cleanup halted.'
      return 1
    fi
    status="${record##*|}"
    allowed=''
    case "${record}" in
      "${id}|/secagent-prep-init|${owner}|preparation-initializer|${status}" \
      | "${id}|/secagent-prep-auth|${owner}|preparation-enrollment|${status}" \
      | "${id}|/secagent-prep-check|${owner}|preparation-check|${status}")
        allowed=1
        ;;
    esac
    if [[ -z "${allowed}" || ! "${status}" =~ ${states} ]]; then
      lab_status FAIL 'Unexpected preparation container reference.'
      return 1
    fi
    seen+="${id}"$'\n'
    printf 'container|%s|%s\n' "${id}" "${status}"
  done <<< "${names}"$'\n'"${refs}"
  if [[ $'\n'"${volumes}"$'\n' == *$'\nsecagent-vol\n'* ]]; then
    options='{{.Driver}}|{{.Scope}}|{{if not (index . "Options")}}ok{{end}}'
    if ! record="$("${DOCKER[@]}" volume inspect --format "${options}" \
      secagent-vol 2>/dev/null)" || [[ "${record}" != 'local|local|ok' ]]; then
      lab_status FAIL 'Unsupported volume backend/options; refused.'
      return 1
    fi
    printf '%s\n' 'volume|secagent-vol'
  fi
}
