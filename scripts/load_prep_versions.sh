#!/bin/bash
# Read selected public pins through the cached runtime; no host Python required.
# shellcheck source=runtime_image.sh
source "${BASH_SOURCE[0]%/*}/runtime_image.sh"

#######################################
# Read and validate public tool pins from the selected cached runtime image.
# Globals: checked DOCKER/DOCKER_ARCH; lookup refreshes RUNTIME_IMAGE_ID.
#   PI_VERSION, NONO_VERSION, OPENSHELL_VERSION (empty on failure).
# Arguments: trusted project directory. Outputs: fixed status/errors.
# Returns: 0 validated pins published, 1 refused. No build/pull/private state.
# Requires trusted checkout/daemon without concurrent setup or edits.
#######################################
load_prep_versions() {
  local output pi nono openshell number='(0|[1-9][0-9]*)' pin pattern
  PI_VERSION='' NONO_VERSION='' OPENSHELL_VERSION=''
  if (( $# != 1 )); then
    lab_status FAIL 'Expected the preparation project directory.'
    return 1
  fi
  lookup_runtime_image "$1" >/dev/null || return
  # The source-tagged image includes this exact public config and validator.
  if ! output="$("${DOCKER[@]}" run --rm --pull never \
    --name secagent-prep-check \
    --label org.secagent.owner=secure-agent-workshop \
    --label org.secagent.role=preparation-check \
    --platform "linux/${DOCKER_ARCH}" --network none --read-only \
    --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 32 --memory 256m --cpus 1 --workdir /tmp \
    "${RUNTIME_IMAGE_ID}" python3 -I -B -c \
    'import runpy; from pathlib import Path
source = Path("/opt/secagent/preparation")
validator = runpy.run_path(str(source / "setup_guest_pi.py"))
config = validator["load_runtime_config"](
    (source / "runtime_config.json").read_bytes())
print("|".join(config[name] for name in ("pi", "nono", "openshell")))' \
    </dev/null 2>/dev/null)"; then
    lab_print '%s\n' \
      '[FAIL] Cannot read selected runtime pins; state preserved.' >&2
    return 1
  fi
  pin="${number}\\.${number}\\.${number}"
  pattern="^${pin}\\|${pin}\\|${pin}$"
  if [[ ! "${output}" =~ ${pattern} ]]; then
    lab_print '%s\n' \
      '[FAIL] Invalid runtime pin response; values not published.' >&2
    return 1
  fi
  IFS='|' read -r pi nono openshell <<< "${output}"
  if (( ${#pi} > 64 || ${#nono} > 64 || ${#openshell} > 64 )); then
    lab_print '%s\n' \
      '[FAIL] Oversized runtime pin response; values not published.' >&2
    return 1
  fi
  PI_VERSION="${pi}" NONO_VERSION="${nono}" OPENSHELL_VERSION="${openshell}"
  lab_print '[PASS] Selected pins: Pi %s, nono %s, OpenShell %s.\n' \
    "${PI_VERSION}" "${NONO_VERSION}" "${OPENSHELL_VERSION}"
}
