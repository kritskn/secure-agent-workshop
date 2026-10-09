"""Prepare the guest user's private workshop Pi profile without credentials."""

import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tarfile
import tempfile


CONTAINER_HOME = Path("/home/lab-user")
CONTAINER_ASSETS = {
    "scripts/runtime_config.json": "runtime_config.json",
    "agents/pi/settings.json": "settings.json",
    "agents/pi/models.json": "models.json",
    "agents/pi/extensions/observer.ts": "observer.ts",
}


def unique_fields(pairs):
    """Reject ambiguous duplicate JSON keys without echoing configuration data."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON configuration field")
        result[name] = value
    return result


def load_runtime_config(content):
    """Validate exact stable tool pins, not artifact availability or lab readiness."""
    if not 0 < len(content) <= 4096:
        raise ValueError("Missing or oversized runtime_config.json")
    try:
        config = json.loads(content, object_pairs_hook=unique_fields)
    except (ValueError, UnicodeError):
        raise ValueError("Invalid runtime_config.json") from None
    if not isinstance(config, dict) or set(config) != {"pi", "nono", "openshell"}:
        raise ValueError("runtime_config.json requires only pi, nono and openshell")
    for name, version in config.items():
        if (not isinstance(version, str) or len(version) > 64
                or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)):
            raise ValueError(f"{name} must be an exact stable version such as 1.0.0")
    return config


def render_settings(template):
    """Use native Pi defaults for the same setup and read-only profile checks."""
    try:
        settings = json.loads(template, object_pairs_hook=unique_fields)
    except (ValueError, UnicodeError):
        raise ValueError("Invalid Pi settings.json") from None
    if not isinstance(settings, dict) or settings.get("defaultProvider") != "ollama":
        raise ValueError("The workshop Pi profile requires Ollama Cloud")
    model = settings.get("defaultModel")
    if (not isinstance(model, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model)):
        raise ValueError("defaultModel must be one literal model ID without whitespace or wildcards")
    settings["enabledModels"] = list(dict.fromkeys(
        "ollama/" + entry for entry in (model, "gemma4:31b", "nemotron-3-super")))
    return (json.dumps(settings, indent=2) + "\n").encode("utf-8")


def directory(path, uid, *, home=False):
    """Return whether a safe directory exists; do not follow symlinks."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    forbidden = 0o022 if home else 0o077
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & forbidden:
        raise RuntimeError(f"Unsafe {path}; preserve it and review owner/mode/type.")
    return True


# Pi 1.0.2 presentation/history fields do not define workshop runtime policy.
# Resource loading, shell commands, provider routing and model controls are NOT UI.
UI_SETTINGS = {
    "lastChangelogVersion": (str,), "trackingId": (str,), "deviceId": (str,),
    "hideThinkingBlock": (bool,), "showCacheMissNotices": (bool,),
    "quietStartup": (bool, str), "collapseChangelog": (bool,),
    "doubleEscapeAction": (str,), "treeFilterMode": (str,),
    "editorPaddingX": (int,), "outputPad": (int,),
    "autocompleteMaxVisible": (int,), "showHardwareCursor": (bool,),
    "tuiMode": (str,), "fullscreenExitOutput": (str,),
    "fullscreenCopyOnSelect": (bool,),
}


def compatible_content(name, actual, expected):
    """Compare JSON policy, not formatting/UI state; executable code stays exact."""
    if name not in {"settings.json", "models.json"}:
        return actual == expected
    try:
        current = json.loads(actual.decode("utf-8"), object_pairs_hook=unique_fields)
        desired = json.loads(expected.decode("utf-8"), object_pairs_hook=unique_fields)
        if not isinstance(current, dict) or not isinstance(desired, dict):
            return False
        if name == "settings.json":
            for settings in (current, desired):
                if any(type(value) not in UI_SETTINGS[key]
                       for key, value in settings.items() if key in UI_SETTINGS):
                    return False
            current = {key: value for key, value in current.items() if key not in UI_SETTINGS}
            desired = {key: value for key, value in desired.items() if key not in UI_SETTINGS}
        # Canonical JSON preserves boolean/number distinctions (False != 0).
        return (json.dumps(current, sort_keys=True, allow_nan=False)
                == json.dumps(desired, sort_keys=True, allow_nan=False))
    except (ValueError, UnicodeError, RecursionError):
        return False


