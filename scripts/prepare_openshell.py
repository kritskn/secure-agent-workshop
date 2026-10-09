"""Build-time Linux OpenShell CLI installer; never starts infrastructure.

Only reviewed release digests are accepted. A different selected version needs
reviewed artifact metadata, not an unchecked download or a host installation.
"""

import hashlib
import io
import os
from pathlib import Path
import platform
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request


BINARY = Path("/usr/local/bin/openshell")
# v0.1.2 release checksums agree with GitHub asset digest metadata.
# Source tag: NVIDIA/OpenShell, 6648bd0c290efbc41ba131ee9831ee45cd431f94.
ARTIFACTS = {
    ("0.1.2", "aarch64"): (
        "aarch64-unknown-linux-musl", 9420629,
        "9880c5776688231d5242deb046cdee361734f94901b9123949a0baf29fdadd9e",
    ),
    ("0.1.2", "x86_64"): (
        "x86_64-unknown-linux-musl", 10203618,
        "7eb6917285331a09e3300266a0558616481a5e9927cae2612ea07c4045b6dd6f",
    ),
}
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com",
                  "objects.githubusercontent.com"}


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    """Permit only HTTPS public GitHub release redirects, without credentials."""

    def redirect_request(self, request, response, code, message, headers, url):
        target = urllib.parse.urlsplit(url)
        if (target.scheme != "https" or target.hostname not in DOWNLOAD_HOSTS
                or target.username is not None or target.password is not None
                or target.port not in (None, 443)):
            raise RuntimeError("Public release redirect refused")
        return super().redirect_request(request, response, code, message, headers, url)


def verify_version(binary, home, version, *, command="openshell"):
    """Clean isolated version probe; COMPLETE and gateway/provider env are absent."""
    environment = {
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_STATE_HOME": str(home / "state"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "PATH": "/usr/bin:/bin",
    }
    result = subprocess.run(
        [str(binary), "--version"], env=environment, cwd=home,
        stdin=subprocess.DEVNULL, text=True, capture_output=True,
        check=True, timeout=30,
    )
    if result.stdout.strip() != command + " " + version:
        raise RuntimeError(f"{command} version mismatch; staged binary not installed")


def install_cli(architecture, version):
    """Fresh image installation only; preserve any existing binary, even broken."""
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("OpenShell installation requires a Linux image build as root")
    if (version, architecture) not in ARTIFACTS:
        raise RuntimeError("Selected OpenShell version/platform lacks reviewed checksums")
    target, size, digest = ARTIFACTS[version, architecture]
    url = (f"https://github.com/NVIDIA/OpenShell/releases/download/v{version}/"
           f"openshell-{target}.tar.gz")
    install_release(BINARY, url, size, digest,
                    lambda binary, home: verify_version(binary, home, version))


def install_release(destination, url, size, digest, probe):
    """Shared nono/OpenShell fresh-image primitive; caller selects reviewed metadata.

    The caller supplies a fixed destination and public release URL, never user
    input. Only a verified single regular binary is staged, probed and published.
    """
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("Existing binary preserved; use a fresh image build")
    parent = destination.parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError("Binary destination must be a root-owned nonwritable directory")
    # No inherited proxies, keyring, authenticated API or credential fallback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ReleaseRedirect())
    with opener.open(url, timeout=60) as response:
        content = response.read(size + 1)
    if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
        raise RuntimeError("Release archive checksum/size mismatch; not extracted")
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=parent) as temporary:
        stage = Path(temporary)
        binary = stage / destination.name
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            member = archive.next()
            if (member is None or member.name != destination.name or not member.isfile()
                    or not 0 < member.size <= 32 * 1024 * 1024 or archive.next() is not None):
                raise RuntimeError("Release archive must contain only one regular named binary")
            # Never extract paths, ownership, links, setuid bits or archive permissions.
            with archive.extractfile(member) as source, binary.open("xb") as output:
                shutil.copyfileobj(source, output)
        binary.chmod(0o555)
        home = stage / "home"
        home.mkdir(mode=0o700)
        probe(binary, home)
        # Trusted single-writer image build, not a concurrent installation API.
        binary.rename(destination)


def main(arguments=()):
    if arguments:
        print("Usage: prepare_openshell.py (no arguments)", file=sys.stderr)
        return 2
    try:
        source = Path(__file__).parent
        profile = runpy.run_path(str(source / "setup_guest_pi.py"))
        config = profile["load_runtime_config"]((source / "runtime_config.json").read_bytes())
        install_cli(platform.machine(), config["openshell"])
    except RuntimeError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
        # HTTP exceptions can contain signed redirect URLs; do not print them.
        print("[FAIL] OpenShell image installation failed; existing files preserved. "
              "Check selected pin/platform, reviewed checksums and public network access.",
              file=sys.stderr)
        return 1
    print("[PASS] OpenShell CLI installed; gateway and lab readiness are not checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
