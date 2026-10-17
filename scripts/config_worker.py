"""One-shot public configuration volume worker; no tools or credentials.

The host supplies this code and config_files through trusted argv source. File
contents travel on stdin, never argv/output. Import is inert; tests call handle
with synthetic directories instead of running a container.
"""

import base64
import json
import os
import sys
import tempfile
from pathlib import Path

import config_files

DESTINATIONS = {"herdr": ".config/herdr", "fresh": ".config/fresh", "pi": ".pi/agent"}
PI_RUNTIME = ("auth.json", "sessions", "models-store.json")


def check_pi_path(relative, location):
    """Reject runtime entries, including descendants, without reading their bytes."""
    if Path(relative).parts and Path(relative).parts[0] in PI_RUNTIME:
        raise config_files.Refused(location, "reserved Pi runtime path; keep credentials, sessions "
                                   "and model cache outside public configuration, then rerun setup; "
                                   "no configuration files were written")


def summary(plan):
    """Only destination metadata/status crosses the worker boundary, not bytes."""
    return {
        "files": [{"path": str(file.destination), "status": file.status,
                   "stamp": list(file.destination_stamp) if file.destination_stamp else None}
                  for file in plan.files],
        "directories": [[str(path), list(stamp) if stamp else None]
                        for path, stamp in plan.directories],
    }


def handle(request, home, *, destinations=None):
    """Stage, inspect and publish using trusted tool-name/HOME-relative mappings.

    Omission retains the default layout. Request data cannot select destinations;
    the trusted caller supplies non-overlapping roots, with Pi under the "pi" key.
    Filesystem inspection/publication remains owned by config_files.
    """
    try:
        destinations = dict(DESTINATIONS if destinations is None else destinations)
        roots = []
        if not destinations:
            raise ValueError("Empty destination mapping")
        for name, destination in destinations.items():
            if not isinstance(name, str) or Path(name).parts != (name,) or name == "..":
                raise ValueError("Tool name must be one path component")
            root = Path(destination)
            if (root.is_absolute() or ".." in root.parts
                    or (not root.parts and (destination != "." or name != "public"
                                           or len(destinations) != 1))):
                raise ValueError("Destination must be below HOME")
            # Root overlap could alias Pi runtime paths through another tool key,
            # even when this request contains no colliding file destinations.
            if any(root == other or root in other.parents or other in root.parents for other in roots):
                raise ValueError("Destination roots overlap")
            roots.append(root)
        action = request["action"]
        if action not in ("inspect", "publish") or not isinstance(request["files"], dict):
            raise ValueError("Invalid request")
        with tempfile.TemporaryDirectory(prefix="secagent-config-") as directory:
            source = Path(directory).resolve()
            for name in destinations:
                (source / name).mkdir(mode=0o700)
            for name, encoded in request["files"].items():
                relative = Path(name)
                if (len(relative.parts) < 2 or relative.is_absolute() or ".." in relative.parts
                        or relative.parts[0] not in destinations):
                    raise ValueError("Invalid source path")
                if relative.parts[0] == "pi":
                    check_pi_path(Path(*relative.parts[1:]),
                                  home / destinations["pi"] / Path(*relative.parts[1:]))
                path = source / relative
                # Each new source parent is private, including nested additions.
                for parent in reversed(path.parents):
                    if parent != source and source in parent.parents and not parent.exists():
                        parent.mkdir(mode=0o700)
                with path.open("xb") as stream:
                    stream.write(base64.b64decode(encoded, validate=True))
                path.chmod(0o600)
            plan = config_files.inspect(home, [(source / name, destination)
                                               for name, destination in destinations.items()])
            view = summary(plan)
            written = ()
            if action == "publish":
                if view != request.get("expected"):
                    raise config_files.Refused(home, "destination plan changed; inspect and confirm again")
                written = config_files.publish(plan, approved=True)
            return {"ok": True, "plan": view, "written": [str(path) for path in written]}
    except config_files.Refused as error:
        return {"ok": False, "message": str(error)}
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Redact private configuration/worker diagnostics.
        return {"ok": False, "message": "Configuration worker failed or was interrupted; "
                "publication outcome may be partial. Inspect the selected lab before retrying; "
                "no automatic retry or repair."}


def main(*, destinations=None):
    home = Path("/home/lab-user")
    if (sys.platform != "linux" or os.geteuid() != 1000 or os.getegid() != 1000
            or not os.path.ismount(home)):
        raise RuntimeError("Ordinary lab identity and mounted HOME required")
    print(json.dumps(handle(json.load(sys.stdin), home, destinations=destinations)), flush=True)


if __name__ == "__main__":
    main()
