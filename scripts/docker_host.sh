#!/bin/bash
# Passive Docker preflight library for preparation, checks and removal.
# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Detect the host for guidance and pin the selected local Docker socket.
# Globals: DOCKER, DOCKER_ARCH (empty on failure); Docker CLI environment.
# Arguments: None.
# Outputs: Coarse platform/status to stdout; safe guidance to stderr.
# Returns: 0 for reachable Linux amd64/arm64 metadata, 1 otherwise.
# No feature probes, startup, installation or configuration/resource changes.
#######################################
check_docker_host() {
  local os architecture kernel hint endpoint server
  DOCKER=()
  DOCKER_ARCH=''
  if ! os="$(uname -s 2>/dev/null)" \
    || ! architecture="$(uname -m 2>/dev/null)" \
    || ! kernel="$(uname -r 2>/dev/null)" \
    || [[ -z "${os}" || -z "${architecture}" || -z "${kernel}" ]]; then
    lab_status FAIL 'Could not detect the host platform.'
    return 1
  fi
  case "${os}:${kernel}" in
    Darwin:*)
      os='macOS'
      hint='macOS: install/start your Docker environment (e.g. Docker Desktop).'
      ;;
    Linux:*[Mm]icrosoft* | Linux:*[Ww][Ss][Ll]*)
      os='WSL'
      hint='WSL: use WSL2; check Docker Desktop integration or Linux Engine.'
      ;;
    Linux:*)
      hint="Linux: follow Docker's distro installation/service/access guidance."
      ;;
    *)
      lab_status FAIL 'Use macOS or Linux Bash; on Windows use WSL2.'
      return 1
      ;;
  esac
  case "${architecture}" in
    arm64 | aarch64 | x86_64) ;;
    *) architecture='other' ;;
  esac
  lab_print '[INFO] Host platform: %s (%s).\n' "${os}" "${architecture}"
  if ! command -v docker >/dev/null 2>&1; then
    lab_print '%s\n' '[FAIL] Docker CLI not found.' "${hint}" \
      'See https://docs.docker.com/get-started/get-docker/' >&2
    return 1
  fi
  # With no name, inspect uses Docker's effective context and env overrides.
  if ! endpoint="$(docker context inspect \
    --format '{{.Endpoints.docker.Host}}' 2>/dev/null)"; then
    lab_print '%s\n' '[FAIL] Cannot resolve the selected Docker endpoint.' \
      'Inspect docker context ls and your Docker environment variables.' >&2
    return 1
  fi
  if [[ "${endpoint}" != unix:///* || "${endpoint}" == 'unix:///' \
    || "${endpoint}" =~ [[:cntrl:]] ]]; then
    lab_print '%s\n' '[FAIL] Select a local Unix-socket Docker connection.' \
      'TCP, SSH and Windows named-pipe endpoints are not accepted.' \
      'Inspect docker context ls; no engine connection was attempted.' >&2
    return 1
  fi
  # Pin the socket, not a mutable context. TLS overrides do not apply to Unix.
  DOCKER=(env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS \
    -u DOCKER_TLS_VERIFY docker --host "${endpoint}")
  if ! server="$("${DOCKER[@]}" info \
    --format '{{.OSType}}|{{.Architecture}}' 2>/dev/null)"; then
    DOCKER=()
    lab_print '%s\n' '[FAIL] Docker engine unreachable or access denied.' \
      "${hint}" \
      'Inspect docker info and docker context ls; review user access.' \
      'No automatic sudo, permission changes or startup were attempted.' >&2
    return 1
  fi
  case "${server}" in
    'linux|amd64' | 'linux|x86_64') DOCKER_ARCH='amd64' ;;
    'linux|arm64' | 'linux|aarch64') DOCKER_ARCH='arm64' ;;
    *)
      DOCKER=()
      lab_print '%s\n' \
        '[FAIL] Docker must report Linux amd64/arm64 containers.' \
        'Windows-container mode is not supported; use a Linux engine.' >&2
      return 1
      ;;
  esac
  lab_print '[PASS] Local-socket Linux Docker metadata accepted (%s).\n' \
    "${DOCKER_ARCH}"
  lab_print '%s\n' \
    '[INFO] Container features and workshop readiness are not yet verified.'
}
