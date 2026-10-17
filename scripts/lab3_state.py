"""Private control/evidence for one explicit attempt, not a host run registry.

The selected directory is under the same XDG/default private workshop root as
host logs. Changing that root is not recovery; former roots are not discovered.
No registry, adoption, reset, migration or automatic resumption.
"""

import contextlib
import fcntl
import json
import os
import stat
import tempfile
import threading
import time
from pathlib import Path

from lab_log import private_state_directory


class Refused(RuntimeError):
    """Operation cannot safely proceed; preserve the attempt and its evidence."""


def selected_directory():
    """Select one Lab 3 directory; create only the shared private parent, not an attempt."""
    return private_state_directory() / "lab3"


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise Refused("Private regular control metadata required; existing files preserved")
        content = stream.read(65537)
    if len(content) > 65536:
        raise Refused("Control metadata exceeds its read bound; preserve it for inspection")
    return json.loads(content)


class State:
    def __init__(self, root, resources=None):
        self.mutex = threading.RLock()  # Foreground/watchdog facts; never held across a model task.
        self.root = Path(root).absolute()
        if ".." in self.root.parts or any(path.is_symlink() or (path / ".git").exists()
               for path in (self.root, *self.root.parents)):
            raise Refused("Explicit private non-repository control directory required")
        if resources is not None:
            self.root.mkdir(mode=0o700)  # Never adopt/recreate a prior attempt.
            self.data = {"resources": resources, "phase": "new", "fallback_used": False,
                         "outcome": "not-started"}
        info = self.root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise Refused("Private control directory required; existing contents preserved")
        self.root_identity = (info.st_dev, info.st_ino, info.st_mode, info.st_uid)
        if resources is None:
            self.data = private_json(self.root / "state.json")
        else:
            self.save()

    def check_directory(self):
        """Refuse a replaced/linked control root before evidence writes or deletion."""
        info = self.root.lstat()
        if ((info.st_dev, info.st_ino, info.st_mode, info.st_uid) != self.root_identity
                or any(path.is_symlink() for path in (self.root, *self.root.parents))):
            raise Refused("Private control directory identity changed; preserve both locations, no mutation.")

    def write(self, name, content):
        self.check_directory()
        if name != Path(name).name or name in ("", ".", "..", "lock", "ui.lock"):
            raise Refused("A single evidence filename is required")
        path = self.root / name
        if os.path.lexists(path):
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise Refused("Unsafe existing evidence file; preserved")
        with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def save(self):
        with self.mutex:
            self.write("state.json", json.dumps(self.data, indent=2).encode())

    def change(self, **values):
        """Persist a short foreground/watchdog fact group under the same mutex."""
        with self.mutex:
            self.data.update(values)
            self.save()

    def phase(self, name):
        self.change(phase=name)

    @contextlib.contextmanager
    def private_file(self, name):
        if name != Path(name).name or name in ("", ".", "..", "state.json", "lock", "ui.lock"):
            raise Refused("A single capture filename is required")
        self.check_directory()
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            yield stream

    @contextlib.contextmanager
    def lock(self, name="lock", *, wait_seconds=0):
        if name not in ("lock", "ui.lock"):
            raise Refused("Only lifecycle and observation locks are supported")
        self.check_directory()
        fd = os.open(self.root / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise Refused("Private lifecycle lock required")
            end = time.monotonic() + wait_seconds
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= end:
                        raise
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)
