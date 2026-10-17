"""Selected stopped Lab 3 setup; no execution/controller or credential imports."""

import os

import lab3_config as configuration
import lab3_guards as guards
import lab3_image as software
import lab3_resources as resources
from lab3_state import Refused, State


def prepare_fresh(docker, directory, *, engine_socket):
    """Create exclusive control state before effects; never adopt partial storage."""
    state = State(directory, {})
    with state.lock():
        state.phase("preparing")
        try:
            state.data["resources"] = resources.plan(docker, engine_socket)
            state.save()
            resources.create(docker, state.data["resources"], state.save)
            state.phase("prepared")
        except Refused:
            state.phase("cleanup-needed")
            raise
        except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Persist uncertainty and redact private failures.
            state.phase("cleanup-needed")
            raise Refused("Lab 3 stopped setup incomplete; partial resources and pending-operation evidence "
                          "are preserved. Inspect the selected private phase/pending operation before "
                          "recovery; no automatic retry, adoption or rollback.") from None
    return state


def deploy(docker, state, *, stream=None, confirm=None):
    """Update only public state/editor files; preserve consumed actions and images."""
    record = state.data["resources"]

    def guard(**_options):
        resources.engine_guard(docker, record)
        resources.require_settled(state)
        for role in record["containers"]:
            obj = resources.inspect_owned(docker, record, role)
            resources.stopped(obj)
        guards.prepared_guard(docker, record, active=False)

    def pending(active):
        if active:
            record["pending"] = "configuration-worker"
        else:
            record.pop("pending", None)
        state.save()

    guard()
    try:
        return configuration.deploy(docker, record, guard=guard, pending=pending,
                                    stream=stream, confirm=confirm)
    except configuration.config_deploy.Uncertain:
        record["pending"] = "configuration-worker"
        state.phase("cleanup-needed")
        raise


def setup(docker, directory, *, engine_socket=None, diagnostic=None, tool_output=None,
          stream=None, confirm=None):
    """Build public software only for fresh setup; repeat retains recorded images."""
    if os.path.lexists(directory):
        state = State(directory)
        with state.lock():
            record = state.data["resources"]
            resources.engine_guard(docker, record)
            if engine_socket is not None and engine_socket != record["engine_socket"]:
                raise Refused("Existing engine-side socket differs; no migration. Retain the selected environment.")
            result = deploy(docker, state, stream=stream, confirm=confirm)
        return state, result
    # Public preflight/build failure must not create an attempt directory.
    require_fresh_inventory(docker)
    configuration.preflight()
    software.prepare(docker, diagnostic=diagnostic, tool_output=tool_output)
    state = prepare_fresh(docker, directory, engine_socket=engine_socket or "/var/run/docker.sock")
    return state, "Gateway/editor configuration initialized and stopped resources verified."


def require_fresh_inventory(docker):
    """Absent control state does not authorize adopting/bypassing older resources."""
    for kind in ("container", "volume", "network"):
        fmt = "{{.Names}}" if kind == "container" else "{{.Name}}"
        names = docker.run([kind, "ls", *(["--all"] if kind == "container" else []), "--format", fmt])
        for name in names.splitlines():
            if name.startswith("secagent-lab3-"):
                raise Refused("Lab 3 resources exist without this selected control record; preserved. "
                              "Use the original state root/engine; no adoption or new attempt.")
            if kind == "container" or name.startswith("openshell-"):
                obj = resources.one(docker.run([kind, "inspect", name]))
                labels = ((obj.get("Config") or {}).get("Labels") if kind == "container" else obj.get("Labels")) or {}
                if (str(labels.get(resources.LABEL, "")).startswith("secagent-lab3-")
                        or str(labels.get("openshell.ai/sandbox-namespace", "")).startswith("secagent-lab3-")):
                    raise Refused("Unselected native Lab 3 resource preserved; find its original private control "
                                  "state and settle STOP there. Do not bypass it with a fresh attempt.")
