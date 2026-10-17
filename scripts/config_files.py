"""Filesystem-only configuration deployment; no Docker, prompts or tool execution.

Callers select public source directories and destination paths relative to HOME.
They own lifecycle checks and consent. No credential/runtime source discovery.
Serialize setup and external edits; metadata rechecks are not arbitrary-writer CAS.
"""

import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class Refused(RuntimeError):
    """Path-only diagnostic with explicit partial publication information."""

    def __init__(self, path, reason, *, written=(), created_directories=()):
        self.path = Path(path)
        self.reason = reason
        self.written = tuple(written)
        self.created_directories = tuple(created_directories)
        super().__init__(
            f"{str(self.path)!r}: {reason}. Preserve existing work and inspect this path "
            "before retrying; no automatic repair. "
            f"Published files: {[str(p) for p in self.written]!r}; "
            f"created directories: {[str(p) for p in self.created_directories]!r}."
        )


@dataclass(frozen=True)
class Source:
    relative: Path
    content: bytes = field(repr=False)
    stamp: tuple


@dataclass(frozen=True)
class File:
    source: Path
    destination: Path
    content: bytes = field(repr=False)
    source_stamp: tuple
    destination_stamp: object
    status: str


@dataclass(frozen=True)
class Plan:
    home: Path
    mappings: tuple
    uid: int
    gid: int
    file_mode: int
    directory_mode: int
    files: tuple
    directories: tuple

    @property
    def additions(self):
        return tuple(file.destination for file in self.files if file.status == "added")

    @property
    def replacements(self):
        return tuple(file.destination for file in self.files if file.status == "changed")


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _ancestors(path):
    for parent in reversed(path.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise Refused(parent, "parent is not a real directory (symlinks are refused)")


def _owner_mode(path, info, uid, gid, mode):
    if info.st_uid != uid:
        raise Refused(path, f"owner UID {info.st_uid} differs from expected UID {uid}")
    if gid is not None and info.st_gid != gid:
        raise Refused(path, f"group GID {info.st_gid} differs from expected GID {gid}")
    actual = stat.S_IMODE(info.st_mode)
    if mode is not None and actual != mode:
        raise Refused(path, f"permissions {actual:04o} differ from expected {mode:04o}")
    if mode is None and actual & 0o7022:
        raise Refused(path, f"permissions {actual:04o} include special or group/world-write bits")


def _directory(path, uid, gid, mode=None, *, missing=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise Refused(path, "required directory is missing") from None
    if not stat.S_ISDIR(info.st_mode):
        raise Refused(path, "expected a real directory; symlinks and other file types are refused")
    if uid is not None:  # Explicit public sources are trusted, not private state.
        _owner_mode(path, info, uid, gid, mode)
    # Unrelated child changes must not invalidate a managed-parent identity.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _read(path, uid, gid=None, mode=None, *, missing=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None, None
        raise Refused(path, "required source file is missing") from None
    if not stat.S_ISREG(info.st_mode):
        raise Refused(path, "expected a regular file; symlinks and special files are refused")
    if info.st_nlink != 1:
        raise Refused(path, f"file has {info.st_nlink} hardlinks; expected exactly one")
    if uid is not None:
        _owner_mode(path, info, uid, gid, mode)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        if _stamp(os.fstat(stream.fileno())) != _stamp(info):
            raise Refused(path, "file changed before reading")
        content = stream.read()
        if _stamp(os.fstat(stream.fileno())) != _stamp(info):
            raise Refused(path, "file changed while reading")
    return content, _stamp(info)


def _sources(root):
    _directory(root, None, None)
    for path in sorted(root.iterdir()):
        if stat.S_ISDIR(path.lstat().st_mode):
            yield from _sources(path)
        else:
            yield path


def collect_file(path):
    """Snapshot a trusted public file, not credentials; never read its siblings."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise Refused(path, "source must not contain parent traversal")
    try:
        _ancestors(path)
        content, stamp = _read(path, None)
        return Source(Path(path.name), content, stamp)
    except OSError as error:
        affected = Path(error.filename) if error.filename else path
        raise Refused(affected, f"source inspection failed (errno {error.errno}); check access") from None


def collect(source):
    """Snapshot a trusted public tree, not private state; no source UID/mode policy."""
    source = Path(source).absolute()
    if ".." in source.parts:
        raise Refused(source, "source must not contain parent traversal")
    affected = source
    try:
        _ancestors(source)
        files = []
        for path in _sources(source):
            affected = path
            content, stamp = _read(path, None)
            files.append(Source(path.relative_to(source), content, stamp))
        return tuple(files)
    except OSError as error:
        affected = Path(error.filename) if error.filename else affected
        raise Refused(affected, f"source inspection failed (errno {error.errno}); check access") from None


def _parents(home, destination, uid, gid, mode):
    result = {home: _directory(home, uid, gid)}
    path = home
    for part in destination.relative_to(home).parts[:-1]:
        path = path / part
        result[path] = _directory(path, uid, gid, mode, missing=True)
    return result


def inspect(home, mappings, *, uid=None, gid=None, file_mode=0o600, directory_mode=0o700):
    """Snapshot recursive source files and managed destinations without writes.

    mappings: (source_directory, relative_destination_directory) pairs. Empty
    source directories create nothing. Existing destination modes must match;
    newly published files/directories use the requested safe modes. Config bytes
    are opaque, including malformed JSON/TOML. No destination deletion planning.
    """
    home = Path(home).absolute()
    uid = os.geteuid() if uid is None else uid
    gid = os.getegid() if gid is None else gid
    for mode in (file_mode, directory_mode):
        if type(mode) is not int or mode < 0 or mode > 0o777 or mode & 0o022:
            raise Refused(home, "requested permissions must exclude special/group/world-write bits")
    if not file_mode & 0o400 or directory_mode & 0o700 != 0o700:
        raise Refused(home, "files need owner-read and directories need owner read/write/search permissions")
    if ".." in home.parts:
        raise Refused(home, "HOME must not contain parent traversal")
    files, directories, selected = [], {}, []
    affected = home
    try:
        _ancestors(home)
        _directory(home, uid, gid)
        destinations = set()
        for source, relative in mappings:
            source, relative = Path(source).absolute(), Path(relative)
            affected = source
            if ".." in source.parts or relative.is_absolute() or ".." in relative.parts:
                raise Refused(source, "mapping must use a source directory and HOME-relative destination")
            if source == home or home in source.parents or source in home.parents:
                raise Refused(source, "source and destination HOME trees must be separate")
            selected.append((source, relative))
            for entry in collect(source):
                path = source / entry.relative
                content, source_stamp = entry.content, entry.stamp
                destination = home / relative / path.relative_to(source)
                if (destination in destinations or any(
                        other in destination.parents or destination in other.parents
                        for other in destinations)):
                    raise Refused(destination, "source mappings overlap at a file destination")
                destinations.add(destination)
                affected = destination
                directories.update(_parents(home, destination, uid, gid, directory_mode))
                actual, destination_stamp = _read(destination, uid, gid, file_mode, missing=True)
                status = "added" if destination_stamp is None else (
                    "matching" if actual == content else "changed")
                files.append(File(path, destination, content, source_stamp, destination_stamp, status))
    except OSError as error:
        affected = Path(error.filename) if error.filename else affected
        raise Refused(affected, f"filesystem inspection failed (errno {error.errno}); check access") from None
    return Plan(home, tuple(selected), uid, gid, file_mode, directory_mode,
                tuple(files), tuple(directories.items()))


def publish(plan, *, approved):
    """Return written paths, or None on decline (zero writes, including additions).

    Caller authorization covers the entire inspected plan. Recheck all inputs
    before writes, then each file/parent before publication. A partial failure
    retains completed writes and reports them; it never rolls back other files.
    """
    if approved is not True:
        return None
    written, created = [], []
    affected = plan.home
    try:
        if (os.geteuid(), os.getegid()) != (plan.uid, plan.gid):
            raise Refused(plan.home, "publication must run as the destination owner/group; no ownership repair")
        current = inspect(plan.home, plan.mappings, uid=plan.uid, gid=plan.gid,
                          file_mode=plan.file_mode, directory_mode=plan.directory_mode)
        if current != plan:
            old_files = {file.destination: file for file in plan.files}
            new_files = {file.destination: file for file in current.files}
            affected = next((path for path in dict.fromkeys((*old_files, *new_files))
                             if old_files.get(path) != new_files.get(path)), plan.home)
            old_directories = dict(plan.directories)
            if affected == plan.home:
                affected = next((path for path, stamp in current.directories
                                 if old_directories.get(path) != stamp), plan.home)
            raise Refused(affected, "configuration inputs/destinations changed; inspect and obtain consent again")
        directories = dict(plan.directories)
        for path, previous in plan.directories:
            affected = path
            if previous is None:
                path.mkdir(mode=plan.directory_mode)
                created.append(path)
                path.chmod(plan.directory_mode)
                directories[path] = _directory(path, plan.uid, plan.gid, plan.directory_mode)
        for file in plan.files:
            affected = file.destination
            _ancestors(plan.home)
            for path, stamp in _parents(plan.home, affected, plan.uid, plan.gid,
                                        plan.directory_mode).items():
                if stamp != directories[path]:
                    raise Refused(path, "managed parent changed after inspection")
            source, source_stamp = _read(file.source, None)
            if source != file.content or source_stamp != file.source_stamp:
                raise Refused(file.source, "source changed after inspection")
            _, stamp = _read(affected, plan.uid, plan.gid, plan.file_mode, missing=True)
            if stamp != file.destination_stamp:
                raise Refused(affected, "destination changed after inspection")
            if file.status == "matching":
                continue
            descriptor, name = tempfile.mkstemp(prefix=".config-", dir=affected.parent)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    os.fchmod(stream.fileno(), plan.file_mode)
                    stream.write(file.content)
                    stream.flush()
                    os.fsync(stream.fileno())
                _, stamp = _read(affected, plan.uid, plan.gid, plan.file_mode, missing=True)
                if stamp != file.destination_stamp:
                    raise Refused(affected, "destination changed before publication")
                if file.status == "added":
                    os.link(temporary, affected)  # No overwrite if a destination appears.
                else:
                    os.replace(temporary, affected)
                written.append(affected)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as error:
                    raise Refused(temporary, f"temporary file cleanup failed (errno {error.errno})") from None
            actual, _ = _read(affected, plan.uid, plan.gid, plan.file_mode)
            if actual != file.content:
                raise Refused(affected, "installed bytes did not verify")
    except (Refused, OSError, KeyboardInterrupt) as error:
        if isinstance(error, Refused):
            affected, reason = error.path, error.reason
        elif isinstance(error, KeyboardInterrupt):
            reason = "deployment interrupted; completed writes were not rolled back"
        else:
            affected = Path(error.filename) if error.filename else affected
            reason = f"filesystem publication failed (errno {error.errno}); check access"
        raise Refused(affected, reason, written=written, created_directories=created) from None
    return tuple(written)
