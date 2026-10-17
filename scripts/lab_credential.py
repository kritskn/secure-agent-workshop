"""Lab 1 private credential bootstrap and offline reset preflight.

Transport accepts the lifecycle's checked Docker runner and immutable image ID.
Only public Python source crosses host stdin; credential bytes stay in Docker.
The caller must serialize preparation/lab setup and hold the destination unused.
Importing this module does not inspect Docker, HOME or credentials.
"""

import json
import os
import platform
import re
import stat
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARATION_VOLUME = "secagent-vol"
LAB_VOLUME = "secagent-lab1-home"
SOURCE_HOME = Path("/preparation-home")
TARGET_HOME = Path("/home/lab-user")
OWNER = "secure-agent-workshop"


def private_profile(home):
    """Inspect path metadata only; never follow a HOME/profile symlink."""
    for path in (home, home / ".pi", home / ".pi/agent"):
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 1000
                or info.st_gid != 1000 or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("Unsafe private profile")
    return home / ".pi/agent/auth.json"


def credential_stamp(info):
    """Detect replacement/content/permission changes, ignoring read-access time."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def copy_credential(auth, source_home, target_home):
    """Copy validated preparation auth into a create-only private lab profile.

    auth is the unchanged preparation validation module. Caller supplies isolated
    mounted homes, ordinary UID/GID 1000, and a read-only preparation mount.
    Failures preserve existing files; a failed write may leave partial new auth.
    """
    source = private_profile(source_home)
    target = private_profile(target_home)
    if source_home.samefile(target_home):
        raise ValueError("Separate lab HOME required")
    # Refuse even a dangling symlink or empty existing auth before reading a key.
    if os.path.lexists(target):
        raise ValueError("Existing lab credential preserved")
    # Preparation selects the key; destination configuration is tool-owned.
    auth.check_container_catalog(source)
    before = credential_stamp(source.lstat())
    if not auth.credential_exists(source):
        raise ValueError("Preparation credential required")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    with os.fdopen(os.open(source, flags), "rb") as stream:
        if credential_stamp(os.fstat(stream.fileno())) != before:
            raise ValueError("Preparation credential changed")
        content = stream.read(16385)
        if (credential_stamp(os.fstat(stream.fileno())) != before
                or credential_stamp(source.lstat()) != before):
            raise ValueError("Preparation credential changed")
    if not 0 < len(content) <= 16384:
        raise ValueError("Preparation credential size refused")
    # Serialize only the selected key, not raw auth-file text or duplicate fields.
    key = json.loads(content)["ollama"]["key"]
    credential = (json.dumps({"ollama": {"type": "api_key", "key": key}}) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(target, flags, 0o600), "wb") as output:
        output.write(credential)


def guest_main(auth, *, check_only=False):
    """Guest-only entry; diagnostics never contain paths, JSON or exception text."""
    try:
        if (platform.system() != "Linux" or os.geteuid() != 1000
                or os.getegid() != 1000 or any(gid != 1000 for gid in os.getgroups())
                or not os.path.ismount(SOURCE_HOME)
                or not os.statvfs(SOURCE_HOME).f_flag & os.ST_RDONLY):
            raise ValueError("Isolated credential transfer required")
        if check_only:
            path = private_profile(SOURCE_HOME)
            auth.check_container_catalog(path)
            if not auth.credential_exists(path):
                raise ValueError("Preparation credential required")
        else:
            if not os.path.ismount(TARGET_HOME):
                raise ValueError("Separate mounted lab HOME required")
            os.umask(0o077)
            copy_credential(auth, SOURCE_HOME, TARGET_HOME)
    except (OSError, ValueError, KeyError):
        action = "Preparation credential check" if check_only else "Lab credential copy"
        print(f"[FAIL] {action} refused; existing state preserved.", file=sys.stderr)
        return 1
    print("[PASS] Lab credential ready (not checked online).")
    return 0


def public_guest_source(*, check_only=False):
    """Carry current public validators without modifying the distributed image."""
    sources = []
    for name in ("setup_guest_auth.py", "lab_credential.py"):
        path = ROOT / "scripts" / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Unsafe public credential helper")
        sources.append(path.read_text())
    return (
        "import types\n"
        "auth = types.ModuleType('preparation_auth')\n"
        f"exec(compile({sources[0]!r}, 'setup_guest_auth.py', 'exec'), auth.__dict__)\n"
        "guest = {'__name__': 'lab_credential_guest', "
        "'__file__': '/opt/secagent/lab_credential.py'}\n"
        f"exec(compile({sources[1]!r}, 'lab_credential.py', 'exec'), guest)\n"
        f"raise SystemExit(guest['guest_main'](auth, check_only={check_only!r}))\n"
    ).encode()


def validate_volume(metadata, name, role):
    labels = metadata.get("Labels") or {}
    if (metadata.get("Name") != name or metadata.get("Driver") != "local"
            or metadata.get("Scope") != "local" or metadata.get("Options")
            or labels.get("org.secagent.owner") != OWNER
            or labels.get("org.secagent.role") != role
            or labels.get("org.secagent.schema") != "1"):
        raise ValueError("Workshop volume identity refused")


def transfer(run, image_id, *, check_only=False):
    """Copy or check using a validated image/socket; no enrollment or models.

    run(arguments, payload=None) is the checked Docker transport: it captures
    both streams without printing, raises on failure and returns stdout as text.
    Raw Docker diagnostics are suppressed.
    Copy refuses destination references (even stopped containers). Check-only
    mounts just the read-only preparation source; it never touches a lab HOME.
    Neither mode creates volumes or adopts partial state.
    """
    try:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Immutable checked image required")
        payload = public_guest_source(check_only=check_only)
        volumes = [(PREPARATION_VOLUME, "preparation-home")]
        destination_mount = []
        if not check_only:
            volumes.append((LAB_VOLUME, "lab1-home"))
            destination_mount = ["--mount", "type=volume,src=" + LAB_VOLUME
                                 + ",dst=" + str(TARGET_HOME) + ",volume-nocopy"]
        for name, role in volumes:
            metadata = json.loads(run(["volume", "inspect", name]))
            if not isinstance(metadata, list) or len(metadata) != 1:
                raise ValueError("Unexpected volume inspection")
            validate_volume(metadata[0], name, role)
        if not check_only:
            references = run(["container", "ls", "--all", "--quiet",
                              "--filter", "volume=" + LAB_VOLUME])
            if references.strip():
                raise ValueError("Lab HOME is already in use")
        run(["run", "--rm", "--pull", "never", "--name",
             "secagent-lab1-auth-" + uuid.uuid4().hex,
             "--label", "org.secagent.owner=" + OWNER,
             "--label", "org.secagent.role=" + (
                 "lab1-credential-check" if check_only else "lab1-enrollment"),
             "--network", "none", "--read-only", "--user", "1000:1000",
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
             "--pids-limit", "32", "--memory", "256m", "--cpus", "1",
             "--workdir", "/tmp",
             "--mount", "type=volume,src=" + PREPARATION_VOLUME
             + ",dst=" + str(SOURCE_HOME) + ",readonly,volume-nocopy",
             *destination_mount,
             "--interactive", image_id, "python3", "-I", "-B", "-c",
             "import sys; exec(compile(sys.stdin.buffer.read(), '<public-helper>', 'exec'))"],
            payload=payload)
    except Exception:  # noqa: BLE001 - Runner errors may contain private Docker output.
        # Never relay raw diagnostics across the credential transport boundary.
        if check_only:
            raise RuntimeError("Preparation credential check refused; state preserved.") from None
        raise RuntimeError("Lab credential transfer refused; state preserved. "
                           "A failed copy may leave partial new lab auth.") from None
