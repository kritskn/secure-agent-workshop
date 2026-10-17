"""Read bounded, workload-reported Pi state; never return transcript contents.

The controller must validate workload identity before executing this reader in
that workload. Results are untrusted workload reports, not authoritative policy
evidence, provider settlement or sufficient CHECK eligibility. The menu is only
a reported path, not validated content. Import is inert; controller integration
and its error/privacy boundary remain a separate slice.
"""

import json
import os
import stat
from itertools import islice
from pathlib import Path

LIMIT = 8 * 1024 * 1024


def observe(parent):
    roots = list(islice(parent.glob("secagent-lab3-pi-*"), 2))
    if not roots:
        return {"fresh": True, "reason": None, "menu": None}
    if len(roots) != 1 or roots[0].is_symlink():
        raise ValueError("Ambiguous workspace")
    root = roots[0]
    paths = list(islice((root / "sessions").rglob("*.jsonl"), 2))
    if len(paths) > 1:
        raise ValueError("Ambiguous session")
    last = {}
    if paths:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(paths[0], flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Regular session file required")
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Session bound exceeded")
        for line in raw.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue  # Pi may still be appending the last line.
            message = entry.get("message")
            if isinstance(message, dict):
                last = message
    reason = last.get("stopReason") if last.get("role") == "assistant" else None
    return {"fresh": False,
            "reason": reason if reason in ("stop", "error", "aborted") else None,
            "menu": str(root / "work/menu.html")}


if __name__ == "__main__":
    print(json.dumps(observe(Path("/tmp"))))
