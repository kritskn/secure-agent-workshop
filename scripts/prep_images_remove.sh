#!/bin/bash
# Confirmed image-tag cleanup, separate from preparation HOME and lab removal.
# shellcheck source=prep_image_inventory.sh
source "${BASH_SOURCE[0]%/*}/prep_image_inventory.sh"

#######################################
# Remove displayed reserved tags, including consented label mismatches.
# Globals: DOCKER. Args: optional verbosity 0/1. Outputs: scope/prompt/status.
# Returns: 0 absent/removed, 1 declined/refused, or Docker failure status.
# No force/prune, container stop, volume, credential or host-state changes.
# No concurrent builds/removal or administrator retagging during cleanup.
#######################################
remove_prep_images() {
  local inventory current tag image_id ownership record answer status remaining
  local verbose="${1:-0}"
  if (( $# > 1 )) || [[ ! "${verbose}" =~ ^[01]$ \
    || ! -t 0 || ! -t 1 || ! -t 2 ]]; then
    lab_status FAIL 'Image removal requires an interactive terminal.'
    return 1
  fi
  (( verbose == 0 )) || lab_status DEBUG 'Checking reserved tags/references.'
  inventory="$(prep_image_inventory)" || return
  if [[ -z "${inventory}" ]]; then
    lab_status INFO 'Preparation image tags are absent; nothing removed.'
    return 0
  fi
  lab_print '%s\n' \
    'Remove these exact preparation tags (both architectures):' \
    'TAG | ACTUAL IMAGE ID | OWNER/ROLE LABELS'
  while IFS='|' read -r tag image_id ownership; do
    lab_print '%s | %s | %s\n' "${tag}" "${image_id}" "${ownership}"
  done <<< "${inventory}"
  lab_print '%s\n' \
    'Confirmation includes listed tags with missing/wrong ownership labels.' \
    'Docker may delete unshared images; other tags and shared cache are kept.' \
    'Preparation HOME, credentials, sessions and lab environments are kept.' \
    'Published src-* and stock images are outside this removal scope.' \
    'Do not run builds, retag images or start containers during removal.'
  printf 'Remove these preparation image tags? [y/N] '
  if ! IFS= read -r answer; then
    lab_print '\n%s\n' '[INFO] Image removal cancelled.'
    return 1
  fi
  case "${answer}" in
    [Yy] | [Yy][Ee][Ss]) ;;
    *) lab_status INFO 'Image removal cancelled.'; return 1 ;;
  esac
  (( verbose == 0 )) || lab_status DEBUG 'Rechecking the confirmed inventory.'
  current="$(prep_image_inventory)" || return
  if [[ "${current}" != "${inventory}" ]]; then
    lab_status FAIL 'Inventory changed after confirmation; nothing removed.'
    return 1
  fi
  while IFS= read -r record; do
    tag="${record%%|*}"
    (( verbose == 0 )) || lab_status DEBUG "Rechecking ${tag} before removal."
    if ! current="$(prep_image_record "${tag}")" \
      || [[ "${current}" != "${record}" ]]; then
      lab_status FAIL 'Image changed/in use; removal halted, may be partial.'
      return 1
    fi
    if "${DOCKER[@]}" image rm --no-prune "${tag}" >/dev/null 2>&1; then
      lab_status INFO "Removed tag: ${tag}"
    else
      status=$?
      lab_status FAIL "Image removal failed: ${tag} (exit ${status})."
      lab_status WARN 'Underlying cause cannot safely be distinguished.'
      lab_status WARN 'Earlier tags may already be removed; preserve the rest.'
      lab_print '%s\n' \
        '[NEXT] Inspect the selected engine: docker image ls --no-trunc' >&2
      return "${status}"
    fi
  done <<< "${inventory}"
  (( verbose == 0 )) || lab_status DEBUG 'Verifying reserved tags are absent.'
  remaining="$(prep_image_inventory)" || {
    lab_status FAIL 'Cannot confirm cleanup; image-tag removal may be partial.'
    return 1
  }
  if [[ -n "${remaining}" ]]; then
    lab_status FAIL 'Reserved preparation tags remain; removal is incomplete.'
    return 1
  fi
  lab_status PASS 'Reserved preparation image tags removed.'
  lab_status INFO 'Shared cache/other tags kept; this is not a factory reset.'
  lab_status INFO 'To rebuild tools only: ./lab.sh setup --build-only'
}
