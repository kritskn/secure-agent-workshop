"""Install a pinned, root-owned Node/npm/pi runtime in the participant Lima guest.

Called by setup_guest_tools.sh with a clean environment. No model credentials,
agent sessions, personal configuration, Docker or other lab services are created.
Python stdlib handles structured checks, verified downloads and staged cleanup.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


INSTALL_ROOT = Path("/opt/secagent")
RUNTIME = INSTALL_ROOT / "runtime"
NODE_VERSION = "24.21.0"
NPM_VERSION = "12.1.0"
PI_PACKAGE = "@earendil-works/pi-coding-agent"
UBUNTU_VERSION = "26.04"
NODE_IMAGES = {
    "aarch64": ("arm64", "6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2"),
    "x86_64": ("x64", "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6"),
}
# Only the reviewed Lima cloud-init deprecation is allowed, not arbitrary exit 2.
KNOWN_CLOUD_WARNING = (
    "Deprecated cloud-config provided: users.0.ssh-authorized-keys:  "
    "Deprecated in version 18.3. Use **ssh_authorized_keys** instead., "
    "users.0.uid:  Changed in version 22.3. The use of ``string`` type is "
    "deprecated. Use an ``integer`` instead."
)
STAGES = ("init-local", "init", "modules-config", "modules-final")


class RuntimeMismatchError(RuntimeError):
    """Known manifest mismatch with complete, participant-facing recovery text."""


def validate_cloud_init(code, report):
    """Reject incomplete/fatal/unknown degraded results; return known warnings."""
    if code not in (0, 2) or report.get("status") != "done":
        raise RuntimeError("Cloud-init has not completed successfully")
    warnings = set()
    for section in (report, *(report.get(name, {}) for name in STAGES)):
        if section.get("errors"):
            raise RuntimeError("Cloud-init reports errors; inspect its status locally")
        for category, messages in section.get("recoverable_errors", {}).items():
            if category != "DEPRECATED" or any(m != KNOWN_CLOUD_WARNING for m in messages):
                raise RuntimeError("Unreviewed cloud-init warnings; inspect status locally")
            warnings.update(messages)
    if code == 2 and not warnings:
        raise RuntimeError("Cloud-init exit 2 without the reviewed deprecation warning")
    return warnings


def check_guest():
    """Accidental-host guard, not a security boundary against a privileged actor."""
    if platform.system() != "Linux" or platform.node() != "lima-secagent-lab":
        raise RuntimeError("Run only inside the participant lima-secagent-lab VM")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != UBUNTU_VERSION:
        raise RuntimeError(
            f"This preparation block requires Ubuntu {UBUNTU_VERSION}; "
            "existing VM preserved, no automatic OS migration"
        )
    if os.geteuid() != 0:
        raise RuntimeError("Guest preparation requires operator sudo/root")
    architecture = platform.machine()
    if architecture not in NODE_IMAGES:
        raise RuntimeError("Only native aarch64 and x86_64 guests are supported")
    result = subprocess.run(
        ["cloud-init", "status", "--long", "--format=json"],
        text=True, capture_output=True, timeout=30,
    )
    # Accept only the reviewed deprecations silently; all other problems still fail.
    validate_cloud_init(result.returncode, json.loads(result.stdout))
    print(f"[PASS] Ubuntu {UBUNTU_VERSION} {architecture} guest preparation checks.", flush=True)
    return architecture


def require_root_owned(path):
    """Do not execute or replace a user-writable installation as root."""
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"Expected a real installation directory: {path}")
    for item in (path, *path.rglob("*")):
        info = item.lstat()
        if info.st_uid != 0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022):
            raise RuntimeError(f"Installation is not root-owned/read-only: {item}")


def clean_environment(home, runtime):
    """Explicit env/config, never inherited provider/npm credentials or NODE_OPTIONS."""
    home.mkdir(exist_ok=True)
    for name in ("user.npmrc", "global.npmrc"):
        (home / name).touch()
    return {
        "HOME": str(home),
        "PATH": f"{runtime / 'bin'}:/usr/sbin:/usr/bin:/sbin:/bin",
        "npm_config_userconfig": str(home / "user.npmrc"),
        "npm_config_globalconfig": str(home / "global.npmrc"),
        "npm_config_registry": "https://registry.npmjs.org",
        "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
        "DEBIAN_FRONTEND": "noninteractive",
    }


def verify_runtime(runtime, environment, home, pi_version, *, process_identity=None):
    # Pi enables Node's persistent cache even for --version; checks must not.
    environment = environment | {"NODE_DISABLE_COMPILE_CACHE": "1"}
    for executable, expected in (
        ("node", "v" + NODE_VERSION), ("npm", NPM_VERSION), ("pi", pi_version),
    ):
        result = subprocess.run(
            [str(runtime / "bin" / executable), "--version"],
            env=environment, cwd=home, text=True, capture_output=True,
            stdin=subprocess.DEVNULL, check=True, timeout=30,
            **(process_identity or {}),
        )
        actual = result.stdout.strip()
        if actual != expected:
            raise RuntimeError(
                f"Unexpected {executable} version: expected {expected!r}, got {actual!r}; "
                "existing files preserved. This does not match the workshop base. "
                "See the preparation presentation referenced in README.md; "
                "do not edit the manifest."
            )


def install_packages(environment, home):
    missing = []
    for name in ("ca-certificates", "git"):
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", name], env=environment,
            text=True, capture_output=True, timeout=30,
        )
        if result.returncode or result.stdout.strip() != "install ok installed":
            missing.append(name)
    if missing:
        subprocess.run(["apt-get", "update", "--error-on=any"],
                       env=environment, cwd=home, check=True, timeout=600)
        subprocess.run(["apt-get", "install", "-y", "--no-install-recommends", *missing],
                       env=environment, cwd=home, check=True, timeout=600)


def runtime_versions(architecture, pi_version):
    """One manifest schema/pin set for installation and read-only checks."""
    return {"node": NODE_VERSION, "npm": NPM_VERSION, "pi": pi_version,
            "architecture": architecture}


def verify_runtime_manifest(runtime, architecture, pi_version):
    """Keep legacy/mismatched installs unchanged in both setup and check."""
    recorded = json.loads((runtime / "runtime_versions.json").read_text())
    if recorded != runtime_versions(architecture, pi_version):
        raise RuntimeMismatchError(
            "Existing runtime differs; no automatic replacement.\n"
            f"Required Node {NODE_VERSION}, npm {NPM_VERSION}, pi {pi_version} "
            f"({architecture}). Do not edit the manifest.\n"
            "Remove the existing workshop VM (deletes its contents),\n"
            "then run setup again. On your Mac, from this preparation folder:\n\n"
            "  ./lab.sh remove &&\n"
            "  ./lab.sh setup"
        )


def image_build_ownership(path, uid, gid):
    """Change only freshly generated image-build paths, never participant state.

    Do not follow symlinks when transferring ownership. After unprivileged
    installation, root seals this generated runtime before it is published.
    """
    for item in (path, *path.rglob("*")):
        info = item.lstat()
        os.chown(item, uid, gid, follow_symlinks=False)
        if uid == 0 and not stat.S_ISLNK(info.st_mode):
            item.chmod(stat.S_IMODE(info.st_mode) & ~0o022)


def install_runtime(architecture, pi_version, *, image_build=False):
    """Reuse/stage the runtime; image builds execute npm/Pi as fixed lab-user.

    The legacy guest caller retains its existing root installation behavior.
    Image builds require root for OS packages, but pass explicit unprivileged
    credentials to package installation and version probes before sealing.
    """
    process_identity = {}
    verification = {}
    if image_build:
        if platform.system() != "Linux" or os.geteuid() != 0:
            raise RuntimeError("Runtime image build requires Linux build-time root")
        account = pwd.getpwnam("lab-user")
        if (account.pw_uid, account.pw_gid, account.pw_dir) != (1000, 1000, "/home/lab-user"):
            raise RuntimeError("Runtime image build requires lab-user 1000:1000")
        process_identity = {"user": 1000, "group": 1000, "extra_groups": []}
        verification = {"process_identity": process_identity}
    expected = runtime_versions(architecture, pi_version)
    if INSTALL_ROOT.is_symlink():
        raise RuntimeError("Refusing a symlink installation root")
    INSTALL_ROOT.mkdir(mode=0o755, exist_ok=True)
    require_root_owned(INSTALL_ROOT)
    with (INSTALL_ROOT / ".setup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix=".setup-", dir=INSTALL_ROOT) as temporary:
            stage = Path(temporary)
            home = stage / "home"
            environment = clean_environment(home, RUNTIME)
            if RUNTIME.exists() or RUNTIME.is_symlink():
                require_root_owned(RUNTIME)
                verify_runtime_manifest(RUNTIME, architecture, pi_version)
                if image_build:
                    home.chmod(0o700)
                    image_build_ownership(stage, 1000, 1000)
                verify_runtime(RUNTIME, environment, home, pi_version, **verification)
                install_packages(environment, home)
                print("[PASS] Existing Node/npm/pi runtime reused without reinstall.", flush=True)
                return
            install_packages(environment, home)
            node_arch, digest = NODE_IMAGES[architecture]
            name = f"node-v{NODE_VERSION}-linux-{node_arch}"
            archive = stage / "node.tar.xz"
            url = f"https://nodejs.org/dist/v{NODE_VERSION}/{name}.tar.xz"
            # Public download, no ambient proxy credentials or fallback endpoint.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            with archive.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                    raise RuntimeError("Node archive checksum mismatch; not extracted")
            with tarfile.open(archive, "r:xz") as bundle:
                bundle.extractall(stage, filter="data")
            runtime = stage / name
            environment = clean_environment(home, runtime)
            if image_build:
                home.chmod(0o700)
                image_build_ownership(stage, 1000, 1000)
            # Bootstrap npm inside the unpublished stage, then use it for pi.
            # Only these subprocesses drop identity; OS package work stays root.
            for package in (f"npm@{NPM_VERSION}", f"{PI_PACKAGE}@{pi_version}"):
                subprocess.run(
                    [str(runtime / "bin" / "npm"), "install", "--global", "--prefix", str(runtime),
                     "--ignore-scripts", "--no-audit", "--no-fund", package],
                    env=environment, cwd=home, stdin=subprocess.DEVNULL,
                    check=True, timeout=600, **process_identity,
                )
            verify_runtime(runtime, environment, home, pi_version, **verification)
            (runtime / "runtime_versions.json").write_text(json.dumps(expected, indent=2) + "\n")
            if image_build:
                image_build_ownership(runtime, 0, 0)
            require_root_owned(runtime)
            runtime.rename(RUNTIME)
            print("[PASS] Installed pinned Node/npm/pi runtime under /opt/secagent/runtime.",
                  flush=True)


def main(arguments=()):
    if arguments:
        print("Usage: prepare_guest.py (no arguments)", file=sys.stderr)
        return 2
    try:
        # Explicit trusted sibling paths work with isolated Python (-I), which
        # deliberately excludes the staged script directory from import search.
        source = Path(__file__).parent
        profile = runpy.run_path(str(source / "setup_guest_pi.py"))
        config = profile["load_runtime_config"]((source / "runtime_config.json").read_bytes())
        architecture = check_guest()
        os.umask(0o022)
        install_runtime(architecture, config["pi"])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[INFO] Tool installation only; credential isolation and lab readiness remain pending.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
