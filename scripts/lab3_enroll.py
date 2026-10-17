"""Trusted enrollment child; source is transported without provider key material."""

import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path("/preparation-home")
PROVIDER = "lab3-ollama-run"


def enroll(auth, helpers, selection):
    """Use preparation's validator, exposing the key only to the operator child."""
    try:
        if (sys.platform != "linux" or os.geteuid() != 1000 or os.getegid() != 1000
                or any(group != 1000 for group in os.getgroups())
                or not os.path.ismount(SOURCE)
                or not os.statvfs(SOURCE).f_flag & os.ST_RDONLY):
            raise ValueError("Read-only preparation mount and ordinary identity required")
        key = selection.selected_key(auth, helpers, SOURCE)
        subprocess.run(
            ["/usr/local/bin/openshell", "provider", "create", "--name", PROVIDER,
             "--type", "lab3-ollama", "--credential", "LAB3_OLLAMA_API_KEY"],
            env={"HOME": "/state/home", "PATH": "/usr/local/bin:/usr/bin:/bin",
                 "LAB3_OLLAMA_API_KEY": key},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=30, check=True)
    except (OSError, ValueError, RuntimeError, TypeError, LookupError, subprocess.SubprocessError):
        print("[FAIL] Lab 3 enrollment refused; no credential details emitted.")
        return 1
    print("[PASS] Lab 3 provider created privately; no model request made.")
    return 0
