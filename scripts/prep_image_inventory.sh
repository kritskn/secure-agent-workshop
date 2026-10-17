#!/bin/bash
# Exact reserved preparation-tag inventory; no mutation or private-data access.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Inspect a reserved tag; refuse containers using it or a derived image.
# Globals: DOCKER (selected local engine). Arguments: exact reserved tag.
# Outputs: tag|image ID|ownership marker on stdout, diagnostics on stderr.
# Returns: 0 absent/eligible, 1 unsafe or inspection failed. Never deletes.
#######################################
prep_image_record() {
  local tag="$1" role inventory details image_id references format
  local pattern='^secagent-(runtime|nono|openshell):local-(arm64|amd64)$'
  if [[ ! "${tag}" =~ ${pattern} ]] \
    || [[ "${DOCKER[0]:-}" != env ]]; then
    lab_status FAIL 'Expected a reserved preparation tag and selected engine.'
    return 1
  fi
  role="${tag#secagent-}" role="${role%%:*}"
  if ! inventory="$("${DOCKER[@]}" image ls --all \
    --format '{{.Repository}}:{{.Tag}}' \
    --filter "reference=${tag}" 2>/dev/null)"; then
    lab_status FAIL "Cannot inventory ${tag}; no removal."
    return 1
  fi
  if [[ -z "${inventory}" ]]; then return 0; fi
  if [[ "${inventory}" != "${tag}" ]]; then
    lab_status FAIL "Unexpected inventory for ${tag}; preserved."
    return 1
  fi
  format='{{.Id}}|{{with index . "Config"}}{{with index . "Labels"}}'
  format+='{{if and (eq (index . "org.secagent.owner") '
  format+='"secure-agent-workshop") '
  format+="(eq (index . \"org.secagent.role\") \"preparation-${role}\")}}"
  format+='matching{{else}}mismatch{{end}}{{else}}mismatch{{end}}'
  format+='{{else}}mismatch{{end}}'
  if ! details="$("${DOCKER[@]}" image inspect \
    --format "${format}" "${tag}" 2>/dev/null)" \
    || [[ ! "${details}" =~ ^sha256:[0-9a-f]{64}\|(matching|mismatch)$ ]]; then
    lab_status FAIL "Cannot verify actual image identity for ${tag}; preserved."
    return 1
  fi
  image_id="${details%%|*}"
  if ! references="$("${DOCKER[@]}" container ls --all \
    --filter "ancestor=${image_id}" --format '{{.ID}}' 2>/dev/null)"; then
    lab_status FAIL "Cannot check container references for ${tag}; preserved."
    return 1
  fi
  if [[ -n "${references}" ]]; then
    lab_status FAIL "Container uses ${tag} or a derived image; preserved."
    return 1
  fi
  printf '%s|%s\n' "${tag}" "${details}"
}

#######################################
# Inventory only the six reserved preparation tags on the selected engine.
# Globals: DOCKER. Arguments: none. Outputs: records/errors as above.
# Returns: 0 complete, 1 refused; caller must discard partial output on failure.
#######################################
prep_image_inventory() {
  local role architecture
  for role in runtime nono openshell; do
    for architecture in arm64 amd64; do
      prep_image_record "secagent-${role}:local-${architecture}" || return
    done
  done
}
