"""Settled, stopped Lab 3 disposal for reset and the sole root uninstall.

Never starts a gateway or invokes native delete (which may acknowledge only
accepted cleanup and force-remove helpers). Delete only recorded exact Docker
identities, with no references, after STOP and a default-No disposal decision.
"""

import os
import re
import stat
from pathlib import Path

import lab3_resources as resources
import lab3_setup as setup
import lab_tools as tools
from lab3_state import Refused, State
from lab_log import progress


def host_files(state):
    """Flat private evidence only; never follow a link or recurse into unknown data."""
    state.check_directory()
    result = {}
    for path in state.root.iterdir():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise Refused("Unexpected/unsafe Lab 3 evidence entry; preserve the control directory. "
                          "Inspect its file names and permissions without sharing private contents.")
        result[path.name] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return result


def inventory(docker, directory, *, for_stop=False):
    state = State(directory)
    record = state.data["resources"]
    resources.engine_guard(docker, record)
    if for_stop and state.data["phase"] not in ("disposing", "disposed"):
        if (state.data["phase"] not in ("prepared", "stopped", "ready", "running", "cleanup-needed")
                or record.get("pending") or state.data.get("operators_pending")
                or state.data.get("enrollment_pending") or state.data.get("provider_conflict")):
            raise Refused("Lab 3 has unresolved operations; preserve its resources and evidence.")
    elif state.data["phase"] not in ("disposing", "disposed"):
        resources.require_settled(state)
    elif (record.get("pending") or state.data.get("operators_pending")
          or state.data.get("enrollment_pending") or state.data.get("provider_conflict")
          or (state.data.get("enrollment_attempted") and not state.data.get("provider_removed"))):
        raise Refused("Lab 3 disposal/settlement is uncertain; preserve remaining resources and control evidence.")
    selected = {kind: {} for kind in ("container", "network", "volume")}
    for role in record["containers"]:
        obj = resources.inspect_owned(docker, record, role,
                                      absence=role == "supervisor" and bool(record.get("sandbox_id")))
        if obj is not None:
            if not for_stop or obj["State"].get("Running") is not True:
                resources.stopped(obj)
            elif (obj["State"].get("Status") != "running"
                  or any(obj["State"].get(key) for key in ("Paused", "Restarting", "Dead"))):
                raise Refused("Lab 3 lifecycle state is uncertain; preserve the attempt.")
            selected["container"][obj["Name"].lstrip("/")] = obj
    for role, created in record["volumes"].items():
        name = record["name"] + "-" + role
        obj = resources.one(docker.run(["volume", "inspect", name]))
        if (obj["Name"] != name or obj["CreatedAt"] != created or obj["Driver"] != "local"
                or obj.get("Options") or (obj.get("Labels") or {}).get(resources.LABEL) != record["name"]):
            raise Refused("Lab 3 volume identity changed; preserved, no disposal.")
        selected["volume"][name] = obj
    for name, created in record.get("native_volumes", {}).items():
        obj = resources.native_volume(docker, record, name)
        if obj["CreatedAt"] != created:
            raise Refused("Recorded native volume identity changed; preserve all remaining data.")
        selected["volume"][name] = obj
    allowed = {item["Id"] for item in selected["container"].values()}
    for key in ("network", "viewer_network"):
        if not record.get(key):
            continue
        obj = resources.one(docker.run(["network", "inspect", record[key]]))
        expected_name = record["name"] + ("-net" if key == "network" else "-viewer-net")
        if (obj["Id"] != record[key] or obj["Name"] != expected_name or obj["Driver"] != "bridge"
                or (obj.get("Labels") or {}).get(resources.LABEL) != record["name"]
                or set(obj.get("Containers") or {}) - (allowed if for_stop else set())):
            raise Refused("Lab 3 network identity/endpoints changed; preserve it.")
        selected["network"][obj["Name"]] = obj
    # Unknown helpers, even stopped ones, are not adopted for cleanup.
    for ident in docker.run(["ps", "--all", "--no-trunc", "--format", "{{.ID}}"] ).splitlines():
        obj = resources.one(docker.run(["inspect", ident]))
        if not re.fullmatch(r"[a-f0-9]{64}", ident) or obj["Id"] != ident:
            raise Refused("Full exact container identity required for disposal; preserve the selection.")
        labels = obj["Config"].get("Labels") or {}
        ours = (labels.get(resources.LABEL) == record["name"]
                or labels.get("openshell.ai/sandbox-namespace") == record["name"]
                or (record.get("sandbox_id") and labels.get("openshell.ai/sandbox-id") == record["sandbox_id"]))
        if (obj["Id"] not in allowed and (ours
                or any(m.get("Name") in selected["volume"] for m in obj.get("Mounts", []))
                or set(obj["NetworkSettings"].get("Networks") or {}) & selected["network"].keys())):
            raise Refused("Unrecorded Lab 3 helper or unrelated storage reference; preserved. "
                          "Inspect full container IDs/labels on the recorded engine, not a name-based delete.")
    if (record.get("sandbox_id") and state.data["phase"] not in ("disposing", "disposed")
            and resources.native_volumes(docker, record) != record.get("native_volumes")):
        raise Refused("Native storage identity differs from its acknowledged record; preserved.")
    return {"resources": selected, "host": host_files(state), "state": state.data,
            "root_identity": state.root_identity}


