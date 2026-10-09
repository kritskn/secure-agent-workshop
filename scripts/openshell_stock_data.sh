#!/bin/bash
# Reviewed public v0.1.2 OCI metadata, not a second canonical version setting.
# NVIDIA/OpenShell source: 6648bd0c290efbc41ba131ee9831ee45cd431f94.
# GHCR metadata hashes/sizes/platforms were checked; no signature verification.
# Published index digests (gateway, sandbox, supervisor):
# 2fe4dad9118e14ab80a8258b545ea6e6cd74c3469e24ad4e6610f964d98913a2
# bf4797b6c511f2d8ba02955dbba4bf76c1f0dd6d83531420c5408d5f1fb9d72f
# d7b5264bb6bc56f4796e6fa3617b8e4a8d785be0b7293542efd8cc250b0fb67a
# Cache platform manifests directly; do not guess which index variant is local.

# shellcheck source=lab_output.sh
source "${BASH_SOURCE[0]%/*}/lab_output.sh"

#######################################
# Select reviewed release metadata; unknown selections fail without downloads.
# Arguments: Selected canonical version, Linux architecture amd64 or arm64.
# Outputs: role|manifest-digest|config-digest rows; fixed errors on stderr.
# Returns: 0 selected, 1 refused. No engine or filesystem actions.
#######################################
openshell_stock_metadata() {
  local number
  local roles=(gateway sandbox supervisor) manifests=() image_ids=()
  case "$1:$2" in
    0.1.2:amd64)
      manifests=(
        e0e18aa7a497290eed1f6ffb36f51540f037cec967c6d4354a264fecfd988620
        b0f0f6217b11b22954b10a033a9fd798cf0a4e35cf4af63c1ba0d9c03e74338a
        90a6f1a7257a8d3c76f89cc7cc1a1050567cf065a59ce76888f23dfd4f4c757d
      )
      image_ids=(
        d6a87806b557730d55c95b4b3bd99ab74ccab0ad479166e116fae545e2b2f45e
        e7a78d2e2c9c7d6ffc801e429a3304b51ffd65a84692530f2bbceea11e6e1558
        494b86855b51987cd68e205aa1b08d67592d4ea7b989f94c66e7179e17a97388
      )
      ;;
    0.1.2:arm64)
      manifests=(
        6eb7b779ac4b1a7ab8ebb3a901d6c73eae4b840dd033cc8e1cba4e39d6d3aed2
        e11541da52fa2963bdc371463095711e05cfc033d12e92b09f07e52df25ad86b
        8be4805ab3daa927e386c4945f827ed23a90238ecdf2dc2b8783069c17044657
      )
      image_ids=(
        e67f0bb7fac103c9efd05d481ea9aee464a59d8503490d3c4daca63546718eec
        a30614a2fdcead437debe0e88754b198b5c37f99a72bb948851cec0988ba95a6
        aef77570c4fbfdafc2451344ca41fa7dc5ded7a4299c223f0ae5ea929e55a608
      )
      ;;
    *)
      lab_print '%s\n' \
        '[FAIL] OpenShell version/platform lacks reviewed OCI metadata.' \
        >&2
      return 1
      ;;
  esac
  for number in 0 1 2; do
    printf '%s|%s|%s\n' "${roles[number]}" \
      "${manifests[number]}" "${image_ids[number]}"
  done
}
