#!/bin/bash
# Preparation-only reset used by the participant remove command.
# Reserved volume may have broken/missing labels; confirmation covers its data.

# shellcheck source=prep_reset_inventory.sh
source "${BASH_SOURCE[0]%/*}/prep_reset_inventory.sh"

#######################################
# Confirm and remove only identified preparation containers and reserved HOME.
# Globals: DOCKER, DOCKER_ARCH from preflight. Arguments: none.
# Outputs: Warning, interactive Y/n prompt, fixed results/errors.
# Returns: 0 removed/absent, 1 cancelled/refused/failed. No automatic rebuild.
# Requires trusted daemon, no concurrent setup/admin mutations. No force/prune.
#######################################
reset_prep_state() {
  local inventory kind id status answer remaining
  if (( $# != 0 )) || [[ ! -t 0 || ! -t 1 || ! -t 2 ]]; then
    lab_status FAIL 'Reset requires a terminal and no arguments.'
    return 1
  fi
  if [[ "${DOCKER[0]:-}" != env \
    || ( "${DOCKER_ARCH:-}" != amd64 && "${DOCKER_ARCH:-}" != arm64 ) ]]; then
    lab_status FAIL 'Run Docker preflight before preparation reset.'
    return 1
  fi
  inventory="$(prep_reset_inventory)" || return
  if [[ -z "${inventory}" ]]; then
    lab_status INFO 'Preparation state is absent; nothing to reset.'
    return 0
  fi
  lab_print '%s%s\n' \
    '[WARN] Reset deletes preparation containers' \
    ' and the workshop Docker volume.'
  lab_print '%s\n' \
    'Saved credentials, sessions and logs will be lost.' \
    'Cached dependencies, lab state and legacy VMs will be preserved.' \
    'Deleting a saved key does not revoke it at the provider.'
  while true; do
    printf 'Reset preparation? (Y/n) '
    if ! IFS= read -r answer; then
      lab_print '\n%s\n' '[INFO] Reset cancelled.'
      return 1
    fi
    case "${answer}" in
      '' | [Yy] | [Yy][Ee][Ss]) break ;;
      [Nn] | [Nn][Oo])
        lab_status INFO 'Reset cancelled.'
        return 1
        ;;
      *) printf '%s\n' 'Please answer Y or n.' ;;
    esac
  done
  # All references are validated before any destructive command is issued.
  while IFS='|' read -r kind id status; do
    if [[ "${kind}" != container ]]; then
      continue
    fi
    case "${status}" in
      running | restarting | paused)
        if ! "${DOCKER[@]}" container stop --time 10 "${id}" \
          >/dev/null 2>&1; then
          lab_status FAIL 'Container stop failed; cleanup halted.'
          return 1
        fi
        ;;
    esac
    if ! "${DOCKER[@]}" container rm "${id}" >/dev/null 2>&1; then
      lab_status FAIL 'Container removal failed; remaining state kept.'
      return 1
    fi
  done <<< "${inventory}"
  if [[ $'\n'"${inventory}"$'\n' == *$'\nvolume|secagent-vol\n'* ]]; then
    if ! "${DOCKER[@]}" volume rm secagent-vol >/dev/null 2>&1; then
      lab_status FAIL 'Volume removal failed; remaining state kept.'
      return 1
    fi
  fi
  remaining="$(prep_reset_inventory)" || return
  if [[ -n "${remaining}" ]]; then
    lab_print '%s\n' \
      '[FAIL] Preparation resources remain; reset not confirmed.' >&2
    return 1
  fi
  lab_print '%s\n' '[PASS] Preparation state removed; dependencies preserved.'
}
