#!/usr/bin/env bash
# Public lab software builds only; inert help requires no tools or engine.
set -euo pipefail
unset LAB_WORK_PID LAB_SETUP_BRIEF LAB_WORK_TITLE LAB_WORK_WORD LAB_WORK_STYLE
# shellcheck source=lab_work.sh
source "${BASH_SOURCE[0]%/*}/lab_work.sh"

# Clear only our spinner; interruption does not prove daemon build settlement.
# Globals: LAB_WORK_PID. Args: signal exit status. Outputs: warning to stderr.
# Returns: exits with the supplied signal status.
cancel_build() {
  lab_stop_work
  lab_status WARN 'Build interrupted; Docker work may still be running.'
  lab_status WARN 'Inspect the build log and engine before another operation.'
  exit "$1"
}

# Validate before delegating to existing lab builders.
# Globals: BASH_SOURCE, LAB_WORK_STYLE. Args: --help. Outputs: status/help.
# Returns: build status, 0 help or 2 invalid arguments.
main() {
  local project
  if (( $# == 1 )) && [[ "$1" == --help ]]; then
    help_lines 'Usage: ./lab.sh build-labs [--help]' '' \
      'Prepare public Lab 1/2/3 images on the selected Linux engine.' \
      'Complete preparation first. Shared tooling may download public tools.' \
      'No private HOME, credentials, lab setup, services or model tasks.' \
      'Existing environments keep recorded images; no implicit upgrades.' \
      'Use sequentially; never overlap image or lifecycle operations.'
    return 0
  fi
  if (( $# )); then
    lab_status FAIL 'Use ./lab.sh build-labs --help.'
    return 2
  fi
  if ! command -v python3 >/dev/null 2>&1 \
    || ! python3 -I -B -c 'import sys;sys.exit(sys.version_info < (3,9))'; then
    lab_status FAIL 'Python 3.9 or newer is required; no builds performed.'
    return 1
  fi
  project="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)" || return
  trap 'lab_stop_work' EXIT
  trap 'cancel_build 130' INT
  trap 'cancel_build 143' TERM
  trap 'cancel_build 129' HUP
  LAB_WORK_STYLE=robot lab_work 'Building lab images' \
    python3 -u -I -B "${project}/scripts/build_labs.py"
}

main "$@"
