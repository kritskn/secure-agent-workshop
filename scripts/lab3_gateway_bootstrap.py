"""Gateway-only privilege bootstrap; never imported or executed by the workload.

The caller mounts one explicitly selected engine socket at SOCKET, sets a
read-only rootfs, no-new-privileges and only SETUID/SETGID capabilities. No socket
permission changes, daemon discovery, credential reads or root fallback here.
"""

import os
import stat
import sys
from pathlib import Path

SOCKET = "/var/run/docker.sock"
GATEWAY = "/usr/local/bin/openshell-gateway"
IDENTITY = 1000
SWITCH_CAPS = (1 << 6) | (1 << 7)  # Linux CAP_SETGID and CAP_SETUID only.
ENVIRONMENT = {"HOME": "/state/home", "PATH": "/usr/local/bin:/usr/bin:/bin",
               "LANG": "C.UTF-8", "OPENSHELL_TELEMETRY_ENABLED": "false"}


class Refused(RuntimeError):
    """Only fixed public refusal categories, never native exception details."""


def process_status():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator and key in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd", "NoNewPrivs"):
            fields[key] = int(value.strip(), 10 if key == "NoNewPrivs" else 16)
    return fields


def require_capabilities(*, before_drop):
    expected = SWITCH_CAPS if before_drop else 0
    if process_status() != {"CapEff": expected, "CapPrm": expected, "CapInh": 0,
                            "CapAmb": 0, "CapBnd": SWITCH_CAPS, "NoNewPrivs": 1}:
        raise Refused("privilege configuration")


def socket_identity():
    info = os.lstat(SOCKET)
    if (not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o660
            or not 0 <= info.st_gid < 2 ** 32 - 1):
        raise Refused("socket metadata")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


def launch():
    """Drop every root UID/GID, verify, then exec one fixed gateway command."""
    if os.getresuid() != (0, 0, 0) or os.getresgid() != (0, 0, 0):
        raise Refused("bootstrap identity")
    require_capabilities(before_drop=True)
    identity = socket_identity()
    group = identity[3]
    os.umask(0o077)
    os.setgroups([group])  # Replace inherited groups; no initgroups/NSS lookup.
    os.setresgid(IDENTITY, IDENTITY, IDENTITY)
    os.setresuid(IDENTITY, IDENTITY, IDENTITY)
    if (os.getresuid() != (IDENTITY,) * 3 or os.getresgid() != (IDENTITY,) * 3
            or os.getgroups() != [group]):
        raise Refused("identity drop")
    require_capabilities(before_drop=False)
    if socket_identity() != identity:
        raise Refused("socket changed")
    if not os.access(SOCKET, os.R_OK | os.W_OK, effective_ids=True):
        raise Refused("socket access")
    os.chdir("/state/home")
    os.execve(GATEWAY, [GATEWAY, "--config", "/state/gateway.toml"], dict(ENVIRONMENT))


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args:
        print("Usage: gateway_bootstrap.py (no arguments; approved gateway container only)")
        return 0 if args == ["--help"] else 2
    try:
        launch()
    except Refused as error:
        print("[FAIL] Gateway bootstrap refused: " + str(error) + "; no fallback.", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - Redact unexpected native failures.
        print("[FAIL] Gateway bootstrap failed; no root fallback or permission changes.", file=sys.stderr)
        return 1
    return 0  # execve does not return on success.


if __name__ == "__main__":
    raise SystemExit(main())
