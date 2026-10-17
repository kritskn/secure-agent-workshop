"""Lab 2 recorded resource identity and lifecycle inspection; no host ledger.

Setup requires stopped resources; entry/stop may inspect a stable running run.
Removal and stop can validate resources without inspecting an unavailable image.
"""

import json
import re

import lab2_image as software
import lab2_resources as resources
import lab_tools as tools


class Refused(RuntimeError):
    """Known refusal; preserve resources without guessing ownership or state."""


class NotStopped(Refused):
    """A stopped-state prerequisite failed; callers may add operation-specific help."""


def lifecycle_state(data, name):
    """Only created/exited or normally running containers are actionable."""
    state = data.get("State") or {}
    status = state.get("Status")
    if (status not in ("created", "exited", "running")
            or state.get("Running") is not (status == "running")
            or any(state.get(key) for key in ("Paused", "Restarting", "Dead"))):
        raise Refused(f"Container {name!r} has uncertain lifecycle state; preserve it "
                      "and inspect its status on the selected engine. No automatic recovery.")
    return status


def require_idle(docker, run, *, allow_reservation=False):
    """Reject workers; a caller may allow only its separately validated reservation."""
    if type(run) is not int or run not in (1, 2):
        raise Refused("Select Lab 2 Run 1 or Run 2; no action taken.")
    prefix = f"secagent-lab2-run{run}-"
    allowed = {prefix + role for role in resources.CONTAINERS}
    if allow_reservation:
        allowed.add(prefix + "setup-reservation")
    names = docker.run(["container", "ls", "--all", "--format", "{{.Names}}"]).splitlines()
    if any(name.startswith(prefix) and name not in allowed for name in names):
        raise Refused(f"Lab 2 Run {run} has a setup reservation or unexpected worker; "
                      "preserve it and inspect selected-run container status. "
                      "No takeover, retry or removal.")


def inspect_one(docker, kind, name):
    try:
        result = json.loads(docker.run([kind, "inspect", name]))
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            raise ValueError("Exact resource required")
        return result[0]
    except Exception:  # noqa: BLE001 - Never expose private Docker diagnostics.
        raise Refused(f"Cannot confirm {kind} {name!r}; preserve it and inspect its metadata "
                      "on the selected Docker engine before another lifecycle operation. No automatic retry.") from None


def stopped(data, name):
    state = data.get("State") or {}
    if (state.get("Running") is not False or state.get("Status") not in ("created", "exited")
            or any(state.get(key) for key in ("Paused", "Restarting", "Dead"))):
        raise NotStopped(f"Container {name!r} is not confirmed stopped. Save editor work; use the selected "
                      "lab's supported stop command and confirm its status before continuing. "
                      "No implicit stop or automatic retry.")


def token(data, kind):
    value = data.get("CreatedAt") if kind == "volume" else data.get("Id")
    if not isinstance(value, str) or not value or (kind != "volume" and not re.fullmatch(r"[a-f0-9]{64}", value)):
        raise Refused("Resource identity is incomplete; preserve storage and inspect Docker metadata.")
    return value


def inventory(docker, run):
    """Only inspect the selected new namespace; never search legacy state."""
    names = {}
    for kind in ("container", "volume", "network"):
        format_string = "{{.Names}}" if kind == "container" else "{{.Name}}"
        flags = ["--all"] if kind == "container" else []
        names[kind] = set(docker.run([kind, "ls", *flags, "--format", format_string]).splitlines())
    return {role for role, kind in resources.Plan.roles().items()
            if f"secagent-lab2-run{run}-{role}" in names[kind]}


def guard(docker, plan, expected, *, complete, require_stopped=True):
    """Recheck generation, resource IDs, isolation, stopped state and sharing."""
    data = {}
    for role, identity in expected.items():
        kind = plan.roles()[role]
        item = inspect_one(docker, kind, plan.name(role))
        try:
            plan.validate(item, role)
        except (ValueError, TypeError, KeyError):
            raise Refused(f"Lab 2 {role} ownership or isolation differs; preserve resources and "
                          "inspect the selected run before retrying. No adoption or repair.") from None
        if token(item, kind) != identity:
            raise Refused(f"Lab 2 {role} was replaced; preserve resources and inspect this run's metadata.")
        if kind == "container":
            if require_stopped:
                stopped(item, plan.name(role))
            else:
                lifecycle_state(item, plan.name(role))
        data[role] = item
    containers = tuple(role for role in resources.CONTAINERS if role in expected) if complete else ()
    for role in expected:
        kind = plan.roles()[role]
        if kind == "volume":
            refs = set(docker.run(["container", "ls", "--all", "--no-trunc", "--quiet",
                                  "--filter", "volume=" + plan.name(role)]).splitlines())
            allowed = {expected[container] for container in containers
                       if any(volume == role for volume, _, _ in plan.mounts(container))}
            if refs != allowed:
                raise Refused(f"Volume {plan.name(role)!r} has unexpected container references; "
                              "preserve it and inspect those references before another lifecycle operation.")
        elif kind == "network":
            allowed = {expected[container] for container in containers if role in plan.networks(container)}
            if set(data[role].get("Containers") or {}) - allowed:
                raise Refused(f"Network {plan.name(role)!r} has unexpected endpoints; preserve it "
                              "and inspect connected containers before another lifecycle operation.")
    return data


def existing(docker, run, app_port=None, *, require_stopped=True, validate_image=True):
    present = inventory(docker, run)
    if not present:
        return None
    if present != set(resources.Plan.roles()):
        raise Refused(f"Incomplete Lab 2 Run {run} resources are preserved. Inspect the selected "
                      "run's named containers, volumes and networks; do not retry fresh creation or force removal.")
    agent = inspect_one(docker, "container", f"secagent-lab2-run{run}-agent")
    try:
        labels = agent["Config"]["Labels"]
        plan = resources.Plan(run, labels["org.secagent.run-id"], agent["Image"],
                              int(labels["org.secagent.lab2.app-port"]))
    except (ValueError, TypeError, KeyError):
        raise Refused("Lab 2 completion metadata is incompatible; preserve this run without migration.") from None
    if validate_image:
        software.validate_image(inspect_one(docker, "image", plan.image),
                                architecture=tools.engine_architecture(docker))
    if app_port is not None and app_port != plan.app_port:
        raise Refused(f"Run {run} retains browser port {plan.app_port}; rerun setup without --app-port "
                      "to preserve it. Changing topology requires separately confirmed recreation.")
    try:
        expected = json.loads(labels["org.secagent.lab2.resources"])
        if not isinstance(expected, dict) or set(expected) != set(plan.roles()) - {"agent"}:
            raise ValueError("Incomplete recorded identities")
        for role, identity in expected.items():
            if (not isinstance(identity, str) or not identity
                    or (plan.roles()[role] != "volume" and not re.fullmatch(r"[a-f0-9]{64}", identity))):
                raise ValueError("Invalid recorded identity")
        expected["agent"] = token(agent, "container")
    except (ValueError, TypeError, KeyError):
        raise Refused("Lab 2 recorded resource identities are incompatible; preserve this run without adoption.") from None
    guard(docker, plan, expected, complete=True, require_stopped=require_stopped)
    return plan, expected
