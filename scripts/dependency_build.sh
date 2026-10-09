#!/bin/bash
# Build-only dependency transport; cached lookup never loads this helper.

#######################################
# Build the validated public manifest with the default embedded Docker builder.
# Globals: DOCKER, DOCKER_ARCH. Arguments: project, recipe, tag, source digest,
#   Pi base tag (empty for other roles), title, then public input filenames.
# Outputs: fixed stderr on failure; no output on success.
# Returns: 0 built, nonzero failed. No deletion/replacement of existing state.
#######################################
build_dependency_image() {
  local project="$1" recipe="$2" tag="$3" digest="$4" base="$5" title="$6"
  local builder
  local build_args=() driver_pattern=$'\nDriver:[[:blank:]]+docker\n'
  local engine=(env -u BUILDX_BUILDER -u BUILDKIT_HOST \
    -u DOCKER_DEFAULT_PLATFORM DOCKER_BUILDKIT=1 "${DOCKER[@]}")
  shift 6
  if [[ -n "${base}" ]]; then
    build_args=(--build-arg "PI_BASE=${base}")
  fi
  if ! builder="$("${engine[@]}" buildx inspect default 2>/dev/null)" \
    || [[ ! $'\n'"${builder}"$'\n' =~ ${driver_pattern} ]]; then
    lab_status FAIL 'Default embedded Buildx builder required.'
    return 1
  fi
  if ! (set -o pipefail
    COPYFILE_DISABLE=1 tar --format=ustar --no-xattrs -C "${project}" \
      -cf - "$@" 2>/dev/null \
      | "${engine[@]}" buildx build --builder default --load \
        --platform "linux/${DOCKER_ARCH}" --file "${recipe}" \
        ${build_args[@]+"${build_args[@]}"} \
        --label "org.secagent.prep.source-sha256=${digest}" --tag "${tag}" - \
        >/dev/null 2>&1); then
    lab_print '[FAIL] %s build failed; partial cache/images kept.\n' \
      "${title}" >&2
    return 1
  fi
}
