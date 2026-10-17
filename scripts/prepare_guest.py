"""Build the pinned Node/npm/Pi image runtime and validate installed versions.

The Docker recipe calls install_runtime with a clean environment. No standalone
installer, model credentials, agent sessions or personal configuration. Python
stdlib handles structured checks, verified downloads and staged publication.
"""

import fcntl
import hashlib
import json
import os
import platform
import pwd
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

INSTALL_ROOT = Path("/opt/secagent")
RUNTIME = INSTALL_ROOT / "runtime"
NODE_VERSION = "24.21.0"
NPM_VERSION = "12.1.0"
PI_PACKAGE = "@earendil-works/pi-coding-agent"
NODE_IMAGES = {
    "aarch64": ("arm64", "6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2"),
    "x86_64": ("x64", "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6"),
}


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
            text=True, capture_output=True, timeout=30, check=False,
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
    """Keep mismatched runtimes unchanged during image builds and checks."""
    recorded = json.loads((runtime / "runtime_versions.json").read_text())
    if recorded != runtime_versions(architecture, pi_version):
        raise RuntimeError(
            "Existing runtime differs; no automatic replacement.\n"
            f"Required Node {NODE_VERSION}, npm {NPM_VERSION}, pi {pi_version} "
            f"({architecture}). Do not edit the manifest.\n"
            "Preserve the existing image and preparation state. Review the runtime\n"
            "image/build diagnostics with your TA before retrying setup; do not\n"
            "delete preparation or edit installed files to bypass this check."
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


def install_runtime(architecture, pi_version):
    """Stage/reuse the image runtime with npm/Pi executed as fixed lab-user.

    Linux build-time root supplies OS packages. Package installation and version
    probes use explicit unprivileged credentials before root seals the runtime.
    """
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("Runtime image build requires Linux build-time root")
    account = pwd.getpwnam("lab-user")
    if (account.pw_uid, account.pw_gid, account.pw_dir) != (1000, 1000, "/home/lab-user"):
        raise RuntimeError("Runtime image build requires lab-user 1000:1000")
    process_identity = {"user": 1000, "group": 1000, "extra_groups": []}
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
                home.chmod(0o700)
                image_build_ownership(stage, 1000, 1000)
                verify_runtime(RUNTIME, environment, home, pi_version,
                               process_identity=process_identity)
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
            verify_runtime(runtime, environment, home, pi_version,
                           process_identity=process_identity)
            (runtime / "runtime_versions.json").write_text(json.dumps(expected, indent=2) + "\n")
            image_build_ownership(runtime, 0, 0)
            require_root_owned(runtime)
            runtime.rename(RUNTIME)
            print("[PASS] Installed pinned Node/npm/pi runtime under /opt/secagent/runtime.",
                  flush=True)