def matching_file(path, expected, uid):
    """Accept private compatible JSON or exact executable code; never rewrite."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
            or info.st_mode & 0o077
            or not compatible_content(path.name, path.read_bytes(), expected)):
        raise RuntimeError(f"Incompatible {path}; no existing file was replaced.")
    return True


def validate_models_store(profile, uid):
    """Allow Pi's optional private catalog cache, without reading or changing it."""
    path = profile / "models-store.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise RuntimeError(f"Unsafe Pi model cache at {path}; preserve it and review owner/mode/type.")


def create_file(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "wb") as destination:
        destination.write(content)


def setup(source, home, uid):
    """Preflight existing resources, then create only missing private assets."""
    load_runtime_config((source / "runtime_config.json").read_bytes())
    expected_settings = render_settings((source / "settings.json").read_bytes())
    if not home.is_absolute() or not directory(home, uid, home=True):
        raise RuntimeError(f"Missing or unsafe absolute guest home: {home}")
    root = home / ".pi"
    profile = root / "agent"
    extensions = profile / "extensions"
    logs = home / "pi-log"
    for path in (root, profile, extensions, logs):
        directory(path, uid)

    observer = source / "observer.ts"
    desired = ((profile / "settings.json", expected_settings),
               (profile / "models.json", (source / "models.json").read_bytes()),
               (extensions / "observer.ts", observer.read_bytes()))
    matches = [matching_file(path, content, uid) for path, content in desired]

    # Do not merge with unrelated Pi resources that bare Pi could auto-load.
    # Once installed, keep Pi's saved auth/session data on subsequent runs.
    if profile.exists():
        allowed = {"settings.json", "models.json", "extensions"}
        if all(matches):
            allowed.update({"auth.json", "sessions", "models-store.json"})
        if {p.name for p in profile.iterdir()} - allowed:
            raise RuntimeError(f"Existing Pi profile at {profile}; preserve it.")
        if extensions.exists() and {p.name for p in extensions.iterdir()} - {"observer.ts"}:
            raise RuntimeError(f"Existing Pi extensions at {extensions}; preserve them.")
        if all(matches):
            validate_models_store(profile, uid)
            auth = profile / "auth.json"
            if auth.is_symlink():
                raise RuntimeError(f"Unsafe credential file at {auth}; preserve it.")
            if auth.exists():
                info = auth.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                        or info.st_mode & 0o077):
                    raise RuntimeError(f"Unsafe credential file at {auth}; preserve it.")
            directory(profile / "sessions", uid, home=True)

    for path in (root, profile, extensions, logs):
        if not path.exists():
            path.mkdir(mode=0o700)
    for (path, content), exists in zip(desired, matches):
        if not exists:
            create_file(path, content)
    print(f"[PASS] Guest Pi profile ready: {profile}")
    print(f"[PASS] Private observer log directory ready: {logs}")
    print("[INFO] Pi credential is managed separately; live model access is unverified.")


def validate_container_home(home, uid, gid):
    """Check private HOME metadata/inventory without reading private contents."""
    if not home.is_absolute() or not home.is_dir() or home.is_symlink():
        raise RuntimeError("Missing or unsafe container HOME; no state changed")
    # Inspect metadata before reading managed configuration or creating anything.
    # rglob does not descend through directory symlinks; all links are refused.
    for path in (home, *home.rglob("*")):
        info = path.lstat()
        directory_mode = stat.S_ISDIR(info.st_mode)
        regular_mode = stat.S_ISREG(info.st_mode)
        if (info.st_uid != uid or info.st_gid != gid
                or not (directory_mode or regular_mode)
                or stat.S_IMODE(info.st_mode) != (0o700 if directory_mode else 0o600)
                or (regular_mode and info.st_nlink != 1)):
            raise RuntimeError("Unsafe container HOME metadata; existing state preserved")
    if {path.name for path in home.iterdir()} - {".pi", "pi-log"}:
        raise RuntimeError("Unrecognized container HOME contents; existing state preserved")
    pi_root = home / ".pi"
    if pi_root.exists() and {path.name for path in pi_root.iterdir()} - {"agent"}:
        raise RuntimeError("Unrecognized Pi HOME contents; existing state preserved")


