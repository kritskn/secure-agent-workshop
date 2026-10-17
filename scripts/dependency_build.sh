#!/bin/bash
# Build-only dependency transport; cached lookup never loads this helper.

#######################################
# Build the validated public manifest with the default embedded Docker builder.
# Globals: DOCKER, DOCKER_ARCH. Arguments: project, recipe, tag, image role,
#   Pi base tag (empty for other roles), title, cache|no-cache, public files.
# Outputs: public tool diagnostics on stderr; stdout reserved for caller IDs.
# Returns: tool status (rightmost failure for pipeline), 1 unsupported builder.
# No environment cleanup or private state access.
#######################################
build_dependency_image() {
  local project="$1" recipe="$2" tag="$3" role="$4" base="$5" title="$6"
  local builder status cache="$7"
  local build_args=() driver_pattern=$'\nDriver:[[:blank:]]+docker\n'
  local engine=(env -u BUILDX_BUILDER -u BUILDKIT_HOST \
    -u DOCKER_DEFAULT_PLATFORM DOCKER_BUILDKIT=1 "${DOCKER[@]}")
  shift 7
  if [[ -n "${base}" ]]; then
    build_args=(--build-arg "PI_BASE=${base}")
  fi
  if [[ "${cache}" == no-cache ]]; then build_args+=(--no-cache); fi
  if builder="$("${engine[@]}" buildx inspect default)"; then
    if [[ ! $'\n'"${builder}"$'\n' =~ ${driver_pattern} ]]; then
      lab_status FAIL 'Default embedded Buildx builder required.'
      return 1
    fi
  else
    status=$?
    lab_status FAIL 'Default embedded Buildx builder required.'
    return "${status}"
  fi
  if (set -o pipefail
    COPYFILE_DISABLE=1 tar --format=ustar --no-xattrs -C "${project}" \
      -cf - "$@" \
      | "${engine[@]}" buildx build --builder default --load \
        --platform "linux/${DOCKER_ARCH}" --file "${recipe}" \
        ${build_args[@]+"${build_args[@]}"} \
        --label org.secagent.owner=secure-agent-workshop \
        --label "org.secagent.role=preparation-${role}" --tag "${tag}" - \
        >&2); then
    return 0
  else
    status=$?
    lab_print '[FAIL] %s build failed; partial cache/images kept.\n' \
      "${title}" >&2
    return "${status}"
  fi
}