def dispose(docker, directory, expected):
    """Caller owns consent. Journal each deletion before dispatch, no retry on loss."""
    state = State(directory)
    with state.lock():
        # Opening a new lock may add an empty private file; it holds no runtime fact.
        current = inventory(docker, directory)
        if current["root_identity"] != expected["root_identity"] or state.root_identity != current["root_identity"]:
            raise Refused("Lab 3 control directory identity changed; nothing deleted.")
        for kind, items in expected["resources"].items():
            now = current["resources"][kind]
            if (now.keys() != items.keys() or any(tools.removal_identity(item, kind)
                    != tools.removal_identity(now[name], kind) for name, item in items.items())):
                raise Refused("Lab 3 resource identity/ownership/dependencies changed after consent; nothing deleted.")
        # inventory() has freshly verified stopped state, settlement and references.
        state.data = current["state"]
        record = state.data["resources"]
        state.phase("disposing")
        for kind in ("container", "network", "volume"):
            for name, before in current["resources"][kind].items():
                resources.engine_guard(docker, record)
                fresh = inventory(docker, directory)["resources"][kind].get(name)
                if fresh is None or tools.removal_identity(fresh, kind) != tools.removal_identity(before, kind):
                    raise Refused("Lab 3 resource changed during disposal; remaining data preserved.")
                if kind != "container":
                    refs = docker.run(["container", "ls", "--all", "--quiet", "--filter", kind + "=" + name])
                    if refs.strip():
                        raise Refused("Lab 3 storage still has container references; preserved.")
                record["pending"] = "delete:" + kind + ":" + name
                state.save()
                target = name if kind == "volume" else before["Id"]
                docker.run([kind, "rm", target], timeout=None)
                # A successful rm response is still independently read back.
                fmt = "{{.Names}}" if kind == "container" else "{{.Name}}"
                names = docker.run([kind, "ls", *(["--all"] if kind == "container" else []), "--format", fmt])
                if name in names.splitlines():
                    raise Refused("Deletion not confirmed; pending disposal preserved. No automatic retry.")
                if kind == "container":
                    role = next(role for role, value in record["containers"].items() if value["id"] == target)
                    del record["containers"][role]
                elif kind == "network":
                    key = next(key for key in ("network", "viewer_network") if record[key] == target)
                    record[key] = None
                elif name in record.get("native_volumes", {}):
                    del record["native_volumes"][name]
                else:
                    del record["volumes"][name.removeprefix(record["name"] + "-")]
                record.pop("pending")
                state.save()
                print("Removed Lab 3:", kind, name, flush=True)
        record["stage"] = "disposed"
        state.phase("disposed")
    return state


def remove_host(state):
    """Only after verified resource disposal; no private archive or recursive erase."""
    if state.data["phase"] != "disposed":
        raise Refused("Verified Lab 3 disposal is required before deleting control evidence.")
    snapshot = host_files(state)
    for name in sorted(snapshot, key=lambda value: value == "state.json"):
        before = snapshot[name]
        if host_files(state).get(name) != before:
            raise Refused("Evidence changed during disposal; preserve remaining files.")
        (state.root / name).unlink()
    state.root.rmdir()


def reset(docker, directory, *, confirm=None, verbose=False):
    """Default-No stopped disposal, preflight current public inputs, fresh stopped setup."""
    progress("Validating stopped resources and provider settlement before reset consent.", verbose=verbose)
    snapshot = inventory(docker, directory)
    print("Reset selected Lab 3: deletes the following resources and ALL private attempt evidence/work:")
    for kind, items in snapshot["resources"].items():
        for name in items:
            print(" ", kind, name)
    print("  control/evidence:", str(Path(directory)))
    print("Saved menu/site results, configuration, sessions, logs and client/provider storage are lost. "
          "Images/preparation/unrelated resources remain. No cloud cancellation/upstream key revocation.")
    accepted = confirm() if confirm is not None else input("Dispose this stopped attempt and recreate? (y/N) ").strip().lower() in ("y", "yes")
    if accepted is not True:
        return "Reset cancelled; nothing deleted."
    # Do not discard a working attempt if its replacement public inputs cannot be prepared.
    progress("Preparing replacement public inputs before any disposal.", verbose=verbose)
    setup.configuration.preflight()
    setup.software.prepare(docker)
    engine_socket = snapshot["state"]["resources"]["engine_socket"]
    state = dispose(docker, directory, snapshot)
    remove_host(state)
    setup.prepare_fresh(docker, directory, engine_socket=engine_socket)
    return "Lab 3 reset: verified disposal completed; fresh setup is stopped. Use ./lab.sh lab3 run-pipeline. No START submitted."
