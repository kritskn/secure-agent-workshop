#!/bin/bash
# Standalone readiness: cached selection and one live check, never provisioning.
# shellcheck source=lab_work.sh
source "${BASH_SOURCE[0]%/*}/lab_work.sh"
# shellcheck source=docker_host.sh
source "${BASH_SOURCE[0]%/*}/docker_host.sh"
# shellcheck source=load_prep_versions.sh
source "${BASH_SOURCE[0]%/*}/load_prep_versions.sh"
# shellcheck source=check_dependency_cli.sh
source "${BASH_SOURCE[0]%/*}/check_dependency_cli.sh"
# shellcheck source=openshell_stock.sh
source "${BASH_SOURCE[0]%/*}/openshell_stock.sh"
# shellcheck source=check_prep.sh
source "${BASH_SOURCE[0]%/*}/check_prep.sh"
# shellcheck source=prep_recovery.sh
source "${BASH_SOURCE[0]%/*}/prep_recovery.sh"

#######################################
# Select cached dependencies, probe CLIs, then validate profile/provider/log.
# Globals: helpers refresh DOCKER/DOCKER_ARCH, image IDs and selected pins.
# Arguments: trusted project directory. Outputs: brief checks/recovery guidance.
# LAB_SETUP_BRIEF is reused for scoped setup/check detail filtering.
# Locals LAB_SETUP_BRIEF/LAB_WORK_TITLE/LAB_WORK_WORD shadow caller values.
# Returns: 0 passed, 1 prerequisite failure, 3 typed live failure; other errors
#   from the live transport are preserved. No prompts, repairs or retries.
# Live checker includes offline prerequisites; one inference at most.
# No lab infrastructure or enforcement qualification. Native calls need consent.
#######################################
check_preparation() {
  local project="${1:-}" status stage=profile LAB_SETUP_BRIEF=0
  local LAB_WORK_TITLE='Checking tools' LAB_WORK_WORD='Working…'
  if (( $# != 1 )) || [[ -z "${project}" ]]; then
    lab_print '%s\n' '[FAIL] Expected the preparation project directory.' >&2
    return 1
  fi
  if LAB_SETUP_BRIEF=1 lab_work 'Docker' check_docker_host \
    && LAB_SETUP_BRIEF=1 lab_work 'Selected versions' \
      load_prep_versions "${project}" \
    && LAB_SETUP_BRIEF=1 lab_work 'nono CLI' \
      check_dependency_cli "${project}" nono "${NONO_VERSION}" \
    && LAB_SETUP_BRIEF=1 lab_work 'OpenShell CLI' \
      check_dependency_cli "${project}" openshell "${OPENSHELL_VERSION}" \
    && LAB_SETUP_BRIEF=1 lab_work 'Stock images' \
      lookup_openshell_stock "${OPENSHELL_VERSION}"; then
    lab_status PASS 'Workshop Tools ready.'
  else
    prep_recovery dependencies
    return 1
  fi
  if LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Checking agent' \
    lab_work 'Private profile' check_prep_runtime "${project}"; then
    lab_status PASS 'Agent profile ready.'
  else
    prep_recovery profile
    return 1
  fi
  lab_print '%s%s\n' \
    '[WARN] Online check uses available free credits first' \
    ' and tests observer log writing.' >&2
  if LAB_SETUP_BRIEF=1 LAB_WORK_TITLE='Checking Ollama Cloud' \
    lab_work 'Provider response and log' check_prep_live "${project}"; then
    lab_status PASS 'Ollama response and fresh observer log verified.'
    lab_status PASS 'Workshop preparation is ready.'
    lab_print '\n'
    lab_status BANNER '  +----------------------------------+
  | Preparation completed!           |
  | See you at the workshop.         |
  | LINE DEV CONF 2026               |
  | 17 Oct 2026 • BITEC              |
  +----------------------------------+'
    return 0
  else
    status=$?
  fi
  if (( status == 3 )); then
    stage=live
  fi
  prep_recovery "${stage}"
  return "${status}"
}