def initialize_container_home(source, home, uid, gid):
    """Create/reuse public profile files after read-only private HOME validation.

    The caller supplies trusted staged templates and a bootstrapped HOME.
    Never adopt, repair, update conflicting configuration or read credentials.
    """
    validate_container_home(home, uid, gid)
    # The caller owns/validates the staging location, which is not participant HOME.
    # Refuse missing, linked, empty or oversized inputs before setup can write.
    for name in ("runtime_config.json", "settings.json", "models.json", "observer.ts"):
        path = source / name
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= 2 * 1024 * 1024):
            raise RuntimeError("Unsafe staged profile input; existing state preserved")
    # Reuse create-only preflight. Conflicts (including partial state with auth)
    # deliberately require the future controlled-update/reset flow, never repair.
    setup(source, home, uid)
    return home / ".pi" / "agent"


def initialize_container_volume(stream):
    """Internal container entry: bounded public stdin bundle, empty-only bootstrap.

    Host helper must validate the named volume and image and mount HOME without
    copy-up. Root is used only for temporary staging and an empty root-owned
    HOME; existing UID/GID 1000 state is checked after dropping privileges.
    """
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("Volume initialization requires Linux container root")
    if not os.path.ismount(CONTAINER_HOME) or CONTAINER_HOME.is_symlink():
        raise RuntimeError("Expected the private HOME volume mount")
    payload = stream.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise RuntimeError("Oversized public profile bundle")
    assets = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive:
            if (member.name not in CONTAINER_ASSETS or member.name in assets
                    or not member.isfile() or not 0 < member.size <= 2 * 1024 * 1024):
                raise RuntimeError("Unexpected public profile bundle member")
            with archive.extractfile(member) as source:
                assets[member.name] = source.read()
    if set(assets) != set(CONTAINER_ASSETS):
        raise RuntimeError("Incomplete public profile bundle")
    load_runtime_config(assets["scripts/runtime_config.json"])
    render_settings(assets["agents/pi/settings.json"])
    json.loads(assets["agents/pi/models.json"], object_pairs_hook=unique_fields)
    info = CONTAINER_HOME.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("Unsafe private HOME mount")
    if (info.st_uid, info.st_gid) == (0, 0):
        if any(CONTAINER_HOME.iterdir()):
            raise RuntimeError("Nonempty root-owned HOME preserved; no ownership repair")
    elif (info.st_uid, info.st_gid) != (1000, 1000):
        raise RuntimeError("Unexpected HOME ownership; state preserved")
    with tempfile.TemporaryDirectory(prefix="secagent-profile-") as temporary:
        source = Path(temporary)
        for name, content in assets.items():
            path = source / CONTAINER_ASSETS[name]
            create_file(path, content)
            os.chown(path, 1000, 1000, follow_symlinks=False)
        os.chown(source, 1000, 1000, follow_symlinks=False)
        if (info.st_uid, info.st_gid) == (0, 0):
            CONTAINER_HOME.chmod(0o700)
            os.chown(CONTAINER_HOME, 1000, 1000, follow_symlinks=False)
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
        if (os.geteuid(), os.getegid(), os.getgroups()) != (1000, 1000, []):
            raise RuntimeError("Could not drop initializer privileges")
        initialize_container_home(source, CONTAINER_HOME, 1000, 1000)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if len(args) != 1:
        print("Usage: python3 setup_guest_pi.py <staged-profile-directory>", file=sys.stderr)
        return 2
    if (platform.system() != "Linux" or platform.node() != "lima-secagent-lab"
            or os.geteuid() == 0):
        print("[FAIL] Run as the ordinary user inside secagent-lab only.", file=sys.stderr)
        return 1
    try:
        setup(Path(args[0]), Path(os.environ["HOME"]), os.geteuid())
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"[FAIL] Guest Pi profile setup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
