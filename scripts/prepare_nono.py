"""Build-time verified Linux nono binary installation, not sandbox setup.

Reuses the existing OpenShell installer's public-release primitive. Image
integration must include that trusted sibling; no host or personal Pi imports.
"""

import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tarfile


BINARY = Path("/usr/local/bin/nono")
# nolabs-ai/nono v0.79.0, commit e5ff57f916b528c38ee00d20556d86902215e3d8.
# SHA256SUMS.txt agrees with GitHub asset digest metadata; signatures not checked.
ARTIFACTS = {
    ("0.79.0", "aarch64"): (
        "aarch64-unknown-linux-gnu", 11401531,
        "c4a4f4b9ae318574d30d352127a34dcc919c4d6682ee8fbd30bb8d2bd2e0e85d",
    ),
    ("0.79.0", "x86_64"): (
        "x86_64-unknown-linux-gnu", 12356832,
        "36dfeeb6e8c6a30c43f80ba239e2460af43047c008153af527fdd893c1f02392",
    ),
}


def install_cli(architecture, version):
    """Install only in a fresh Linux build; enforcement/auth remain Phase 2."""
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("nono installation requires a Linux image build as root")
    if (version, architecture) not in ARTIFACTS:
        raise RuntimeError("Selected nono version/platform lacks reviewed checksums")
    target, size, digest = ARTIFACTS[version, architecture]
    url = (f"https://github.com/nolabs-ai/nono/releases/download/v{version}/"
           f"nono-v{version}-{target}.tar.gz")
    release = runpy.run_path(str(Path(__file__).with_name("prepare_openshell.py")))
    release["install_release"](
        BINARY, url, size, digest,
        lambda binary, home: release["verify_version"](binary, home, version, command="nono"),
    )


def main(arguments=()):
    if arguments:
        print("Usage: prepare_nono.py (no arguments)", file=sys.stderr)
        return 2
    try:
        source = Path(__file__).parent
        profile = runpy.run_path(str(source / "setup_guest_pi.py"))
        config = profile["load_runtime_config"]((source / "runtime_config.json").read_bytes())
        install_cli(platform.machine(), config["nono"])
    except RuntimeError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
        # Do not echo HTTP errors, signed URLs or binary output.
        print("[FAIL] nono image installation failed; existing files preserved. "
              "Check selected pin/platform, reviewed checksums and public network access.",
              file=sys.stderr)
        return 1
    print("[PASS] nono installed; sandbox enforcement and credential injection are not checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
