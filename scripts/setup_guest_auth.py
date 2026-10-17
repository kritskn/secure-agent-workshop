"""Inspect or create the guest user's Pi Ollama Cloud credential, without echoing it."""

import json
import os
import platform
import pwd
import stat
import subprocess
import sys
import tempfile
import types
from pathlib import Path

MAX_KEY_BYTES = 4096
CONTAINER_HOME = Path("/home/lab-user")


def valid_key(key):
    return (isinstance(key, str) and 0 < len(key) <= MAX_KEY_BYTES
            and not key.startswith("!") and all(33 <= ord(char) <= 126 for char in key))


def credential_path():
    """Use the operator's passwd HOME and Lab 1's private enrollment metadata."""
    uid = os.geteuid()
    account = pwd.getpwuid(uid)
    home = Path(account.pw_dir)
    if (not home.is_absolute() or ".." in home.parts
            or Path(os.environ["HOME"]) != home):
        raise ValueError("Guest HOME must match the absolute operator account home")
    if os.getegid() != account.pw_gid:
        raise ValueError("Guest process must use the operator's primary group")
    for path in (home, home / ".pi", home / ".pi/agent"):
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid
                or info.st_gid != account.pw_gid
                or (mode & 0o022 if path == home else mode != 0o700)):
            raise ValueError(f"Unsafe Pi directory: {path}")
    return home / ".pi/agent/auth.json"


def credential_exists(path):
    """Accept one saved Ollama key with Lab 1's file metadata; never reveal it."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_gid != pwd.getpwuid(os.geteuid()).pw_gid
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not 0 < info.st_size <= 16384):
        raise ValueError("Existing auth.json is unsafe or incompatible; preserve it")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        raise ValueError("Existing auth.json is invalid; preserve it") from None
    entry = data.get("ollama") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or set(data) != {"ollama"}
            or not isinstance(entry, dict)
            or set(entry) != {"type", "key"}
            or entry["type"] != "api_key" or not valid_key(entry["key"])):
        raise ValueError("Existing auth.json is incompatible; preserve it")
    return True


def install(path, *, verify, replace=False):
    """Read stdin, verify, then atomically publish a private credential.

    No concurrent setup or external state edits.
    """
    previous = None
    if replace:
        if not credential_exists(path):
            raise ValueError("No saved credential to replace; run setup first")
        previous = path.lstat()
    elif os.path.lexists(path):
        raise ValueError("Credential appeared before enrollment; preserve it")
    raw = sys.stdin.buffer.read(MAX_KEY_BYTES + 1)
    if not raw or len(raw) > MAX_KEY_BYTES:
        raise ValueError("Empty or unsupported token input; no credential saved")
    try:
        key = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("Unsupported token input; no credential saved") from None
    if not valid_key(key):
        raise ValueError("Empty or unsupported token input; no credential saved")
    verify(key)
    content = json.dumps({"ollama": {"type": "api_key", "key": key}}) + "\n"
    descriptor, name = tempfile.mkstemp(prefix=".auth-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            # Reading auth may update atime; compare identity/content metadata,
            # not access time. Metadata safety is checked again independently.
            if not credential_exists(path):
                raise ValueError("Saved credential disappeared; no replacement attempted")
            current = path.lstat()
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(current, field) != getattr(previous, field) for field in fields):
                raise ValueError("Saved credential changed; no replacement attempted")
            os.replace(temporary, path)
        else:
            # Atomic create without overwriting an auth.json that appeared while
            # verifying. An interruption after this commit can leave both links;
            # later validation refuses that state rather than silently repairing.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print("[PASS] Verified Ollama credential saved privately.")


def container_credential_path():
    """Require ordinary identity; Docker may also list primary GID as supplementary."""
    if (platform.system() != "Linux" or os.geteuid() != 1000 or os.getegid() != 1000
            or any(group != 1000 for group in os.getgroups())
            or Path(os.environ["HOME"]) != CONTAINER_HOME
            or CONTAINER_HOME.is_symlink() or not os.path.ismount(CONTAINER_HOME)
            or stat.S_IMODE(CONTAINER_HOME.lstat().st_mode) != 0o700):
        raise ValueError("Private preparation HOME mount/identity required")
    return credential_path()


def check_container_catalog(path):
    """Bind enrollment to the workshop upstream before any credential read."""
    catalog = path.parent / "models.json"
    info = catalog.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 1000 or info.st_gid != 1000
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not 0 < info.st_size <= 2 * 1024 * 1024):
        raise ValueError("Unsafe preparation catalog; credentials preserved")
    data = json.loads(catalog.read_bytes())
    providers = data.get("providers") if isinstance(data, dict) else None
    provider = providers.get("ollama") if isinstance(providers, dict) else None
    models = provider.get("models") if isinstance(provider, dict) else None
    if (not isinstance(data, dict) or set(data) != {"providers"}
            or not isinstance(providers, dict)
            or set(providers) != {"ollama"} or not isinstance(provider, dict)
            or set(provider) != {"baseUrl", "api", "models"}
            or provider["baseUrl"] != "https://ollama.com/v1"
            or provider["api"] != "openai-completions"
            or not isinstance(models, list) or not models
            or any(not isinstance(model, dict) or "id" not in model
                   or not set(model) <= {"id", "reasoning", "thinkingLevelMap"}
                   for model in models)):
        raise ValueError("Preparation provider destination refused; credentials preserved")


def main(args=None):
    args = sys.argv[1:] if args is None else args
    # Candidate mode takes checker source, three controllers and four templates.
    candidate = bool(args) and args[0] in ("container-install", "container-replace")
    if (not args or (candidate and len(args) != 9)
            or (not candidate and (len(args) != 1 or args[0] != "container-check"))):
        print("[FAIL] Expected credential mode and its trusted public verification inputs.", file=sys.stderr)
        return 2
    mode = args[0].removeprefix("container-")
    checker = None
    previous_umask = os.umask(0o077)
    try:
        path = container_credential_path()
        check_container_catalog(path)
        if credential_exists(path) and mode != "replace" and not candidate:
            print("[PASS] Existing private Pi Ollama Cloud credential retained.")
            return 0
        if mode == "check":
            print("[INFO] Workshop Ollama Cloud credential is not configured.")
            return 10
        checker = types.ModuleType("candidate_check")
        # Trusted public checkout code, never candidate text.
        exec(compile(args[1], "check_guest.py", "exec"), checker.__dict__)  # noqa: S102
        names = (*checker.PROFILE_MODULES, *checker.PROFILE_TEMPLATES)
        controllers, templates = checker.load_profile_sources(
            {name: source.encode("utf-8") for name, source in zip(names, args[2:])})

        def verify(key):
            checker.check_candidate(controllers, templates, key)

        install(path, replace=mode == "replace", verify=verify)
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        if checker is not None and isinstance(error, checker.LiveCheckError):
            rejected = isinstance(error, checker.CredentialRejectedError)
            message = ("Candidate rejected for the selected model (401/403)." if rejected
                       else "Candidate verification incomplete; key not necessarily invalid.")
            print(f"[FAIL] {message} No candidate saved.", file=sys.stderr)
            return 4 if rejected else 3
        # Never include the key or raw JSON in diagnostics.
        print("[FAIL] Preparation credential state/input refused; no repair attempted.", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)
    return 0


if __name__ == "__main__":
    sys.exit(main())
