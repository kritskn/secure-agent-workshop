"""Private, append-only diagnostics for explicitly selected public tooling calls."""

import fcntl
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

HEADER = 'Secure Agent Workshop tooling log v1\n'
LIMIT = 65536


class LogRefused(RuntimeError):
    """Refuse unsafe or unavailable diagnostics without exposing their contents."""


def private_state_directory():
    """Select/create the existing private workshop root; never migrate state."""
    selected = os.environ.get('XDG_STATE_HOME')
    try:
        state = Path(selected) if selected else Path.home() / '.local/state'
    except (OSError, RuntimeError, ValueError):
        raise LogRefused('Cannot select private log storage; set an absolute XDG_STATE_HOME '
                         'in your Linux/user filesystem before retrying. No log was opened.') from None
    directory = state / 'secure-agent-workshop'
    reason = 'state path must be absolute and contain no parent traversal'
    try:
        if not state.is_absolute() or '..' in state.parts:
            raise ValueError(reason)
        reason = 'state path requires accessible real directories, not symlinks'
        for parent in reversed((state, *state.parents)):
            try:
                info = parent.lstat()
            except FileNotFoundError:
                parent.mkdir(mode=0o700)
                info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError(reason)
        info = state.lstat()
        reason = 'state directory must belong to the current user'
        if info.st_uid != os.getuid():
            raise ValueError(reason)
        mode = stat.S_IMODE(info.st_mode)
        reason = (f'state directory mode {mode:04o} permits group/world writes; '
                  'select a new, separate XDG_STATE_HOME directory rather than changing this existing one')
        if mode & 0o022:
            raise ValueError(reason)
        reason = 'workshop log directory must be a user-owned real directory with mode 0700'
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError(reason)
    except (OSError, ValueError):
        raise LogRefused(
            f"Cannot use private log directory {str(directory)!r}: {reason}. "
            "Choose an absolute XDG_STATE_HOME on a filesystem supporting private Unix permissions "
            "(on WSL, use the Linux filesystem, not /mnt/c). A missing directory is created privately. "
            "Existing state was not repaired or removed; new empty directories may remain after refusal."
        ) from None
    return directory


def default_log_path():
    """Keep the established tooling-log location and private-directory checks."""
    return private_state_directory() / 'lab-log.txt'


def clean(text):
    """Best-effort redaction, not a guarantee that arbitrary output is public."""
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = ''.join(char for char in text if char in '\n\t' or char.isprintable())
    text = re.sub(r'(?i)(https?://)[^\s/]+@', r'\1<REDACTED>@', text)
    text = re.sub(r'(?im)(authorization\s*[:=]\s*)[^\n]*', r'\1<REDACTED>', text)
    text = re.sub(r'(?i)(bearer\s+)\S+', r'\1<REDACTED>', text)
    text = re.sub(r'''(?i)((?:api[_-]?key|token|password|secret)["']?\s*[:=]\s*["']?)[^\s&"',}]+''',
                  r'\1<REDACTED>', text)
    return text


def progress(message, *, verbose=False, stream=None):
    """Emit authored stage facts only; never pass arbitrary private subprocess output."""
    if verbose:
        print("[DEBUG] " + clean(message), file=sys.stderr if stream is None else stream, flush=True)


def next_action(command, *, stream=None):
    """Highlight an authored next action, not a command inferred from error text."""
    stream = sys.stdout if stream is None else stream
    message = "[NEXT] " + command
    if stream.isatty() and os.environ.get("TERM", "dumb") != "dumb" and "NO_COLOR" not in os.environ:
        message = "\033[1;33m" + message + "\033[0m"
    print(message, file=stream, flush=True)


class Log:
    def __init__(self, path, terminal=None):
        self.path = path
        self.terminal = terminal
        self.stream = None

    def __enter__(self):
        descriptor = None
        reason = 'cannot open the log; inspect this path for access or file-type conflicts'
        try:
            flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            try:
                descriptor = os.open(self.path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                descriptor = os.open(self.path, flags)
                created = False
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                reason = 'log must be a regular file with exactly one hardlink; preserve this conflicting path'
                raise ValueError(reason)
            if info.st_uid != os.getuid():
                reason = 'log belongs to another user; preserve it and select your own private state directory'
                raise ValueError(reason)
            mode = stat.S_IMODE(info.st_mode)
            if mode != 0o600:
                reason = (f'log permissions are {mode:04o}, expected 0600; select XDG_STATE_HOME on '
                          'a filesystem supporting private Unix permissions (on WSL, use the Linux filesystem)')
                raise ValueError(reason)
            reason = ('exclusive log lock is unavailable; finish any other setup/reset using this log '
                      'before retrying, or select private state storage that supports file locking')
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            reason = 'cannot read/write the log; check storage access and free space'
            self.stream = os.fdopen(descriptor, 'r+', encoding='utf-8', errors='replace')
            descriptor = None
            if created:
                self.stream.write(HEADER)
                self.stream.flush()
            elif self.stream.read(len(HEADER)) != HEADER:
                reason = ('existing file has no recognized workshop log header; preserve it and '
                          'select a separate private XDG_STATE_HOME before retrying')
                raise ValueError(reason)
            return self
        except (OSError, ValueError):
            if self.stream is not None:
                self.stream.close()
            if descriptor is not None:
                os.close(descriptor)
            raise LogRefused(
                f"Cannot safely append {str(self.path)!r}: {reason}. "
                "Existing contents were not overwritten; a newly created file may be empty or partial. "
                "No automatic chmod, deletion or retry."
            ) from None

    def event(self, message):
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')  # noqa: UP017 - Python 3.9 has no datetime.UTC.
        line = f'[DEBUG {stamp}] {message}\n'
        self.output(line)
        if self.terminal is not None:
            try:
                self.terminal.write(line)
                self.terminal.flush()
            except OSError:
                raise LogRefused('Verbose diagnostic output is unavailable; check the terminal connection. '
                                 'Existing log entries are retained; no automatic retry.') from None

    def output(self, text):
        # Redact before truncating so a cut cannot remove a sensitive-field label.
        text = clean(text)
        if len(text.encode('utf-8')) > LIMIT:
            text = '[output truncated; tail follows]\n' + text.encode('utf-8')[-LIMIT:].decode('utf-8', errors='replace')
        try:
            self.stream.write(text + ('' if text.endswith('\n') else '\n'))
            self.stream.flush()
        except (OSError, ValueError):
            raise LogRefused(f"Cannot append {str(self.path)!r}; check storage access and free space. "
                             "The operation stopped; earlier changes/log entries may remain. "
                             "No automatic retry.") from None

    def __exit__(self, *exception):
        if self.stream is not None:
            self.stream.close()
