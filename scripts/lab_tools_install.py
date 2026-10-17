"""Software-only ARM64/AMD64 tooling installer and immutable image recipe inputs.

Import and help are inert. Installation requires the separately approved image
build environment. No lab HOME defaults, credentials, exercises or model calls.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

APT_PACKAGES = ("neovim=0.10.4-8", "emacs-nox=1:30.1+1-6+deb13u1",
                "nano=8.4-1+deb13u1", "ripgrep=14.1.1-1+b4", "fd-find=10.2.0-1+b5",
                "curl")
# Published v0.9.3/v0.5.2 release asset digests; verify downloaded bytes before use.
ARTIFACTS = {
    "arm64": {
        "herdr": (
            "https://github.com/herdrdev/herdr/releases/download/v0.9.3/herdr-linux-aarch64",
            27_606_640,
            "4de7aa3e25678812e92960de64f7c2aaa1bca1f0f80a3c5e559837e231e1f5c0",
        ),
        "fresh.tar.xz": (
            ("https://github.com/sinelaw/fresh/releases/download/v0.5.2/"
             "fresh-editor-aarch64-unknown-linux-musl.tar.xz"),
            11_064_728,
            "1dd3a9aece67fac3aa8f60710911112e19a9f8e7f0782d38fcaed32a83d14e04",
        ),
    },
    "amd64": {
        "herdr": (
            "https://github.com/herdrdev/herdr/releases/download/v0.9.3/herdr-linux-x86_64",
            29_962_088,
            "18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7",
        ),
        "fresh.tar.xz": (
            ("https://github.com/sinelaw/fresh/releases/download/v0.5.2/"
             "fresh-editor-x86_64-unknown-linux-musl.tar.xz"),
            11_032_924,
            "58ecefd2a9c65f214ab752da4fb9c61b33438cd1343492ece0189236651399ce",
        ),
    },
}
# At most 41 MB artifact payloads + 155 MB APT traffic stays below 200 MB.
BUILD_NETWORK_STOP = 155_000_000


def normalize_architecture(machine):
    """Canonical Docker architecture; never infer the target from the host CPU."""
    aliases = {"arm64": "arm64", "aarch64": "arm64", "amd64": "amd64", "x86_64": "amd64"}
    if machine not in aliases:
        raise RuntimeError("Linux ARM64 or AMD64 required; unsupported architecture")
    return aliases[machine]


def verified_bytes(content, size, digest):
    if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
        raise RuntimeError("Public editor artifact size/checksum mismatch")
    return content


def safe_members(archive):
    """Inspect the whole public archive before extraction or binary execution."""
    members = archive.getmembers()
    total = 0
    seen = set()
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts
                or (not path.parts and not member.isdir())
                or not (member.isfile() or member.isdir()) or path in seen):
            raise RuntimeError("Unsafe or duplicate editor archive member")
        seen.add(path)
        total += member.size
    if len(members) > 4096 or total > 256 * 1024 * 1024:
        raise RuntimeError("Editor archive expansion exceeded PoC bound")
    return members


def installer_stage(name):
    """Authored public build diagnostics; never format exception payloads."""
    print("[INFO] Tooling installer stage: " + name, flush=True)


def network_counters():
    """Read namespace RX from procfs; rootless BuildKit may not expose sysfs."""
    lines = Path("/proc/net/dev").read_text().splitlines()
    if (len(lines) < 3 or "Receive" not in lines[0] or "Transmit" not in lines[0]
            or "bytes" not in lines[1]):
        raise RuntimeError("Image build network counters unavailable or invalid")
    counters = {}
    for line in lines[2:]:
        name, separator, values = line.rpartition(":")
        name = name.strip()
        fields = values.split()
        if (not separator or not name or name in counters or len(fields) != 16
                or any(not value.isascii() or not value.isdecimal() for value in fields)):
            raise ValueError("Image build network counters malformed")
        counters[name] = int(fields[0])
    if not counters:
        raise RuntimeError("Image build network counters unavailable or invalid")
    return counters


def received_bytes(start, previous):
    """Reject any observed decrease, then advance the last successful snapshot."""
    current = network_counters()
    if current.keys() != start.keys() or any(current[name] < previous[name] for name in start):
        raise RuntimeError("Image build network counters changed; accounting refused")
    previous.update(current)
    return sum(current[name] - start[name] for name in start)


def image_install():
    """Docker build only: verified software, no profile or model startup."""
    installer_stage("build-environment")
    if (platform.system() != "Linux" or os.geteuid() != 0
            or os.environ.get("SECAGENT_EDITOR_IMAGE_BUILD") != "1"
            or not Path("/opt/secagent/runtime/runtime_versions.json").is_file()):
        raise RuntimeError("Run only inside the approved Linux tooling image build")
    installer_stage("architecture")
    architecture = normalize_architecture(platform.machine())
    selected = ARTIFACTS[architecture]
    artifacts = Path("/tmp/secagent-editor-artifacts")
    artifacts.mkdir()
    for name, (url, size, digest) in selected.items():
        installer_stage("artifact-download " + name)
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read(size + 1)
        installer_stage("artifact-verification " + name)
        verified_bytes(content, size, digest)
        (artifacts / name).write_bytes(content)
        print(f"[INFO] Artifact {name}: {len(content)} bytes; size/SHA256 matched.", flush=True)
    installer_stage("archive-extraction")
    with tarfile.open(artifacts / "fresh.tar.xz", mode="r:xz") as archive:
        members = safe_members(archive)
        destination = Path("/opt/secagent/lab-tools/fresh")
        destination.mkdir()
        archive.extractall(destination, members=members, filter="data")
    installer_stage("tool-staging")
    candidates = [path for path in destination.rglob("fresh") if path.is_file()]
    if len(candidates) != 1:
        raise RuntimeError("Expected one fresh executable in the verified archive")
    fresh = candidates[0]
    fresh.chmod(0o755)
    herdr = Path("/opt/secagent/lab-tools/herdr")
    shutil.copyfile(artifacts / "herdr", herdr)
    herdr.chmod(0o755)
    for name, path in (("fresh", fresh), ("herdr", herdr)):
        link = Path("/usr/local/bin") / name
        if link.exists() or link.is_symlink():
            raise RuntimeError("Existing editor installation preserved")
        link.symlink_to(path)
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
                   "DEBIAN_FRONTEND": "noninteractive", "LANG": "C", "LC_ALL": "C"}
    installer_stage("network-accounting")
    start_rx = network_counters()
    print(f"[INFO] Build network accounting: {len(start_rx)} interfaces; "
          f"eth0 present: {'eth0' in start_rx}.", flush=True)
    deadline = time.monotonic() + 900
    previous_rx = start_rx.copy()

    def checked_received():
        received = received_bytes(start_rx, previous_rx)
        if received >= BUILD_NETWORK_STOP or time.monotonic() >= deadline:
            raise RuntimeError("Image build download/time bound reached")
        return received

    for stage, arguments in (
        ("apt-update", ["apt-get", "-o", "Acquire::Retries=0", "-o",
                        "Acquire::http::Dl-Limit=1024", "update", "--error-on=any"]),
        ("apt-install", ["apt-get", "-o", "Acquire::Retries=0", "-o",
                         "Acquire::http::Dl-Limit=1024", "install", "--yes",
                         "--no-install-recommends", *APT_PACKAGES]),
    ):
        installer_stage(stage)
        process = subprocess.Popen(arguments, env=environment, start_new_session=True)
        try:
            while process.poll() is None:
                checked_received()
                time.sleep(0.1)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
        if process.returncode:
            raise RuntimeError("APT editor installation refused")
        # Catch an overshoot/reset even when APT exits between polling samples.
        received = checked_received()
    installer_stage("build-staging-cleanup")
    # Remove only build-created staging and indices, within this new image layer.
    shutil.rmtree(artifacts)
    shutil.rmtree("/var/lib/apt/lists")
    installer_stage("tool-version-verification")
    versions = {}
    for name, arguments, expected in (
        ("herdr", ["herdr", "--version"], "0.9.3"),
        ("fresh", ["fresh", "--no-upgrade-check", "--version"], "0.5.2"),
        ("neovim", ["nvim", "--version"], "0.10.4"),
        ("emacs", ["emacs", "--version"], "30.1"),
        ("nano", ["nano", "--version"], "8.4"),
        ("ripgrep", ["rg", "--version"], "14.1.1"),
        ("fd", ["fdfind", "--version"], "10.2.0"),
    ):
        output = subprocess.run(arguments, env=environment, capture_output=True,
                                text=True, check=True, timeout=30).stdout.splitlines()[0]
        if not re.search(r"(?<![\d.])" + re.escape(expected) + r"(?![\d.])", output):
            raise RuntimeError("Unexpected editor version")
        versions[name] = output
    versions["curl"] = subprocess.run(
        ["curl", "--version"], env=environment, capture_output=True,
        text=True, check=True, timeout=30).stdout.splitlines()[0]
    installer_stage("receipt")
    receipt = {"architecture": architecture, "versions": versions,
               "build_network_received_bytes": received,
               "artifact_bytes": sum(item[1] for item in selected.values()),
               "pi_or_model_execution": False}
    Path("/opt/secagent/lab-tools/receipt.json").write_text(json.dumps(receipt) + "\n")
    print(json.dumps(receipt), flush=True)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("image-install",))
    parser.parse_args(args)
    image_install()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        detail = type(error).__name__
        if isinstance(error, urllib.error.HTTPError) and type(error.code) is int and 100 <= error.code <= 599:
            detail += f"; HTTP {error.code}"
        print("[FAIL] Tooling image installation failed (" + detail
              + "); review the last installer stage. No automatic retry.", file=sys.stderr)
        sys.exit(1)
