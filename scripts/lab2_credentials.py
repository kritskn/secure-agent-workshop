"""Docker-internal selected-key provisioning source; import/help never read keys.

Only the trusted temporary worker mounts preparation, read-only. The agent gets
one dedicated read-only key store outside child grants; the collector gets a
separate digest/facts store, NOT the key. No credential bytes cross host output,
argv, environment, build context or source. Native transfer needs new approval.
Private volume storage is workshop convenience, not production secret management.
"""

import hashlib
import json
import os
import platform
import stat
import sys
from pathlib import Path


def selected_key(auth, helpers, source_home):
    source = helpers.private_profile(source_home)
    auth.check_container_catalog(source)
    if not auth.credential_exists(source):
        raise ValueError("Selected preparation credential required")
    before = helpers.credential_stamp(source.lstat())
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        if helpers.credential_stamp(os.fstat(stream.fileno())) != before:
            raise ValueError("Selected credential changed")
        content = stream.read(16385)
        if (helpers.credential_stamp(os.fstat(stream.fileno())) != before
                or helpers.credential_stamp(source.lstat()) != before):
            raise ValueError("Selected credential changed")
    if not 0 < len(content) <= 16384:
        raise ValueError("Selected credential bound")
    key = json.loads(content)["ollama"]["key"]
    if not auth.valid_key(key):
        raise ValueError("Selected credential refused")
    return key


def write_selected(auth, helpers, source_home, secrets, receipts):
    for path in (secrets, receipts):
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise ValueError("Fresh separate empty private stores required")
    if secrets.samefile(receipts) or any(source_home.samefile(path) for path in (secrets, receipts)):
        raise ValueError("Separate stores required")
    key = selected_key(auth, helpers, source_home)
    entries = ((secrets / "ollama-key", key.encode()),
               (receipts / "key.sha256", hashlib.sha256(key.encode()).hexdigest().encode() + b"\n"))
    for path, content in entries:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as output:
            output.write(content)


def guest_main(auth, helpers):
    """New empty mounts only, root setup followed by ordinary private copy."""
    try:
        source = Path("/preparation-home")
        secrets, receipts = Path("/secrets"), Path("/receipts")
        if (platform.system() != "Linux" or os.geteuid() != 0
                or not os.path.ismount(source) or source.is_symlink()
                or not os.statvfs(source).f_flag & os.ST_RDONLY):
            raise ValueError("Isolated read-only preparation worker required")
        for path in (secrets, receipts):
            info = path.lstat()
            if (not os.path.ismount(path) or not stat.S_ISDIR(info.st_mode)
                    or any(path.iterdir()) or (info.st_uid, info.st_gid) != (0, 0)):
                raise ValueError("Fresh root-owned mounted stores required")
        for path in (secrets, receipts):
            path.chmod(0o700)
            os.chown(path, 1000, 1000, follow_symlinks=False)
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
        os.umask(0o077)
        if (os.geteuid(), os.getegid(), os.getgroups()) != (1000, 1000, []):
            raise ValueError("Worker privilege drop required")
        write_selected(auth, helpers, source, secrets, receipts)
    except Exception:  # noqa: BLE001 - Credential exceptions may contain key bytes; emit only the fixed refusal.
        print("[FAIL] Selected Lab 2 credential provisioning refused; partial new stores retained.", file=sys.stderr)
        return 1
    print("[PASS] Selected Lab 2 key/digest ready privately; no provider request.")
    return 0


def public_source():
    import lab_tools as tools  # Host-only public transport, never called by guest.
    # No code imports from the guest's edited project/PYTHONPATH. All three
    # public modules are supplied explicitly by the source-approved host driver.
    sources = {name: tools.source_bytes("scripts/" + name).decode() for name in
               ("setup_guest_auth.py", "lab_credential.py", "lab2_credentials.py")}
    return ("import types,sys\n"
        "modules = {}\n"
        f"sources = {sources!r}\n"
        "for name, source in sources.items():\n"
        "    module = types.ModuleType(name[:-3])\n"
        "    module.__file__ = '/opt/secagent/' + name\n"
        "    modules[name] = module\n"
        "    exec(compile(source, name, 'exec'), module.__dict__)\n"
        "raise SystemExit(modules['lab2_credentials.py'].guest_main(\n"
        "    modules['setup_guest_auth.py'], modules['lab_credential.py']))\n").encode()
