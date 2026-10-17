"""Create-only Lab 1 exercise initialization; configuration deploys separately."""

import inspect
import os
import platform
import stat
from pathlib import Path

import lab_tools as tools

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "labs/lab1/skill-poc"
FIXTURES = {
    "skills/fun/SKILL.md": ".agents/skills/fun/SKILL.md",
    "fixtures/auth.json": ".config/magic-portal/auth.json",
    "fixtures/flag.txt": ".local/share/line-dev-conf/flag.txt",
}


def initialize_home(home, files):
    """Guest-only: validate an empty mounted HOME, drop privilege, seed exercises."""
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("Lab 1 initialization requires Linux container root")
    info = home.lstat()
    if not stat.S_ISDIR(info.st_mode) or not os.path.ismount(home) or any(home.iterdir()):
        raise RuntimeError("Fresh empty mounted Lab 1 HOME required; existing state preserved")
    if (info.st_uid, info.st_gid) not in ((0, 0), (1000, 1000)):
        raise RuntimeError("Unexpected HOME ownership; no repair")
    if info.st_uid == 1000 and stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("Existing HOME permissions differ; no repair")
    os.umask(0o077)
    if info.st_uid == 0:
        home.chmod(0o700)
        os.chown(home, 1000, 1000, follow_symlinks=False)
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
    if (os.geteuid(), os.getegid(), os.getgroups()) != (1000, 1000, []):
        raise RuntimeError("Could not drop initializer privileges")
    for relative in (".pi/agent", "pi-log", "workshop/lab1"):
        (home / relative).mkdir(parents=True, mode=0o700)
    for relative, content in files.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(content)
    print("[PASS] Fresh Lab 1 exercise assets ready; configuration and credentials not installed.")


def initializer_source():
    """Freeze public exercise bytes for the isolated empty-HOME worker."""
    files = {destination: tools.source_bytes(str((ASSETS / source).relative_to(ROOT)))
             for source, destination in FIXTURES.items()}
    files["workshop/lab1/README.md"] = tools.source_bytes(str((ASSETS / "workspace/README.md").relative_to(ROOT)))
    return ("import os, platform, stat\nfrom pathlib import Path\n"
            + inspect.getsource(initialize_home) + "\n"
            + f"initialize_home(home, {files!r})\n")
